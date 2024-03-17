import utime
import sys
from machine import ADC, Pin, I2C, Timer, WDT
from ssd1306 import SSD1306_I2C

from simple_pid import PID

from errormessage import ErrorMessage
from customtimer import CustomTimer
from thermocouple import Thermocouple
from displaymanager import DisplayManager
from inputhandler import InputHandler
from menusystem import MenuSystem

#from inductionheater import InductionHeater
from heaters import HeaterFactory, InductionHeater, ElementHeater


#to kill?
#import onewire, ds18x20

####################################

# Format:  main_system-error_code

MAIN_ERROR_MESSAGES = {"display-setup":      "Error initializing display, cannout continue",
                       "heater-too_hot":     "Induction heater too hot > 300C",
                       "pi-too_hot":         "PI too hot > 60C"
}

def load_config(file_path='config.txt'):
    config = {}
    try:
        with open(file_path, 'r') as file:
            for line in file:
                if line.strip() and not line.startswith('#'): # Ignore empty lines and comments
                    key, value = line.strip().split('=')
                    if key == 'session_timeout':
                        config['session_timeout'] = int(value) * 1000 # Convert to milliseconds
                    elif key == 'temperature_units':
                        config['temperature_units'] = value
                    elif key == 'setpoint':
                        config['setpoint'] = int(value)
                    elif key == 'power_threshold':
                        config['power_threshold'] = int(value)
                    elif key == 'heater_on_temperature_difference_threshold':
                        config['heater_on_temperature_difference_threshold'] = int(value)
                    # Add more elif statements for other configuration settings
    except OSError as e:
        print("Error opening or reading config file:", e)
    return config


def get_pi_temperature_or_handle_error(pi_temperature_sensor):
    try:
        ADC_voltage = pi_temperature_sensor.read_u16() * (3.3 / (65536))
        pi_temperature = 27 - (ADC_voltage - 0.706) / 0.001721
        return pi_temperature
    except Exception as e:
        error_message = str(e)
        print("Error reading PI temperature: " + error_message)
        display_manager.display_error("pi-unknown_error", "Error reading PI temperature: " + error_message,10,True) # need to move out of this?
        #while True:
         #   utime.sleep_ms(1000)
    return pi_temperature

def get_thermocouple_temperature_or_handle_error(thermocouple, heater):
    try:

        if isinstance(heater, InductionHeater):
            new_temperature, need_off_temperature = thermocouple.get_filtered_temp(heater.is_on())
        elif isinstance(heater, ElementHeater):
            new_temperature = thermocouple.read_raw_temp()
            need_off_temperature = False  # caller can throw this away if not needed
        else:
            raise ValueError("Unsupported heater type")
        return new_temperature, need_off_temperature
    
    except ErrorMessage as e:
        error_message = str(e)
        error_code = e.error_code
        if error_code in ["thermocouple-invalid_reading",
                          "thermocouple-zero_reading", 
                          "thermocouple-below_zero"]:
            heater.off()
            if pidTimer.is_timer_running(): pidTimer.stop() # Maybe stop other timers?
            print("Stopped heater - [" + error_code + "] " + error_message)
            while True:
                display_manager.display_error(error_code, "Stopped heater - " + error_message)  # need to move out of this?
                utime.sleep_ms(500)
        else:
            #thermocouple-above_limit, thermocouple-read_error
            heater.off()
            print("Pausing heater - [" + error_code + "] " + error_message)
            #display_manager.display_error(error_code, "Pausing heater - " + error_message,10,True)  # need to move out of this?
            return -1, True
    
    except Exception as e:
        # Handle or log unexpected exceptions not dealt with above
        error_message = str(e)
        heater.off()
        if pidTimer.is_timer_running(): pidTimer.stop() 
        print("Stopped heater - Unknown Error: " + error_message)
        while True:
            display_manager.display_error("unknown_error","Stopped heater - Unknown Error: " + error_message)
            utime.sleep_ms(500)

def initialize_display(i2c_scl, i2c_sda, led_pin):
 
    try:
        i2c = I2C(0, scl=Pin(i2c_scl), sda=Pin(i2c_sda), freq=200000)
        display = SSD1306_I2C(128, 32, i2c)
    except Exception as e:
        error_text = "Start up failed - [display-setup] " + MAIN_ERROR_MESSAGES["display-setup"] + " " + str(e)
        print(error_text)
        while True:
            # We could so a special lookup for each error type for the display and morse code it out?
            # For time being 3 on/off in short time with a pause and then repeating is enough to notify 
            # about a display issue
            led_pin.on()
            utime.sleep_ms(200)
            led_pin.off()
            utime.sleep_ms(200)
            led_pin.on()
            utime.sleep_ms(200)
            led_pin.off()
            utime.sleep_ms(200)
            led_pin.on()
            utime.sleep_ms(200)
            led_pin.off()
            utime.sleep_ms(1000)
        sys.exit()

    return display



