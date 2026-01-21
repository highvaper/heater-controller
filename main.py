
import utime
import sys

from collections import deque

import machine
from machine import ADC, Pin, I2C, Timer, WDT, PWM, reset

from ssd1306 import SSD1306_I2C

import uasyncio as asyncio

from simple_pid import PID

from customtimer import CustomTimer
from thermocouple import Thermocouple
from displaymanager import DisplayManagerFactory
from inputhandler import InputHandler
from menusystem import MenuSystem

from heaters import HeaterFactory, InductionHeater, ElementHeater

import utils

from shared_state import SharedState


# Load hardware configuration
hw, hardware_name = utils.load_hardware_config()

# Pin assignments (with fallback defaults if hardware.txt is missing)
hardware_pin_red_led = hw.get('red_led', 17)
hardware_pin_green_led = hw.get('green_led', 18)
hardware_pin_blue_led = hw.get('blue_led', 19)

hardware_pin_display_scl = hw.get('display_scl', 21)
hardware_pin_display_sda = hw.get('display_sda', 20)

hardware_pin_buzzer = hw.get('buzzer', 16)

hardware_pin_rotary_clk = hw.get('rotary_clk', 13)
hardware_pin_rotary_dt = hw.get('rotary_dt', 12)
hardware_pin_button = hw.get('button', 14)

hardware_pin_switch_left = hw.get('switch_left', 23)
hardware_pin_switch_middle = hw.get('switch_middle', 24)
hardware_pin_switch_right = hw.get('switch_right', 25)

hardware_pin_termocouple_sck = hw.get('thermocouple_sck', 6)
hardware_pin_termocouple_cs = hw.get('thermocouple_cs', 7)
hardware_pin_termocouple_so = hw.get('thermocouple_so', 8)

hardware_pin_heater = hw.get('heater', 22)
hardware_pin_voltage_divider_adc = hw.get('voltage_divider_adc', 28)

# Configure global hardware pins in utils module
utils.set_voltage_divider_adc_pin(hardware_pin_voltage_divider_adc)


####################################





def timerSetPiTemp(t):
    global pi_temperature_sensor, pidTimer, display_manager, heater, shared_state
   
    shared_state.pi_temperature = utils.get_pi_temperature_or_handle_error(pi_temperature_sensor,display_manager,shared_state)
    
    # Check if the temperature is safe
    if shared_state.pi_temperature > shared_state.pi_temperature_limit:
        try:
            if not pidTimer.is_timer_running: pidTimer.stop() 
            heater.off()
            error_text = shared_state.error_messages.get("pi-too_hot", "PI too hot")
            shared_state.set_error("pi-too_hot", error_text)
            while not shared_state.pi_temperature <= shared_state.pi_temperature_limit:
                shared_state.pi_temperature = utils.get_pi_temperature_or_handle_error(pi_temperature_sensor,display_manager,shared_state)
                utime.sleep_ms(250)  # Warning shown for 5 secs so has had a time to cool down a bit
            
            shared_state.clear_error()
            pidTimer.start()
        except Exception as e:
            heater.off()
            print("Error updating display or deinitializing timers:", e)
            # dont feed watchdog let it reboot
    else:
        if not pidTimer.is_timer_running: pidTimer.start()


