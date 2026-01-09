import utime
from simple_pid import PID

class SharedState:
    def __init__(self, led_red_pin, led_green_pin, led_blue_pin):
        # All of the below hard coded can be loaded from a file or similar 
        # Need to add other stuff like butto click time, max temp, etc

        #If more of these are added need to update line count in intputhandler for displing them
        # Store hardware dependencies
        self.led_green_pin = led_green_pin
        self.led_blue_pin = led_blue_pin
        
        self.temperature_units = 'C'       # Not tested F at all 
        
        self.setpoint = 165     # Initial PID setpoint 

        # PID controller
        self.pid = PID(setpoint=self.setpoint)
        self.pid.output_limits = (0, 100)


        self.control = 'pid'
        #self.control = 'watts'
        self.setwatts = 30  # like setpoint but for watts
        
        
        self.power_type = 'mains'
        #self.power_type = 'lipo'  #'mains', 'lipo', 'lead'
        
        self.lipo_count = 4

        self.lipo_safe_volts = 3.3
        self.lead_safe_volts = 12.0 
        self.mains_safe_volts = 28.0 

        self.heater_resitance = 0.4  #this should not change unless coils is replaced user needs to provide this value

        self.max_watts = 75 #135w for 0.6 ohm nichrome coil is about max before it starts to glow
                             #Note: 14 awg copper wire rated max amp is about 15amp - so at 12v = 180w max power to be safe
                             #Keep to 100w for single mosfet unit if doing them in parrallel then ok to go more

        self.heater_max_duty_cycle_percent = 0 #this now gets adjusted automatically based on max_watts / watt level
        self.input_volts = False  # Needs to be False at startup
       
        self.session_timeout = 7 * 60 * 1000       # length of time for a session before auto off (7 mins)
        self.session_extend_time = 2 * 60 * 1000   # length of time to extens senssion by when single click in last minute of session

        
        # When in session mode and we first hist setpoint make led change colour ?  and / or sound a buzzer 
        # When session mode about to end (5 secs?) sound buzzer so user can extens easily -
        # maybe popup with "extend session?" screen and on any click/rotate extent it

        # need to check on max temp and how long its been above 250?  re Ptfe insulation and not keeping it too ig for too long 
        # maybe have a timer for this?

        #self.power_threshold = 5  #between pid.output_limits range (1-10)
        self.power_threshold = 0 #for slower sensors like DS18X20 probally lower is better 

        # for the filtered tempterature when induction is on 
        # possibly needs adjusting for different coil sizes/current/voltages - 
        # maybe need way to reset this in the termocouple class if loading setting between reboots?
        # calibrate by placeing thermopile in induction coil and seeing effects on readings when on / off 
        # dont set this too low 
        self.heater_on_temperature_difference_threshold = 20 #for induction heaters

        self.display_contrast = 255
        self.display_rotate = True
        
        # Below is stuff perhaps better to leave alone
        self.click_check_timeout = 800 # ms timeout to multi click in 
        self.max_allowed_setpoint = 250 # max allowed temperature - need to protect ptfe around thermocouple
        

        # below are controlled by internal processes dont mess with 
        #self.temperature_readings =  {i: 20 for i in range(128)}
        self.temperature_readings =  {}
        self.heater_temperature = 0  # Overal heater temperature from thermocouple at the moment only deals with one 
                                     # possibly extend to deal with multpile but not to start with

        self.input_volts_readings = {}  #need to add volt graph
        self.input_volts = 0
        
        self.watt_readings = {}
        self.watts = 0
        
        self.pi_temperature = 0         # PI Pico chip temperature
        self.pi_temperature_limit = 60  # Maybe place pico board above/next to mosfet module so we get some idea hot its getting 

        #Maybe make below options have more info eg:
        # setup_rotary_values in inputhandler 
        # options screen timeout to return to home (or none for graphs etc)
        self.menu_options = ["MENU",
                             "Home Screen",
                             "Graph Setpoint",
                             "Graph Line",
                             "Graph Bar",
                             "Temp Watts Line",
                             "Watts Line",
                             "Show Settings",
                             "Display Contrast"
                            ]
                            # Battery/power info screen  - can we get volts & amps? and move to where pid is on home? + level 
                            # Heater / coil info screen - coil length? coil ohm? (user may need to provide ohm reading at 25C)  
                            # Get resitance ? - its possible for the pico to work out the element reistance and approximate wattsage 
                            # to help user work out a limit - would need to be super careful to only happen when element has no power 
                            # Maybe use pwm heater pins and reconfigure them for to get the resitnace and need a reboot once done?
                            # Get varuous settings for elements in config file as may need to limit highest temp coil can get not to burn insulation PTFE 
                            # ie despite pid/thermocouple - so tcr? or just limit wattage on known values for wire type/length/ohms so it doesnt get too hot 
 
        self.in_menu = False   
        self.current_menu_position = 0 
        self.menu_selection_pending = False 
        self.menu_timeout = 3 * 1000   # 3 secs
        
        self.rotary_direction = None
        self.rotary_last_mode = None

        self.show_settings_line = 0  # for show settings in display to know what setting to show
        
        self.session_start_time = 0
        self.session_setpoint_reached = False
        self.session_reset_pid_when_near_setpoint = True # Seems to help improve overshoot reduction by resetting pid stats once near setpoint from cold
        self._mode = "Off" 

        self.error_messages = {"display-setup":      "Error initializing display, cannout continue",
                       "heater-too_hot":     "Heater too hot > 300C",
                       "battery_level-too-low": "Battery too low",
                       "unknown-power-type": "Unknwon power type",
                       "mains-voltage-too-high": "Mains voltage too high",
                       "pi-too_hot":         "PI too hot > 60C"
        }


    def get_mode(self):
        if self._mode == "Session" and (self.session_timeout - self.get_session_mode_duration()) < 0:
            session_start_time = 0
            self.led_green_pin.off()
            self.led_blue_pin.off()  # In case session manually ended when light on
            self._mode = "Off"  # Set off here rather than after playing sounds as this can get called again while sounds being played
            self.session_setpoint_reached = False
#            buzzer_play_tone(buzzer, 1500, 200)
#            utime.sleep_ms(200)
#            buzzer_play_tone(buzzer, 1000, 200)
#            utime.sleep_ms(200)
#            buzzer_play_tone(buzzer, 500, 200)
        return self._mode

    def set_mode(self, new_mode):
        self.session_setpoint_reached = False
        if new_mode in ["Off", "Manual"]:
            if self._mode == "Session": self.session_start_time = 0
            self._mode = new_mode
        elif new_mode == "Session":
            self.session_start_time = utime.ticks_ms()
            self._mode = "Session"
        else:
            raise ValueError("Invalid mode. Must be 'Off', 'Session' or 'Manual'")
        if new_mode == "Off":
            self.led_blue_pin.off() # In case session manually ended when light on
            self.led_green_pin.off()
        else:
            self.led_green_pin.on()
            self.pid.reset()
            print("PID Stats reset")

    def get_session_mode_duration(self):
        return utime.ticks_diff(utime.ticks_ms(), self.session_start_time)