def timerSetPiTemp(t):
    global pi_temperature_sensor, pidTimer, display_manager, heater, shared_state

#    if shared_state.in_menu:   # Not sure we want to return and maybe still do this
#        return
    
    shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor)
    
    # Check if the temperature is safe
    if shared_state.pi_temperature > shared_state.pi_temperature_limit:
        try:
            if not pidTimer.is_timer_running: pidTimer.stop() 
            heater.off()
            while not shared_state.pi_temperature <= shared_state.pi_temperature_limit:
                display_manager.display_error("pi-too_hot", MAIN_ERROR_MESSAGES["pi-too_hot"] + " " + str(pi_temperature) + "C", 5) # Move display out of here?
                
                shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor)
                utime.sleep_ms(250)  # Warning shown for 5 secs so has had a time to cool down a bit

            pidTimer.start()
        except Exception as e:
            heater.off()
            print("Error updating display or deinitializing timers:", e)
            # dont feed watchdog when we implement it let it crash now
    else:
        if not pidTimer.is_timer_running: pidTimer.start()


def timerUpdatePIDandHeater(t):  #nmay replace what this does in the check termocouple function 
                                 #this needs a major clear up now we have share_state 
    global pid, heater, thermocouple

    if pid.setpoint != shared_state.setpoint: pid.setpoint = shared_state.setpoint
    
    new_heater_temperature, need_heater_off_temperature = get_thermocouple_temperature_or_handle_error(thermocouple, heater)

    if new_heater_temperature < 0: # Non fatal error occured 
        heater.off() #should already be off
        return   # Let timer run this again and hopefully next time error has passed

    # new temperature is valid
    shared_state.heater_temperature = new_heater_temperature
    
    if need_heater_off_temperature:
        heater.off()
        print("Getting safe off heater temperature")
        utime.sleep_ms(301) # lets give everything a moment to calm down
        new_heater_temperature, _ = get_thermocouple_temperature_or_handle_error(thermocouple, heater)
        if new_heater_temperature < 0: # Non fatal error occured 
            return   # Let timer run this again and hopefully next time error has passed
        # new off temperature is valid
        shared_state.heater_temperature = new_heater_temperature

    if len(shared_state.temperature_readings) >= 128:
        oldest_time = min(shared_state.temperature_readings.keys())
        del shared_state.temperature_readings[oldest_time]
    shared_state.temperature_readings[utime.ticks_ms()] = int(shared_state.heater_temperature)

    power = pid(shared_state.heater_temperature)  # Update let pid update even if heater is off

    if shared_state.get_mode() == "Off": 
        heater.off()
        return
    
    if power > shared_state.power_threshold:
        if abs(shared_state.heater_temperature) > 350:  # Hard coded limit if user really wants to up this then up to them to edit code
            if heater.is_on():
                heater.off()
            error_text = "Pausing heater - " + MAIN_ERROR_MESSAGES["heater-too_hot"] + " " + str(shared_state.heater_temperature)
            print(error_text)
            display_manager.display_error("heater-too_hot",error_text,10,True)

        elif not heater.is_on():
            if shared_state.get_mode() != "Off":
                heater.on()
    else:
        if heater.is_on():
            heater.off()  #Maybe we call this no matter what just in case?
    
    t = ','.join(map(str, [pid._last_time, shared_state.heater_temperature, thermocouple.raw_temp, pid.setpoint, power, heater.is_on(), pid.components]))
#    print(t)



