
import utime
import sys



import machine
from machine import ADC, Pin, I2C, Timer, WDT, PWM

from ssd1306 import SSD1306_I2C

import uasyncio as asyncio

from simple_pid import PID

from customtimer import CustomTimer
from thermocouple import Thermocouple
from displaymanager import DisplayManager
from inputhandler import InputHandler
from menusystem import MenuSystem

from heaters import HeaterFactory, InductionHeater, ElementHeater

from utils import initialize_display, get_input_volts, buzzer_play_tone, get_thermocouple_temperature_or_handle_error, get_pi_temperature_or_handle_error, load_profile, list_profiles, apply_and_save_profile, apply_and_save_autosession_profile, list_autosession_profiles, create_autosession_log_file, log_autosession_data, flush_autosession_log


from shared_state import SharedState


#Need to get input voltage measured so we can possibly set an upper limit 
#eg:
#24v 0.6ohm 40amp 960w  5%-8%  (50-80w)
#12v 0.6ohm 20amp 240w  25-33% (60-80w)
# 9v 0.6ohm 15amp 135w  45-60% (60-80w)
# 6v 0.6ohm 10amp  60w  100%   (60w)


#Note if we can get input voltage for coil then we can possibly set some sensible default for heater_max_duty_cycle_percent
#also choose the correct profile automatically - ie know its battery or mains - get user to confirm  
# - ie to then enable/diable battery check and also et preset pid values for each battery setup type or mains from profile



hardware_pin_red_led = 17   # indicate within 10C of setemp in session mode
hardware_pin_green_led = 18 # indicate heater (manual or session) is activated 
hardware_pin_blue_led = 19  # indicate at start of last minute of a session

hardware_pin_display_scl = 21
hardware_pin_display_sda = 20

hardware_pin_buzzer = 16

hardware_pin_rotary_clk = 13
hardware_pin_rotary_dt = 12
hardware_pin_button = 14  #can also be a separate button as well as rotary push/sw pin 

hardware_pin_switch_left = 23    #down 
hardware_pin_switch_middle = 24  #select  - on boot hold to disable watchdog
hardware_pin_switch_right = 25   #up

hardware_pin_termocouple_sck = 6
hardware_pin_termocouple_cs = 7 
hardware_pin_termocouple_so = 8

hardware_pin_heater = 22



####################################





