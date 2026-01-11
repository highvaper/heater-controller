
import utime
import sys



import machine
from machine import ADC, Pin, I2C, Timer, WDT, PWM

from ssd1306 import SSD1306_I2C

import uasyncio as asyncio

from simple_pid import PID

from errormessage import ErrorMessage
from customtimer import CustomTimer
from thermocouple import Thermocouple
from displaymanager import DisplayManager
from inputhandler import InputHandler
from menusystem import MenuSystem

from heaters import HeaterFactory, InductionHeater, ElementHeater

from utils import initialize_display, get_input_volts, buzzer_play_tone, get_thermocouple_temperature_or_handle_error, get_pi_temperature_or_handle_error, load_profile, list_profiles, apply_and_save_profile


from shared_state import SharedState

#pid_tunings = 0.48, 0.004, 0   #18mm + nichrome 2mm
#pid_tunings = 0.29, 0.0008, 0   #18mm + nichrome 3mm - 60% limit
#pid_tunings = 0.33, 0.0011, 0   #20mm + nichrome 3mm - 70% limit

#pid_tunings = 0.27, 0.00065, 0   #new heater + 6 coil + nichrome 4mm approx 0.7 ohms - 40% pwm limit - 73 watts meeasured 



#pid_tunings = 0.27, 0.00065, 0   #new heater + 6 coil + nichrome 4mm approx 0.7 ohms - 30% pwm limit - 57 watts meeasured 
#pid_tunings = 0.28, 0.0008, 0   #new heater + 6 coil + nichrome 4mm approx 0.7 ohms - 25% pwm limit - 47 watts meeasured 


#pid_tunings = 2.3, 0.03, 0   #new heater + 6 coil + nichrome 4mm approx 0.6 ohms - with 2 x lipo batteries


#add option for PWM mode so dial sets duty %  and ignore pid/temp (up to 300?) and just go in manual mode - show watts as we can work it out

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
   
    shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor,display_manager)
    
    # Check if the temperature is safe
    if shared_state.pi_temperature > shared_state.pi_temperature_limit:
        try:
            if not pidTimer.is_timer_running: pidTimer.stop() 
            heater.off()
            while not shared_state.pi_temperature <= shared_state.pi_temperature_limit:
                display_manager.display_error("pi-too_hot", 5) # Move display out of here?
                
                shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor,display_manager)
                utime.sleep_ms(250)  # Warning shown for 5 secs so has had a time to cool down a bit

            pidTimer.start()
        except Exception as e:
            heater.off()
            print("Error updating display or deinitializing timers:", e)
            # dont feed watchdog let it reboot
    else:
        if not pidTimer.is_timer_running: pidTimer.start()


def timerUpdatePIDandHeater(t):  #nmay replace what this does in the check termocouple function 
                                 #this needs a major clear up now we have share_state 
    global heater, thermocouple

    if shared_state.pid.setpoint != shared_state.temperature_setpoint:
        shared_state.pid.setpoint = shared_state.temperature_setpoint
    
    new_heater_temperature, need_heater_off_temperature = get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager)

    if new_heater_temperature < 0: # Non fatal error occured 
        heater.off() #should already be off
        return   # Let timer run this again and hopefully next time error has passed

    # new temperature is valid
    shared_state.heater_temperature = new_heater_temperature
    
    shared_state.input_volts = get_input_volts(shared_state.input_volts)

    #shared_state.heater_max_duty_cycle_percent - need to update this now and adjust to MAX WATTS (add to shared state)
    if shared_state.input_volts > 0:
        shared_state.heater_max_duty_cycle_percent = (shared_state.max_watts / (shared_state.input_volts * shared_state.input_volts / shared_state.heater_resistance)) * 100  
    else:
        shared_state.heater_max_duty_cycle_percent = 100
        
    if shared_state.heater_max_duty_cycle_percent > 100:
        shared_state.heater_max_duty_cycle_percent = 100
    heater.set_max_duty_cycle(shared_state.heater_max_duty_cycle_percent)
    
    if need_heater_off_temperature:
        heater.off()
        print("Getting safe off heater temperature")
        utime.sleep_ms(301) # lets give everything a moment to calm down
        new_heater_temperature, _ = get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager)
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

    if shared_state.control == 'temperature_pid': 
        power = shared_state.pid(shared_state.heater_temperature)  # Update pid even if heater is off
    elif shared_state.control == 'duty_cycle':
        power = shared_state.set_duty_cycle  # Use duty cycle directly (0-100%)
    else:
        # In watts mode, calculate duty cycle needed to produce desired watts at current voltage
        # watts = (V^2 / R) * (duty% / 100)
        # duty% = (watts * R / V^2) * 100
        if shared_state.input_volts > 0:
            power = (shared_state.setwatts * shared_state.heater_resistance / (shared_state.input_volts * shared_state.input_volts)) * 100
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
            display_manager.display_error("battery_level-too-low",10,True)
    elif shared_state.power_type == 'lead':
        if shared_state.input_volts  < shared_state.lead_safe_volts:
            heater.off()
            shared_state.set_mode("Off")
            display_manager.display_error("battery_level-too-low",10,True)
    elif shared_state.power_type == 'mains':
        if shared_state.input_volts > shared_state.mains_safe_volts:
            heater.off()
            shared_state.set_mode("Off")
            display_manager.display_error("mains-voltage-too-high",10,True)
    else:
        heater.off()
        shared_state.set_mode("Off")
        display_manager.display_error("unknown-power-type",10,True)    
   
        
    if power > shared_state.power_threshold:
        # Temperature over-limit protection with hysteresis
        if shared_state.heater_temperature > 245:
            shared_state.heater_too_hot = True
        elif shared_state.heater_temperature < 230:  # Hysteresis threshold
            shared_state.heater_too_hot = False
        
        if shared_state.heater_too_hot:
            # Ensure heater is OFF before showing error
            heater.set_power(0)
            heater.off()
            error_text = "Pausing heater - " + shared_state.error_messages["heater-too_hot"] + " " + str(shared_state.heater_temperature)
            print(error_text)
            # Only display error once, not repeatedly every cycle
            if not hasattr(shared_state, '_error_displayed') or not shared_state._error_displayed:
                display_manager.display_error("heater-too_hot", 10, True)
                shared_state._error_displayed = True
        else:
            # Temperature is safe, clear error flag
            shared_state._error_displayed = False
            # Only turn heater back on if we were trying to heat
            if not heater.is_on():
                if shared_state.get_mode() != "Off":
                    heater.on(power)
            # Set power only when temperature is safe
            if isinstance(heater, ElementHeater):
                heater.set_power(power)
    else:
        heater.off()  #Maybe we call this no matter what just in case?
    
 #   t = ','.join(map(str, [pid._last_time, shared_state.heater_temperature, thermocouple.raw_temp, pid.setpoint, power, heater.is_on(), pid.components]))
 #   print(t)








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
shared_state.profile_list = list_profiles()
shared_state.profile_selection_index = 0

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