def timerUpdatePIDandHeater(t):  #nmay replace what this does in the check termocouple function 
                                 #this needs a major clear up now we have share_state 
    global heater, thermocouple, pidTimer, display_manager, shared_state

    if shared_state.pid.setpoint != shared_state.temperature_setpoint:
        shared_state.pid.setpoint = shared_state.temperature_setpoint

    if thermocouple is not None:
        new_heater_temperature, need_heater_off_temperature = utils.get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state)
    else:
        new_heater_temperature = 0
        need_heater_off_temperature = False

    if new_heater_temperature < 0: # Non fatal error occured 
        heater.off() #should already be off
        return   # Let timer run this again and hopefully next time error has passed

    # new temperature is valid
    shared_state.heater_temperature = new_heater_temperature
    
    shared_state.input_volts = utils.get_input_volts(shared_state.input_volts)

    #shared_state.heater_max_duty_cycle_percent - need to update this now and adjust to MAX WATTS (add to shared state)
    if shared_state.input_volts > 0:
        shared_state.heater_max_duty_cycle_percent = (shared_state.temporary_max_watts / (shared_state.input_volts * shared_state.input_volts / shared_state.heater_resistance)) * 100  
    else:
        shared_state.heater_max_duty_cycle_percent = 100
        
    if shared_state.heater_max_duty_cycle_percent > 100:
        shared_state.heater_max_duty_cycle_percent = 100
    heater.set_max_duty_cycle(shared_state.heater_max_duty_cycle_percent)
    
    if need_heater_off_temperature:
        heater.off()
        print("Getting safe off heater temperature")
        utime.sleep_ms(301) # lets give everything a moment to calm down
        new_heater_temperature, _ = utils.get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state)
        if new_heater_temperature < 0: # Non fatal error occured 
            return   # Let timer run this again and hopefully next time error has passed
        # new off temperature is valid
        shared_state.heater_temperature = new_heater_temperature

    # Append to ring buffer - automatically removes oldest when full
    shared_state.temperature_readings.append(int(shared_state.heater_temperature))
    shared_state.input_volts_readings.append(shared_state.input_volts)

    shared_state.temperature_setpoint_readings.append(int(shared_state.temperature_setpoint))

    # Calculate watts and append to ring buffer
    if heater.is_on():
        # Calculate actual watts from voltage, resistance, and actual duty cycle
        # Don't use heater_max_duty_cycle_percent as that's a safety limit, not the actual power
        shared_state.watts = int((((shared_state.input_volts*shared_state.input_volts) / shared_state.heater_resistance) * (heater.get_power() / 100)))
    else:
        shared_state.watts = 0
    
    shared_state.watt_readings.append(shared_state.watts)

    # Check if autosession is active and update setpoint if needed
    if shared_state.get_mode() == "autosession" and shared_state.autosession_profile:
        # Calculate actual elapsed time since autosession start (adjusted by rotary dial)
        elapsed_ms = utime.ticks_diff(utime.ticks_ms(), shared_state.autosession_start_time)
        # Clamp elapsed time to valid range (0 to profile duration)
        elapsed_ms = max(0, elapsed_ms)
        
        profile_setpoint = shared_state.autosession_profile.get_setpoint_at_elapsed_time(elapsed_ms)
        
        if profile_setpoint is not None:
            # Profile is still active, update setpoint
            profile_setpoint = profile_setpoint
            shared_state.temperature_setpoint = profile_setpoint
        else:
            # Profile has finished
            # End the session when autosession profile completes
            shared_state.set_mode("Off")

    if shared_state.control == 'temperature_pid' or shared_state.control == 'autosession':
        if shared_state.heater_temperature is not None:
            power = shared_state.pid(shared_state.heater_temperature)  # Update pid even if heater is off
        else:
            power = 0  # No valid temperature, stay off
    elif shared_state.control == 'duty_cycle':
        power = shared_state.set_duty_cycle  # Use duty cycle directly (0-100%)
    else:
        # In watts mode, calculate duty cycle needed to produce desired watts at current voltage
        # watts = (V^2 / R) * (duty% / 100)
        # duty% = (watts * R / V^2) * 100
        if shared_state.input_volts > 0:
            power = (shared_state.set_watts * shared_state.heater_resistance / (shared_state.input_volts * shared_state.input_volts)) * 100
        else:
            power = 0

    power = min(power , 100)  #Limit happening in heater set power but lets limit here too
    
    if shared_state.get_mode() == "Off": 
        heater.off()
        return
    
    if shared_state.power_type == 'lipo':
        if (shared_state.input_volts / shared_state.lipo_count) < shared_state.lipo_safe_volts:
            heater.off()
            shared_state.set_mode("Off")
            error_text = shared_state.error_messages.get("battery_level-too-low", "Battery too low")
            shared_state.set_error("battery_level-too-low", error_text)
        else:
            # Voltage is safe, clear error
            shared_state.clear_error()
    elif shared_state.power_type == 'lead':
        if shared_state.input_volts  < shared_state.lead_safe_volts:
            heater.off()
            shared_state.set_mode("Off")
            error_text = shared_state.error_messages.get("battery_level-too-low", "Battery too low")
            shared_state.set_error("battery_level-too-low", error_text)
        else:
            # Voltage is safe, clear error
            shared_state.clear_error()
    elif shared_state.power_type == 'mains':
        if shared_state.input_volts > shared_state.mains_safe_volts:
            heater.off()
            shared_state.set_mode("Off")
            error_text = shared_state.error_messages.get("mains-voltage-too-high", "Mains voltage too high")
            shared_state.set_error("mains-voltage-too-high", error_text)
        else:
            # Voltage is safe, clear error
            shared_state.clear_error()
    else:
        heater.off()
        shared_state.set_mode("Off")
        error_text = shared_state.error_messages.get("unknown-power-type", "Unknown power type")
        shared_state.set_error("unknown-power-type", error_text)    
   
        
    if power > shared_state.power_threshold:
        # Temperature over-limit protection with hysteresis
        if shared_state.heater_temperature > 250:
            shared_state.heater_too_hot = True
        elif shared_state.heater_temperature < 240:  # Hysteresis threshold
            shared_state.heater_too_hot = False
        
        if shared_state.heater_too_hot:
            # Ensure heater is OFF before showing error
            heater.set_power(0)
            heater.off()
            error_text = "Pausing heater - " + shared_state.error_messages["heater-too_hot"] + " " + str(shared_state.heater_temperature)
            print(error_text)
            # Set error in shared_state to display on screen
            if not shared_state.has_error():
                shared_state.set_error("heater-too_hot", error_text)
        else:
            # Temperature is safe, clear error flag
            shared_state.clear_error()
            # Only turn heater back on if we were trying to heat
            if not heater.is_on():
                if shared_state.get_mode() != "Off":
                    heater.on(power)
            # Set power only when temperature is safe
            if isinstance(heater, ElementHeater):
                heater.set_power(power)
    else:
        heater.off()  #Maybe we call this no matter what just in case?
    
    # Log autosession data if active and logging is enabled
    if shared_state.autosession_logging_enabled and shared_state.get_mode() == "autosession" and shared_state.autosession_profile:
        elapsed_ms = utime.ticks_diff(utime.ticks_ms(), shared_state.autosession_start_time)
        elapsed_ms = max(0, elapsed_ms)
        
        # Log the data with buffering
        shared_state.autosession_log_buffer, shared_state.autosession_log_file = utils.log_autosession_data(
            shared_state.autosession_log_file,
            shared_state.autosession_log_buffer,
            elapsed_ms,
            shared_state.heater_temperature,
            shared_state.temperature_setpoint,
            shared_state.input_volts,
            heater.get_power(),
            shared_state.watts,
            shared_state.pid.components[0],
            shared_state.pid.components[1],
            shared_state.pid.components[2],
            shared_state.autosession_log_buffer_flush_threshold,
            shared_state.led_blue_pin
        )