def timerSetPiTemp(t):
    global pi_temperature_sensor, pidTimer, display_manager, heater, shared_state
   
    shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor,display_manager,shared_state)
    
    # Check if the temperature is safe
    if shared_state.pi_temperature > shared_state.pi_temperature_limit:
        try:
            if not pidTimer.is_timer_running: pidTimer.stop() 
            heater.off()
            error_text = shared_state.error_messages.get("pi-too_hot", "PI too hot")
            shared_state.set_error("pi-too_hot", error_text)
            while not shared_state.pi_temperature <= shared_state.pi_temperature_limit:
                shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor,display_manager,shared_state)
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
        new_heater_temperature, need_heater_off_temperature = get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state)
    else:
        new_heater_temperature = 0
        need_heater_off_temperature = False

    if new_heater_temperature < 0: # Non fatal error occured 
        heater.off() #should already be off
        return   # Let timer run this again and hopefully next time error has passed

    # new temperature is valid
    shared_state.heater_temperature = new_heater_temperature
    
    shared_state.input_volts = get_input_volts(shared_state.input_volts)

    #shared_state.heater_max_duty_cycle_percent - need to update this now and adjust to MAX WATTS (add to shared state)
    if shared_state.input_volts > 0:
        shared_state.heater_max_duty_cycle_percent = (shared_state.temp_max_watts / (shared_state.input_volts * shared_state.input_volts / shared_state.heater_resistance)) * 100  
    else:
        shared_state.heater_max_duty_cycle_percent = 100
        
    if shared_state.heater_max_duty_cycle_percent > 100:
        shared_state.heater_max_duty_cycle_percent = 100
    heater.set_max_duty_cycle(shared_state.heater_max_duty_cycle_percent)
    
    if need_heater_off_temperature:
        heater.off()
        print("Getting safe off heater temperature")
        utime.sleep_ms(301) # lets give everything a moment to calm down
        new_heater_temperature, _ = get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state)
        if new_heater_temperature < 0: # Non fatal error occured 
            return   # Let timer run this again and hopefully next time error has passed
        # new off temperature is valid
        shared_state.heater_temperature = new_heater_temperature

    if len(shared_state.temperature_readings) >= 128: 
        oldest_time = min(shared_state.temperature_readings.keys())
        del shared_state.temperature_readings[oldest_time]
    shared_state.temperature_readings[utime.ticks_ms()] = int(shared_state.heater_temperature)
    
    # Cache min/max for display optimization
    if shared_state.temperature_readings:
        shared_state.temperature_min_time = min(shared_state.temperature_readings.keys())
        shared_state.temperature_max_time = max(shared_state.temperature_readings.keys())

    if len(shared_state.input_volts_readings) >= 128: 
        oldest_time = min(shared_state.input_volts_readings.keys())
        del shared_state.input_volts_readings[oldest_time]
    shared_state.input_volts_readings[utime.ticks_ms()] = shared_state.input_volts



    if len(shared_state.watt_readings) >= 128: 
        oldest_time = min(shared_state.watt_readings.keys())
        del shared_state.watt_readings[oldest_time]
    
    if heater.is_on():
        # Calculate actual watts from voltage, resistance, and actual duty cycle
        # Don't use heater_max_duty_cycle_percent as that's a safety limit, not the actual power
        shared_state.watts = int((((shared_state.input_volts*shared_state.input_volts) / shared_state.heater_resistance) * (heater.get_power() / 100)))
        shared_state.watt_readings[utime.ticks_ms()] = shared_state.watts
    else:
        shared_state.watts = 0
        shared_state.watt_readings[utime.ticks_ms()] = 0
    
    # Cache min/max for display optimization
    if shared_state.watt_readings:
        shared_state.watt_min_time = min(shared_state.watt_readings.keys())
        shared_state.watt_max_time = max(shared_state.watt_readings.keys())

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
        power = shared_state.pid(shared_state.heater_temperature)  # Update pid even if heater is off
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
        shared_state.autosession_log_buffer, shared_state.autosession_log_file = log_autosession_data(
            shared_state.autosession_log_file,
            shared_state.autosession_log_buffer,
            elapsed_ms,
            shared_state.heater_temperature,
            shared_state.temperature_setpoint,
            shared_state.input_volts,
            heater.get_power(),
            shared_state.watts,
            shared_state.autosession_log_buffer_flush_threshold
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

#Maybe still add an external led - colour one perhaps to indicate above/below/on temp to see from a distance?
#make special colour for manual vs session?
#also add buzzer to sound when session about to end as you dont notice 
#maybe different buzz when first reaches setopoint that session 


print("Display Initialising ...")
display = initialize_display(hardware_pin_display_scl, hardware_pin_display_sda, led_red_pin)
print("Display initialised.")

shared_state = SharedState(led_red_pin=led_red_pin, led_green_pin=led_green_pin, led_blue_pin=led_blue_pin)

# Load profile list at startup (like show_settings loads all settings once)



# Load normal profiles list
shared_state.profile_list = list_profiles()
shared_state.profile_selection_index = 0

# Load autosession profiles list (do not load profile itself)
shared_state.autosession_profile_list = list_autosession_profiles()
shared_state.autosession_profile_selection_index = 0


# Load saved default profile if it exists
try:
    with open('/current_profile.txt', 'r') as f:
        profile_name = f.readline().strip()
    if profile_name:
        print(f"Loading profile: {profile_name}")
        config = load_profile(profile_name, shared_state)
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
    success, message = apply_and_save_autosession_profile(shared_state.default_autosession_profile, shared_state)
    print(message)
else:
    # Fall back to current_autosession_profile.txt if no default in profile
    try:
        with open('/current_autosession_profile.txt', 'r') as f:
            autosession_profile_name = f.readline().strip()
        if autosession_profile_name:
            print(f"Loading autosession profile: {autosession_profile_name}")
            success, message = apply_and_save_autosession_profile(autosession_profile_name, shared_state)
            print(message)
        else:
            print("No autosession profile name found in /current_autosession_profile.txt")
    except OSError:
        print("No /current_autosession_profile.txt found, skipping autosession profile load")

#config = load_config(display)  # need to get config before displaymanager setup perhaps? so if error still need to show user
#shared_state = SharedState(config)
 



# DisplayManager
try:
    display_manager = DisplayManager(display, shared_state)
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
buzzer_play_tone(buzzer, 2500, 200)  # Play a sound so we know its connected correctly
print("Buzzer initialised.")


#button_pin = Pin(hardware_pin_button, Pin.IN)
button_pin = Pin(hardware_pin_switch_middle, Pin.IN, Pin.PULL_UP)
print(button_pin.value())
if button_pin.value():
    enable_watchdog = True
                            
    print("Watchdog: On")
else:
    enable_watchdog = False
    utime.sleep_ms(150)
    buzzer_play_tone(buzzer, 2000, 250)
    utime.sleep_ms(150)
    buzzer_play_tone(buzzer, 1000, 250)
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
shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor, display_manager, shared_state)