class SharedState:
    def __init__(self):
    
        # All of the below hard coded can be loaded from a file or similar 
        # Need to add other stuff like butto click time, max temp, etc
        
        self.session_timeout = 180 * 1000   # length of time for a session before auto off (3 mins)
        self.temperature_units = 'C'       # Not tested F at all 

        self.setpoint = 30     # Initial PID setpoint 

        #self.power_threshold = 5  #between pid.output_limits range (1-10)
        self.power_threshold = 1 #for slower sensors like DS18X20 probally lower is better

        # for the filtered tempterature when induction is on 
        # possibly needs adjusting for different coil sizes/current/voltages - 
        # maybe need way to reset this in the termocouple class if loading setting between reboots?
        # calibrate by placeing thermopile in induction coil and seeing effects on readings when on / off 
        # dont set this too low 
        self.heater_on_temperature_difference_threshold = 20 

        self.display_contrast = 255   # allow change by option in menu

        # Below is stuff perhaps better to leave alone
        self.click_check_timeout = 800 # ms timeout to multi click in 
        self.max_allowed_setpoint = 299 # max allowed temperature
        

        # below are controlled by internal processes dont mess with 
        #self.temperature_readings =  {i: 20 for i in range(128)}
        self.temperature_readings =  {}
        
        self.heater_temperature = 0  # Overal induction heater temperature from thermocouple at the moment only deals with one 
                                 # possibly extend to deal with multpile but not to start with
        
        self.pi_temperature = 0         # PI Pico chip temperature
        self.pi_temperature_limit = 60


        self.menu_options = ["MENU",
                             "Home Screen",
                             "Graph Setpoint",
                             "Graph Line",
                             "Graph Bar",
                             "PI Temperature",
                             "Display Contrast"
                            ]
                            
        self.in_menu = False  # need to add get/set fnctions? 
        self.current_menu_position = 1 # need to add get/set functions? - dont let get more than one or count of options -1
        self.menu_selection_pending = False 
        self.menu_timeout = 3 * 1000   # 3 secs
        
        self.rotary_direction = None
        self.rotary_last_mode = None

        self.session_start_time = 0
        self._mode = "Off" 


    def get_mode(self):
        if self._mode == "Session" and (self.session_timeout - self.get_session_mode_duration()) < 0:
            session_start_time = 0
            led_pin.off()
            self._mode = "Off"
        return self._mode

    def set_mode(self, new_mode):
        if new_mode in ["Off", "Manual"]:
            if self._mode == "Session": self.session_start_time = 0
            self._mode = new_mode
        elif new_mode == "Session":
            self.session_start_time = utime.ticks_ms()
            self._mode = "Session"
        else:
            raise ValueError("Invalid mode. Must be 'Off', 'Session' or 'Manual'")
        if new_mode == "Off":
            led_pin.off()
        else:
            led_pin.on()
            
    def get_session_mode_duration(self):
        return utime.ticks_diff(utime.ticks_ms(), self.session_start_time)





###############################################################
#
# Initialisation 
#
# The led should blink brielfly before the display powers up 
# if no led blink we have a problem but do not think there is a 
# way to know so user needs to be aware that it should blink once breifly
# 
# If there is an issue with the display setup then the led will flash 3 times 
# and switch off for about a second and repeat the flashing and off.
#
# Other errors should be reported on the screen as it should now be avaliable
#
###############################################################



# Lets get most basic way to indicate there is an issue to the user 
# if this doesnt work there isnt much else we can do 
#
# In readme maybe need to definea set LED Pin for people to use so we dont have
# to deal with error trying to find it (ie loading from file and having 
# and error trying that but note this could be edited it code)
print("LED Initialising ...")
try:
    led_pin = Pin(18, Pin.OUT)
    led_pin.on()
    utime.sleep_ms(75)
    led_pin.off()
    print("LED initialised ...")
except Exception as e:
    print("Error initializing LED pin, unable to continue:", e)
    sys.exit()


print("Display Initialising ...")
display = initialize_display(i2c_scl=1, i2c_sda=0, led_pin=led_pin)  # Move to HARDWARE.conf ?
print("Display initialised.")

shared_state = SharedState()

#config = load_config(display)  # need to get config before displaymanager setup perhaps? so if error still need to show user
#shared_state = SharedState(config)
 




# DisplayManager
try:
    display_manager = DisplayManager(display, shared_state)
    display_manager.show_startup_screen()
except Exception as e:
    error_text = "Start up failed - [display-setup] " + MAIN_ERROR_MESSAGES["display-setup"] + " " + str(e)
    print(error_text + " " + str(e))
    display.fill(0)
    display.text(error_text, 0, 0)
    display.text(str(e), 0, 15)
    display.show()
    while True:
        # Flash a LED as a backup - maybe some kind of code like one flash,flash,off,off,flash.off,off etc 
        utime.sleep_ms(100)
    sys.exit()