###############################################################
#
# Initialisation 
#
# The led on the pico should blink brielfy before the display powers up 
# if no led blink we have a problem but do not think there is a 
# way to know so user needs to be aware that it should blink once breifly
# 
# If there is an issue with the display setup then the led will flash 3 times 
# and switch off for about a second and repeat the flashing and off.
#
# Other errors should be reported on the screen as it should now be avaliable
#
###############################################################

print("LEDs Initialising ...")
try:
    #led_pin = Pin(hardware_pin_led, Pin.OUT) #This is the built in pin on the pico
    led_red_pin = Pin(hardware_pin_red_led, Pin.OUT) 
    led_red_pin.on()
    utime.sleep_ms(75)
    led_red_pin.off()
    utime.sleep_ms(75)
    led_red_pin.on()
    utime.sleep_ms(75)
    led_red_pin.off()

    led_green_pin = Pin(hardware_pin_green_led, Pin.OUT) 
    led_green_pin.on()
    utime.sleep_ms(75)
    led_green_pin.off()
    utime.sleep_ms(75)
    led_green_pin.on()
    utime.sleep_ms(75)
    led_green_pin.off()

    led_blue_pin = Pin(hardware_pin_blue_led, Pin.OUT) 
    led_blue_pin.on()
    utime.sleep_ms(75)
    led_blue_pin.off()
    utime.sleep_ms(75)
    led_blue_pin.on()
    utime.sleep_ms(75)
    led_blue_pin.off()

    print("LEDs initialised.")