# InputHandler
input_handler = InputHandler(rotary_clk_pin=hardware_pin_rotary_clk, rotary_dt_pin=hardware_pin_rotary_dt, button_pin=hardware_pin_button, switch_control_pin=hardware_pin_switch_left, middle_button_pin=hardware_pin_switch_middle, shared_state=shared_state)

# MenuSystem
menu_system = MenuSystem(display_manager, shared_state)


# PID


#read before trying to tune: http://brettbeauregard.com/blog/2017/06/introducing-proportional-on-measurement/
#pid.differential_on_measurement = True   #Either this or the below not both - this is the default for PID
#pid.proportional_on_measurement = True   #Seems to be a bit odd


while shared_state.input_volts is False:
    shared_state.input_volts = get_input_volts(False)
    utime.sleep_ms(50)

#lets do some sanity checks on power level 
#warn user if high but still not ridiculous
#reduce if too high to more sensible level

# InductionHeater

#ihTimer = Timer(-1) # need to replace with CustomTimer 
#heater = HeaterFactory.create_heater('induction', coil_pins=(12, 13), timer=ihTimer)

heater = HeaterFactory.create_heater('element', hardware_pin_heater)   # changing the limit will mess with PID tuning

#heater = HeaterFactory.create_heater('element', hardware_pin_heater) # no limit
#heater = HeaterFactory.create_heater('element', hardware_pin_heater, 100) # no limit


heater.off()


pidTimer = CustomTimer(371, machine.Timer.PERIODIC, timerUpdatePIDandHeater)  # need to have timer setup before calling below 
shared_state.heater_temperature, _ = get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state)


print("Timers Initialising ...")
# Do not start timers here; they'll be started when the asyncio loop is running
# pidTimer.start()
# pid.reset()

piTempTimer = CustomTimer(903, machine.Timer.PERIODIC, timerSetPiTemp)



print("Timers initialised.")



# start up stuff done
############### 


# After heater is initialized and before entering the event loop, start the home screen
display_manager.start_home(heater, loop=asyncio.get_event_loop(), interval_ms=200)



# Lets enable and see if it helps when heater on and we crash
# So far from simulated tests this seems to work and heater pin is reset

#enable_watchdog = False
if enable_watchdog: 
    watchdog = machine.WDT(timeout=(1000 * 3)) 
    print("Watchdog enabled")



start_time = utime.ticks_ms()
iteration_count = 0
refresh_rate = 0