# Initialize termocouple before switching on induction heater
try:
    utime.sleep_ms(700)
    thermocouple = Thermocouple(hardware_pin_termocouple_sck, hardware_pin_termocouple_cs, hardware_pin_termocouple_so, shared_state.heater_on_temperature_difference_threshold)
    utime.sleep_ms(350)
    _, _ = thermocouple.get_filtered_temp(False)  # Sets: last_known_safe_temp - Do here rather than in class as it sometimes returns error if on class init 
except Exception as e:
    error_text = "Start up failed: " + str(e)
    print(error_text)
    while True:
        try:
            # Use blocking draw so message appears before asyncio loop starts
            display_manager.fill_display("thermocouple-setup", 0, 12)
        except Exception:
            try:
                # Fallback to raw display if DisplayManager isn't available
                display.fill(0)
                display.text("thermocouple-setup", 0, 12, 1)
                display.show()
            except Exception:
                pass
        utime.sleep_ms(500)
    sys.exit() #?




# PI Temperature Sensor 
pi_temperature_sensor = machine.ADC(4)
shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor, display_manager)


# InputHandler
input_handler = InputHandler(rotary_clk_pin=hardware_pin_rotary_clk, rotary_dt_pin=hardware_pin_rotary_dt, button_pin=hardware_pin_button, switch_control_pin=hardware_pin_switch_left, shared_state=shared_state)

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
shared_state.heater_temperature, _ = get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager)


print("Timers Initialising ...")
# Do not start timers here; they'll be started when the asyncio loop is running
# pidTimer.start()
# pid.reset()

piTempTimer = CustomTimer(903, machine.Timer.PERIODIC, timerSetPiTemp)



print("Timers initialised.")



# start up stuff done
############### 



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

    # Show startup screen asynchronously if possible
    try:
        display_manager.show_startup_screen()
    except Exception:
        pass

    while True:
        if not shared_state.in_menu:
            if shared_state.current_menu_position <= 1:
                # ensure rotary values set once
                if shared_state.rotary_last_mode != "setpoint":
                    input_handler.setup_rotary_values()
                shared_state.current_menu_position = 1
                # start async home-screen updater (no-op if already running)
                display_manager.start_home(lambda: shared_state.pid.components, heater, loop=asyncio.get_event_loop() if asyncio else None, interval_ms=200)
            else:
                # leaving home/menu selection - stop async home updates
                display_manager.stop_home()
                
                # Check if user clicked on profiles screen to load a profile
                if shared_state.rotary_last_mode == "Profiles" and shared_state.profile_load_pending:
                    if shared_state.profile_list:
                        profile_name = shared_state.profile_list[shared_state.profile_selection_index]
                        success, message = apply_and_save_profile(profile_name, shared_state)
                        #display_manager.display_error(message, 2, False)
                    shared_state.profile_load_pending = False
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
                else:
                    #Need to make '15' in shared state so can be set via profile
                    #need to catch runaway temp here after we have already reached setpointand reset pid stats 
                    if shared_state.heater_temperature > (shared_state.temperature_setpoint + 15):
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