except Exception as e:
    print("Error initializing LED pin, unable to continue:", e)
    sys.exit()



shared_state = SharedState(led_red_pin=led_red_pin, led_green_pin=led_green_pin, led_blue_pin=led_blue_pin)

# Set the hardware name from loaded config
shared_state.hardware = hardware_name

# Load profile list at startup (like show_settings loads all settings once)



# Load normal profiles list
shared_state.profile_list = utils.list_profiles()
shared_state.profile_selection_index = 0

# Load autosession profiles list (do not load profile itself)
shared_state.autosession_profile_list = utils.list_autosession_profiles()
shared_state.autosession_profile_selection_index = 0


# Load saved default profile if it exists
try:
    with open('/current_profile.txt', 'r') as f:
        profile_name = f.readline().strip()
    if profile_name:
        print(f"Loading profile: {profile_name}")
        config = utils.load_profile(profile_name, shared_state)
        
        # Check if profile requires different hardware than currently loaded
        profile_hardware = config.get('hardware', 'default')
        if profile_hardware != hardware_name:
            print(f"Profile requires hardware '{profile_hardware}' but '{hardware_name}' is loaded")
            print(f"Updating current_hardware.txt and rebooting...")
            try:
                with open('/current_hardware.txt', 'w') as f:
                    f.write(profile_hardware)
                print(f"Saved current hardware: {profile_hardware}")
                #no screen message as display may not be working with new hardware
                #flash blue led 3 times and reboot
                for _ in range(3):
                    led_blue_pin.on()
                    utime.sleep_ms(200)
                    led_blue_pin.off()
                    utime.sleep_ms(200)
                reset()
            except Exception as e:
                print(f"Error updating hardware config: {e}")
        
        shared_state.apply_profile(config)
        shared_state.set_profile_name(profile_name)
    else:
        print("No profile name found in /current_profile.txt")
except OSError:
    print("No /current_profile.txt found, using default settings")



# Load saved autosession profile if it exists
# First check if the loaded profile has a default_autosession_profile
if shared_state.default_autosession_profile:
    print(f"Loading default autosession profile from profile: {shared_state.default_autosession_profile}")
    success, message = utils.apply_and_save_autosession_profile(shared_state.default_autosession_profile, shared_state)
    print(message)
else:
    # Fall back to current_autosession_profile.txt if no default in profile
    try:
        with open('/current_autosession_profile.txt', 'r') as f:
            autosession_profile_name = f.readline().strip()
        if autosession_profile_name:
            print(f"Loading autosession profile: {autosession_profile_name}")
            success, message = utils.apply_and_save_autosession_profile(autosession_profile_name, shared_state)
            print(message)
        else:
            print("No autosession profile name found in /current_autosession_profile.txt")
    except OSError:
        print("No /current_autosession_profile.txt found, skipping autosession profile load")





# DisplayManager
# Display type options: 'SSD1306_128x32', 'SSD1306_128x64'
display_type = hw.get('display_type', 'SSD1306_128x32')

print("Display Initialising ...")
if display_type in 'SSD1306_128x32,SSD1306_128x64':
    display = utils.initialize_display(hardware_pin_display_scl, hardware_pin_display_sda, led_red_pin)