# Sort of a load average 
#start_times = [utime.ticks_ms(), utime.ticks_ms(), utime.ticks_ms()] 
#iteration_counts = [0, 0, 0] 
#period_durations = [1000, 10000, 30000]


async def async_main():
    # Start periodic timers now that (optionally) the asyncio loop is running.
    try:
        pidTimer.start()
        shared_state.pid.reset()
    except Exception:
        pass
    try:
        piTempTimer.start()
    except Exception:
        pass

    # Start display heartbeat as a background task if available
    if hasattr(display_manager, 'start_heartbeat') and asyncio:
        try:
            display_manager.start_heartbeat(loop=asyncio.get_event_loop(), interval_ms=70)
        except Exception:
            try:
                display_manager.start_heartbeat(interval_ms=70)
            except Exception:
                pass

    display_manager.show_startup_screen()

    while True:
        # Check and display any active errors
        if shared_state.has_error():
            display_manager.show_error()
        # Check if user clicked middle button to show temp_max_watts screen
        elif shared_state.middle_button_pressed:
            display_manager.stop_home()
            shared_state.in_menu = False  # Make sure we exit menu mode
            shared_state.temp_max_watts_screen_active = True
            shared_state.temp_max_watts_start_time = utime.ticks_ms()
            shared_state.rotary_last_mode = None  # Reset so setup_rotary_values sets it to "Temp Max Watts"
            input_handler.setup_rotary_values()
            display_manager.show_screen_temp_max_watts()
            shared_state.middle_button_pressed = False
        # Handle temp_max_watts screen display with timeout
        elif shared_state.temp_max_watts_screen_active:
            # Check if timeout has elapsed (2 seconds with no rotary activity)
            elapsed = utime.ticks_diff(utime.ticks_ms(), shared_state.temp_max_watts_start_time)
            if elapsed >= 2000:
                # Timeout - return to home screen
                shared_state.temp_max_watts_screen_active = False
                shared_state.rotary_last_mode = None
                shared_state.current_menu_position = 1
            else:
                # Still displaying - update the screen
                display_manager.show_screen_temp_max_watts()
        elif not shared_state.in_menu:
            if shared_state.current_menu_position <= 1:
                # ensure rotary values set once (but not if temp_max_watts screen is active)
                # Also ensure rotary is reconfigured when autosession starts/stops
                # Don't reconfigure if we're already in autosession mode with rotary set to autosession
                if (shared_state.rotary_last_mode != "setpoint" and shared_state.rotary_last_mode != "autosession" and not shared_state.temp_max_watts_screen_active) or \
                   (shared_state.get_mode() == "autosession" and shared_state.rotary_last_mode != "autosession"):
                    input_handler.setup_rotary_values()
                shared_state.current_menu_position = 1
                # start async home-screen updater (no-op if already running)
                display_manager.start_home(heater, loop=asyncio.get_event_loop() if asyncio else None, interval_ms=200)
            else:
                # leaving home/menu selection - stop async home updates
                display_manager.stop_home()
                
                # Check if user clicked on profiles screen to load a profile
                if shared_state.rotary_last_mode == "Profiles" and shared_state.profile_load_pending:
                    if shared_state.profile_list:
                        success, message = apply_and_save_profile(shared_state.profile_list[shared_state.profile_selection_index], shared_state)
                        #display_manager.display_error(message, 2, False)
                    shared_state.profile_load_pending = False
                    # Return to home screen
                    shared_state.current_menu_position = 1
                    shared_state.rotary_last_mode = None
                # Check if user clicked on autosession profiles screen to load an autosession profile
                elif shared_state.rotary_last_mode == "Autosession Profiles" and shared_state.autosession_profile_load_pending:
                    if shared_state.autosession_profile_list:
                        success, message = apply_and_save_autosession_profile(shared_state.autosession_profile_list[shared_state.autosession_profile_selection_index], shared_state)
                        #display_manager.display_error(message, 2, False)
                    shared_state.autosession_profile_load_pending = False
                    # Return to home screen
                    shared_state.current_menu_position = 1
                    shared_state.rotary_last_mode = None
                else:
                    if shared_state.rotary_last_mode != shared_state.menu_options[shared_state.current_menu_position]:
                        input_handler.setup_rotary_values()
                    menu_system.display_selected_option()
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
        #Need to make '8' in shared state so can be set via profile
        if shared_state.heater_temperature >= (shared_state.temperature_setpoint-8) and shared_state.heater_temperature <= (shared_state.temperature_setpoint+8):
            led_red_pin.on()
        else:
            led_red_pin.off()

        # Handle autosession logging start/stop
        if shared_state.autosession_logging_enabled:
            if shared_state.get_mode() == "autosession":
                # Start logging if not already active
                if not shared_state.autosession_logging_active:
                    shared_state.autosession_logging_active = True
                    shared_state.autosession_log_file, _ = create_autosession_log_file(shared_state.profile, shared_state.autosession_profile_name)
                    shared_state.autosession_log_buffer = []
            else:
                # Stop logging if it was active
                if shared_state.autosession_logging_active:
                    shared_state.autosession_logging_active = False
                    flush_autosession_log(shared_state.autosession_log_file, shared_state.autosession_log_buffer)
                    shared_state.autosession_log_file = None
                    shared_state.autosession_log_buffer = []
        else:
            # If logging is disabled, ensure we stop any active logging
            if shared_state.autosession_logging_active:
                shared_state.autosession_logging_active = False
                flush_autosession_log(shared_state.autosession_log_file, shared_state.autosession_log_buffer)
                shared_state.autosession_log_file = None
                shared_state.autosession_log_buffer = []


        if shared_state.get_mode() == "Session":
            if (shared_state.session_timeout - shared_state.get_session_mode_duration()) > 50000 and (shared_state.session_timeout - shared_state.get_session_mode_duration()) < 60000:
                led_blue_pin.on()
            else:
                led_blue_pin.off()
            # Only check setpoint reached in temperature-PID mode
            if shared_state.control == 'temperature_pid':
                if shared_state.session_setpoint_reached == False:
                    if shared_state.heater_temperature >= (shared_state.temperature_setpoint-8):
                        shared_state.session_setpoint_reached = True
                        buzzer_play_tone(buzzer, 1500, 350)
                        if shared_state.session_reset_pid_when_near_setpoint:
                            shared_state.pid.reset()
                    # Prevent overshoot by resetting PID if integral is too high while still far from setpoint
                    #elif shared_state.heater_temperature >= (shared_state.temperature_setpoint - 10) and shared_state.pid.components[1] > 10:
                    #    shared_state.pid.reset()
                else:
                    #Need to make '15' in shared state so can be set via profile
                    #If reached setpoint and then temperature drops dramatically Integral can increase to much 
                    #need to catch runaway temp here after we have already reached setpointand reset pid stats 
                    if shared_state.heater_temperature > (shared_state.temperature_setpoint + shared_state.pid_reset_high_temperature):
                        shared_state.pid.reset()
        elif shared_state.get_mode() == "autosession":
            #need to reset pid if big temp change from setpoint too
            if shared_state.heater_temperature > (shared_state.temperature_setpoint + shared_state.pid_reset_high_temperature):
                shared_state.pid.reset()
            # Prevent overshoot by resetting PID if integral is too high while still far from setpoint
            elif shared_state.heater_temperature >= (shared_state.temperature_setpoint - 10) and shared_state.pid.components[1] > 10:
                shared_state.pid.reset()

        if enable_watchdog:
            try:
                watchdog.feed()
            except Exception:
                pass
        await asyncio.sleep_ms(70)

if __name__ == '__main__':

    try:
        asyncio.run(async_main())
    except Exception:
        loop = asyncio.get_event_loop()
        loop.create_task(async_main())
        loop.run_forever()