# Maybe put in function reset when options reloaded as they may affect settings
#Termocouple K type
#MAX6675
#sck = Pin No 6
#cs = Pin No 7
#so = Pin No 8
# Initialize termocouple before switching on induction heater
try:
    utime.sleep_ms(700)
    thermocouple = Thermocouple(6, 7, 8, shared_state.heater_on_temperature_difference_threshold)
    utime.sleep_ms(350)
    _, _ = thermocouple.get_filtered_temp(False)  # Sets: last_known_safe_temp - Do here rather than in class as it sometimes returns error if on class init 
except Exception as e:
    error_text = "Start up failed: " + str(e)
    print(error_text)
    while True:
        display_manager.display_error("thermocouple-setup",str(error_text))
        utime.sleep_ms(100)
    sys.exit() #?

# 1-Wire temperature sensor 
# can chain more than one together easly so will be useful for >1 coils
# not needed for the time being - maybe tie each sensor to the heater coil in ih class?
# planned to be used for monitoring temperature of zvs induction curcuit
#
#ds = ds18x20.DS18X20(onewire.OneWire(machine.Pin(17)))
#roms = ds.scan()
#print('1-wire found devices:', roms)
#ds.convert_temp()
#ds_temperature = ds.read_temp(roms[0])

# PI Temperature Sensor 
pi_temperature_sensor = machine.ADC(4)
shared_state.pi_temperature = get_pi_temperature_or_handle_error(pi_temperature_sensor)

# InputHandler
input_handler = InputHandler(rotary_clk_pin=5, rotary_dt_pin=4, button_pin=14, shared_state=shared_state)

# MenuSystem
menu_system = MenuSystem(display_manager, shared_state)


# PID
pid = PID( (shared_state.setpoint * 0.1), (shared_state.setpoint * 0.02), (shared_state.setpoint * 0.01), setpoint = shared_state.setpoint )
# when setpoint = 100  common values (10%, 2%, 1%) 
# possibly move to shared_state something like: initial_P, initial_I, initial_D?

# Ziegler-Nichols method for a system with a fast response time
#pid = PID(0.6, 1.2, 0.001, setpoint = shared_state.setpoint)

# Auto PID starting values:
#pid = PID(setpoint = shared_state.setpoint)

# not sure if any value moving to shared state?
pid.output_limits = (0, 10)

#read before trying to tune: http://brettbeauregard.com/blog/2017/06/introducing-proportional-on-measurement/
#pid.differential_on_measurement = True   #Either this or the below not both - this is the default for PID
#pid.proportional_on_measurement = True   #Seems to be a bit odd





# InductionHeater

ihTimer = Timer(-1) # need to replace with CustomTimer 

heater = HeaterFactory.create_heater('induction', coil_pins=(12, 13), timer=ihTimer)
heater.off()

pidTimer = CustomTimer(371, machine.Timer.PERIODIC, timerUpdatePIDandHeater)  # need to have timer setup before calling below 
shared_state.heater_temperature, _ = get_thermocouple_temperature_or_handle_error(thermocouple, heater)

print("Timers Initialising ...")
pidTimer.start()


piTempTimer = CustomTimer(903, machine.Timer.PERIODIC, timerSetPiTemp)
piTempTimer.start()



print("Timers initialised.")


# start up stuff done
############### 



#watchdog = machine.WDT(timeout=(1000 * 8)) # 100 secs

while True:
    if not shared_state.in_menu:
        #print(shared_state.current_menu_position)
        if shared_state.current_menu_position <= 1:
            if shared_state.rotary_last_mode != "setpoint": 
                input_handler.setup_rotary_values()
            shared_state.current_menu_position = 1
            display_manager.show_screen_home_screen(pid.components, heater.is_on())
            display_manager.display_heartbeat()
        else:
            if shared_state.rotary_last_mode != shared_state.menu_options[shared_state.current_menu_position]: 
                input_handler.setup_rotary_values()
            #print ("Displaying " + shared_state.menu_options[shared_state.current_menu_position])
            menu_system.display_selected_option()
    else:
        if shared_state.rotary_last_mode != "menu": 
            input_handler.setup_rotary_values()
            
        if shared_state.menu_selection_pending:
            menu_system.handle_menu_selection()
            shared_state.menu_selection_pending = False
        elif shared_state.rotary_direction is not None:
            menu_system.navigate_menu(shared_state.rotary_direction)
            shared_state.rotary_direction = None
        else:
            pass

   
#   contrast = contrast - 1 
    #display.contrast(contrast)
    #print(str(contrast))
    #if contrast < 0: contrast = 255
 #   watchdog.feed() # maybe have a check somewhere to make sure its ok to feed
    utime.sleep_ms(75)