else:
    error_text = "Display init failed - unknown display type: " + str(display_type)
    print(error_text)   
    while True: 

        utime.sleep_ms(100)
print("Display initialised.")


try:
    display_manager = DisplayManagerFactory.create_display_manager(display_type, display, shared_state)
    # Update shared_state with actual display width and reinitialize ring buffers
    shared_state.display_width = display.width
    shared_state.temperature_readings = deque([0], shared_state.display_width)   #  shared_state.display_width * 2 etc to get more data on graphs 
    shared_state.input_volts_readings = deque([0], shared_state.display_width)   #  maybe make this adjustable later in profile
    shared_state.watt_readings = deque([0], shared_state.display_width)
    shared_state.temperature_setpoint_readings = deque([0], shared_state.display_width)
    # startup screen will be scheduled from async_main so it doesn't block here
except Exception as e:
    error_text = "Start up failed - [display-setup] " + shared_state.error_messages["display-setup"] + " " + str(e)
    print(error_text + " " + str(e))
    display.fill(0)
    display.text(error_text, 0, 0)
    display.text(str(e), 0, 15)
    display.show()
    while True:
        # Flash a LED as a backup - maybe some kind of code like one flash,flash,off,off,flash.off,off etc 
        utime.sleep_ms(100)
    sys.exit()



# Buzzer - 2 short buzzes for notifying user session has ended 
#        - 1 buzz when hitting setpoint for first time in a session
print("Buzzer Initialising ...")
buzzer = PWM(Pin(hardware_pin_buzzer))
utils.buzzer_play_tone(buzzer, 2500, 200)  # Play a sound so we know its connected correctly
print("Buzzer initialised.")

# Check disk space
free_kb = utils.get_free_disk_space()
if free_kb is not None:
    print(f"Free disk space: {int(free_kb)}KB")
    if free_kb < 200:
        utils.buzzer_play_tone(buzzer, 1500, 300)
        utime.sleep_ms(100)
        utils.buzzer_play_tone(buzzer, 1500, 300)
        display_manager.show_low_disk_space_screen(free_kb)
        print(f"Warning: Low disk space - {int(free_kb)}KB remaining")

#button_pin = Pin(hardware_pin_button, Pin.IN)
button_pin = Pin(hardware_pin_switch_middle, Pin.IN, Pin.PULL_UP)
print(button_pin.value())
if button_pin.value():
    enable_watchdog = True
                            
    print("Watchdog: On")
else:
    enable_watchdog = False
    utime.sleep_ms(150)
    utils.buzzer_play_tone(buzzer, 2000, 250)
    utime.sleep_ms(150)
    utils.buzzer_play_tone(buzzer, 1000, 250)
    display_manager.show_watchdog_off_screen()
    print("Watchdog: Off")
del button_pin




#switch_middle = Pin(hardware_pin_switch_middle, Pin.IN, Pin.PULL_UP)

#def switch_middle_pressed(pin):
#    # Toggle LED when button is pressed
#    #led.toggle()
#    led_blue_pin.toggle()

#switch_middle.irq(trigger=Pin.IRQ_FALLING, handler=switch_middle_pressed)


# Maybe put in function reset when options reloaded as they may affect settings
#Termocouple K type
#MAX6675

# Initialize termocouple before switching on heater
try:
    utime.sleep_ms(100)
    thermocouple = Thermocouple(hardware_pin_termocouple_sck, hardware_pin_termocouple_cs, hardware_pin_termocouple_so, shared_state.heater_on_temperature_difference_threshold, shared_state)
    utime.sleep_ms(350)
except Exception as e:
    error_text = "Thermocouple init failed: " + str(e)
    print(error_text)
    try:
        shared_state.set_error("thermocouple-not-available", error_text)
    except Exception:
        pass
    shared_state.disable_control('temperature_pid')
    display_manager.fill_display("thermocouple-setup", 0, 12)
    thermocouple = None

if thermocouple is not None:
    _, _ = thermocouple.get_filtered_temp(False)  # Sets: last_known_safe_temp - Do here rather than in class as it sometimes returns error if on class init 

if shared_state.has_error():
    err = shared_state.current_error[0]
    if isinstance(err, str) and err.startswith('thermocouple') or err == 'thermocouple-not-available':
        # Give the user a moment to see the message, then clear it so the home screen appears
        utime.sleep_ms(1000)
        shared_state.clear_error()

        # Thermocouple not available — switch to duty_cycle control so temperature-pid can't be selected
        shared_state.control = 'duty_cycle'
        shared_state.rotary_last_mode = None


# PI Temperature Sensor 
pi_temperature_sensor = machine.ADC(4)
shared_state.pi_temperature = utils.get_pi_temperature_or_handle_error(pi_temperature_sensor, display_manager, shared_state)


# InputHandler
input_handler = InputHandler(rotary_clk_pin=hardware_pin_rotary_clk, rotary_dt_pin=hardware_pin_rotary_dt, button_pin=hardware_pin_button, switch_control_pin=hardware_pin_switch_left, middle_button_pin=hardware_pin_switch_middle, shared_state=shared_state)

# MenuSystem
menu_system = MenuSystem(display_manager, shared_state)


while shared_state.input_volts is False:
    shared_state.input_volts = utils.get_input_volts(False)
    utime.sleep_ms(50)

#lets do some sanity checks on power level 
#warn user if high but still not ridiculous
#reduce if too high to more sensible level

# Create heater based on heater_type in shared_state
if shared_state.heater_type == 'induction':
    # InductionHeater requires timer and coil pins
    # Coil pins need to be defined in hardware.txt, using defaults for now
    ihTimer = CustomTimer(-1, machine.Timer.PERIODIC, lambda t: None)  # Timer for coil switching
    heater = HeaterFactory.create_heater('induction', coil_pins=(12, 13), timer=ihTimer)
else:
    # ElementHeater (default)
    heater = HeaterFactory.create_heater('element', hardware_pin_heater)

heater.off()



pidTimer = CustomTimer(371, machine.Timer.PERIODIC, timerUpdatePIDandHeater)  # need to have timer setup before calling below 
shared_state.heater_temperature, _ = utils.get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state)
# Do not start timers here; they'll be started when the asyncio loop is running
# pidTimer.start()
# pid.reset()
piTempTimer = CustomTimer(903, machine.Timer.PERIODIC, timerSetPiTemp)
print("Timers initialised.")

#enable_watchdog = False
if enable_watchdog: 
    watchdog = machine.WDT(timeout=(1000 * 3)) 
    print("Watchdog enabled")


async def async_main():
    # Start periodic timers now that (optionally) the asyncio loop is running.
    try:
        pidTimer.start()
        shared_state.pid.reset()
    except Exception as e:
        print(f"Error starting pidTimer: {e}")
    try:
        piTempTimer.start()
    except Exception as e:
        print(f"Error starting piTempTimer: {e}")

    # Start display heartbeat as a background task if available
    if hasattr(display_manager, 'start_heartbeat') and asyncio:
        try:
            display_manager.start_heartbeat(loop=asyncio.get_event_loop(), interval_ms=70)
        except Exception as e:
            try:
                display_manager.start_heartbeat(interval_ms=70)
            except Exception:
                pass

    try:
        display_manager.show_startup_screen()
    except Exception as e:
        print(f"Error showing startup screen: {e}")

    await asyncio.sleep_ms(100)  # Brief pause before main loop

    while True:
        try:
            # Check and display any active errors
            if shared_state.has_error():
                display_manager.show_error()
            # Check if user clicked middle button to show temporary_max_watts screen
            elif shared_state.middle_button_pressed:
                display_manager.stop_home()
                shared_state.in_menu = False  # Make sure we exit menu mode
                shared_state.temporary_max_watts_screen_active = True
                shared_state.temporary_max_watts_start_time = utime.ticks_ms()
                shared_state.rotary_last_mode = None  # Reset so setup_rotary_values sets it to "Temporary Max Watts"
                input_handler.setup_rotary_values()
                display_manager.show_screen_temporary_max_watts()
                shared_state.middle_button_pressed = False
            # Handle temporary_max_watts screen display with timeout
            elif shared_state.temporary_max_watts_screen_active:
                # Check if timeout has elapsed (2 seconds with no rotary activity)
                elapsed = utime.ticks_diff(utime.ticks_ms(), shared_state.temporary_max_watts_start_time)
                if elapsed >= 2000:
                    # Timeout - return to home screen
                    shared_state.temporary_max_watts_screen_active = False
                    shared_state.rotary_last_mode = None
                    shared_state.current_menu_position = 1
                else:
                    # Still displaying - update the screen
                    display_manager.show_screen_temporary_max_watts()
            elif not shared_state.in_menu:
                if shared_state.current_menu_position <= 1:
                    # ensure rotary values set once (but not if temporary_max_watts screen is active)
                    # Also ensure rotary is reconfigured when autosession starts/stops
                    # Don't reconfigure if we're already in autosession mode with rotary set to autosession
                    if (shared_state.rotary_last_mode != "setpoint" and shared_state.rotary_last_mode != "autosession" and not shared_state.temporary_max_watts_screen_active) or \
                       (shared_state.get_mode() == "autosession" and shared_state.rotary_last_mode != "autosession"):
                        input_handler.setup_rotary_values()
                    shared_state.current_menu_position = 1
                    # start async home-screen updater (no-op if already running)
                    display_manager.start_home(heater, loop=asyncio.get_event_loop() if asyncio else None, interval_ms=200)
                    # Mark that we're on home screen
                    if not hasattr(shared_state, '_on_home_screen'):
                        shared_state._on_home_screen = True
                else:
                    # leaving home/menu selection - stop async home updates ONCE
                    if not hasattr(shared_state, '_on_home_screen') or shared_state._on_home_screen:
                        display_manager.stop_home()
                        shared_state._on_home_screen = False
                    
                    # Check if user clicked on profiles screen to load a profile
                    if shared_state.rotary_last_mode == "Profiles" and shared_state.profile_load_pending:
                        if shared_state.profile_list:
                            success, message, needs_reboot = utils.apply_and_save_profile(shared_state.profile_list[shared_state.profile_selection_index], shared_state)
                            if needs_reboot:
                                display_manager.display.fill(0)
                                display_manager.display.text("Hardware changed", 0, 0, 1)
                                display_manager.display.text("Rebooting...", 0, 8, 1)
                                display_manager.display.show()
                                utime.sleep_ms(2000)  # Give time to read the message
                                reset()
                            #display_manager.display_error(message, 2, False)
                        shared_state.profile_load_pending = False
                        # Return to home screen
                        shared_state.current_menu_position = 1
                        shared_state.rotary_last_mode = None
                    # Check if user clicked on autosession profiles screen to load an autosession profile
                    elif shared_state.rotary_last_mode == "Autosession Profiles" and shared_state.autosession_profile_load_pending:
                        if shared_state.autosession_profile_list:
                            success, message = utils.apply_and_save_autosession_profile(shared_state.autosession_profile_list[shared_state.autosession_profile_selection_index], shared_state)
                            #display_manager.display_error(message, 2, False)
                        shared_state.autosession_profile_load_pending = False
                        # Return to home screen
                        shared_state.current_menu_position = 1
                        shared_state.rotary_last_mode = None
                    else:
                        if shared_state.rotary_last_mode != shared_state.menu_options[shared_state.current_menu_position]:
                            input_handler.setup_rotary_values()
                            # Only call display_selected_option when screen actually changes
                            menu_system.display_selected_option()
                        # else: screen hasn't changed, async task is already running and updating display
            else:
                # we're in the menu; ensure async home-screen updates are stopped
                display_manager.stop_home()
                if shared_state.rotary_last_mode != "menu":
                    shared_state.current_menu_position = 0
                    input_handler.setup_rotary_values()
                    # Force an initial menu draw when entering menu
                    try:
                        menu_system.display_menu()
                    except Exception:
                        pass
                if shared_state.menu_selection_pending:
                    menu_system.handle_menu_selection()
                    shared_state.menu_selection_pending = False
                elif shared_state.rotary_direction is not None:
                    menu_system.navigate_menu(shared_state.rotary_direction)
                    shared_state.rotary_direction = None
                else:
                    pass
            
            # LED status updates (safe to always execute)
            if shared_state.heater_temperature is not None and shared_state.heater_temperature >= (shared_state.temperature_setpoint-8) and shared_state.heater_temperature <= (shared_state.temperature_setpoint+8):
                led_red_pin.on()
            else:
                led_red_pin.off()

            # Handle autosession logging start/stop
            if shared_state.autosession_logging_enabled:
                if shared_state.get_mode() == "autosession":
                    # Start logging if not already active
                    if not shared_state.autosession_logging_active:
                        # Ensure any previous buffer is flushed before starting new logging
                        if shared_state.autosession_log_file is not None:
                            utils.flush_autosession_log(shared_state.autosession_log_file, shared_state.autosession_log_buffer)
                        shared_state.autosession_logging_active = True
                        shared_state.autosession_log_file, _ = utils.create_autosession_log_file(shared_state.profile, shared_state.autosession_profile_name)
                        shared_state.autosession_log_buffer = []
                else:
                    # Stop logging if it was active
                    if shared_state.autosession_logging_active:
                        shared_state.autosession_logging_active = False
                        utils.flush_autosession_log(shared_state.autosession_log_file, shared_state.autosession_log_buffer)
                        shared_state.autosession_log_file = None
                        shared_state.autosession_log_buffer = []
            else:
                # If logging is disabled, ensure we stop any active logging
                if shared_state.autosession_logging_active:
                    shared_state.autosession_logging_active = False
                    utils.flush_autosession_log(shared_state.autosession_log_file, shared_state.autosession_log_buffer)
                    shared_state.autosession_log_file = None
                    shared_state.autosession_log_buffer = []

            # PID overshoot prevention logic
            if shared_state.get_mode() == "Session":
                if shared_state.session_timeout is not None and shared_state.session_timeout > 0:
                    remaining_time = shared_state.session_timeout - shared_state.get_session_mode_duration()
                    
                    # Flash blue LED in last 5 seconds
                    if remaining_time <= 5000:
                        # Flash at approximately 250ms intervals (on for 250ms, off for 250ms)
                        flash_interval = 250
                        current_time = utime.ticks_ms()
                        if (current_time // flash_interval) % 2 == 0:
                            led_blue_pin.on()
                        else:
                            led_blue_pin.off()
                    elif remaining_time > 50000 and remaining_time < 60000:
                        led_blue_pin.on()
                    else:
                        led_blue_pin.off()
                else:
                    led_blue_pin.off()

            if shared_state.control == "temperature_pid" or shared_state.control == "autosession":   
                #need to reset pid if big temp change from setpoint too
                if shared_state.heater_temperature > (shared_state.temperature_setpoint + shared_state.pid_reset_high_temperature):
                    shared_state.pid.reset()
                # Prevent overshoot by resetting PID if integral is too high while still far from setpoint
                elif shared_state.heater_temperature >= (shared_state.temperature_setpoint - shared_state.pid_reset_low_temperature) and shared_state.pid.components[1] > shared_state.pid_reset_i_threshold:
                    shared_state.pid.reset()

            if enable_watchdog:
                try:
                    watchdog.feed()
                except Exception:
                    pass
        
        except Exception as e:
            print(f"Error in main loop: {e}")
            # Don't import traceback in MicroPython - it may not be available
            try:
                import sys
                sys.print_exception(e)
            except:
                pass
        
        await asyncio.sleep_ms(70)

if __name__ == '__main__':

    try:
        asyncio.run(async_main())
    except Exception:
        loop = asyncio.get_event_loop()
        loop.create_task(async_main())
        loop.run_forever()



