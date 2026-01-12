import utime
from simple_pid import PID

class SharedState:
    def __init__(self, led_red_pin, led_green_pin, led_blue_pin):
        self.led_red_pin = led_red_pin
        self.led_green_pin = led_green_pin
        self.led_blue_pin = led_blue_pin
        
        self.temperature_units = 'C'       # Not tested F at all 
        
        self.temperature_setpoint = 165     # Initial PID temperature setpoint 

        # PID controller
        self.pid = PID(setpoint=self.temperature_setpoint)
        self.pid.output_limits = (0, 100)


        self.control = 'temperature_pid'
        #self.control = 'watts'
        #self.control = 'duty_cycle'
        self.set_watts = 30  # like setpoint but for watts
        self.set_duty_cycle = 50.0  # Duty cycle percentage (0-100%) when control='duty_cycle' (supports 0.1% steps)
        
        
        self.power_type = 'mains'
        #self.power_type = 'lipo'  #'mains', 'lipo', 'lead'
        
        self.lipo_count = 4

        self.lipo_safe_volts = 3.3
        self.lead_safe_volts = 12.0 
        self.mains_safe_volts = 28.0 

        self.heater_resistance = 0.49  #this should not change unless coils is replaced user needs to provide this value

        self.heater_too_hot = False  # State variable for temperature over-limit hysteresis (250C turn on, 240C turn off)

        self.max_watts = 75 #135w for 0.6 ohm nichrome coil is about max before it starts to glow
                             #Note: 14 awg copper wire rated max amp is about 15amp - so at 12v = 180w max power to be safe
                             #Keep to 100w for single mosfet unit if doing them in parrallel then ok to go more

        self.heater_max_duty_cycle_percent = 0 #this now gets adjusted automatically based on max_watts / watt level
        self.input_volts = False  # Needs to be False at startup
        
        # PI Temperature monitoring
        self.pi_temperature_limit = 60  # Shutdown if PI exceeds this temperature
        
        # PID Tuning - can be loaded from profile
        self.pid_tunings = (2.3, 0.03, 0)  # (P, I, D) - example for 2x lipo batteries
        
        # Track which profile is currently loaded
        self.profile = "default"  # Will be updated when a profile is loaded
       
        self.session_timeout = 7 * 60 * 1000       # length of time for a session before auto off (7 mins)
        self.session_extend_time = 2 * 60 * 1000   # length of time to extens senssion by when single click in last minute of session
        self.session_reset_pid_when_near_setpoint = True # Reset PID stats once near setpoint to reduce overshoot
        self.pid_reset_high_temperature = 15  # degrees above setpoint to reset PID when already reached setpoint

        
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
        self.temperature_max_allowed_setpoint = 250 # max allowed temperature - need to protect ptfe around thermocouple
        

        # below are controlled by internal processes dont mess with 
        #self.temperature_readings =  {i: 20 for i in range(128)}
        self.temperature_readings =  {}
        self.heater_temperature = 0  # Overal heater temperature from thermocouple at the moment only deals with one 
                                     # possibly extend to deal with multpile but not to start with

        self.input_volts_readings = {}  #need to add volt graph
        self.input_volts = 0
        
        self.watt_readings = {}
        self.watts = 0
        
        # Cache min/max time values for display optimization
        self.temperature_min_time = 0
        self.temperature_max_time = 0
        self.watt_min_time = 0
        self.watt_max_time = 0
        
        self.pi_temperature = 0         # PI Pico chip temperature
        self.pi_temperature_limit = 60  # Maybe place pico board above/next to mosfet module so we get some idea hot its getting 

        #Maybe make below options have more info eg:
        # setup_rotary_values in inputhandler 
        # options screen timeout to return to home (or none for graphs etc)
        self.menu_options = [f"{self.profile}",
                             "Home Screen",
                             "Profiles",
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
        
        self.profile_list = []  # List of available profiles
        self.profile_selection_index = 0  # Current profile selection in list
        self.profile_load_pending = False  # Flag when user clicks to load profile
        
        self.session_start_time = 0
        self.session_setpoint_reached = False
        self.session_reset_pid_when_near_setpoint = True # Seems to help improve overshoot reduction by resetting pid stats once near setpoint from cold
        self._mode = "Off" 

        # Error tracking (simpler approach without exceptions)
        self.current_error = None  # Tuple of (error_code, error_message) or None
        self.last_error_time = 0
        self.error_display_timeout = 5000  # Display error for 5 seconds
        
        # Error message descriptions (reference only)
        self.error_messages = {"display-setup":      "Error initializing display, cannot continue",
                       "heater-too_hot":     "Heater too hot",
                       "battery_level-too-low": "Battery too low",
                       "unknown-power-type": "Unknown power type",
                       "mains-voltage-too-high": "Mains voltage too high " + str(self.mains_safe_volts) + "V",
                       "pi-too_hot":         "PI too hot > " + str(self.pi_temperature_limit) + "C",
                       "thermocouple-read_error": "Thermocouple read error",
                       "thermocouple-invalid_reading": "Invalid thermocouple reading",
                       "thermocouple-zero_reading": "Thermocouple zero reading",
                       "thermocouple-below_zero": "Temperature below zero",
                       "thermocouple-above_limit": "Temperature above limit"
        }

        # Controls that are currently enabled/available on this hardware
        # Possible values: 'temperature_pid', 'duty_cycle', 'watts'
        self.enabled_controls = ['temperature_pid', 'duty_cycle', 'watts']


    def get_mode(self):
        if self._mode == "Session" and (self.session_timeout - self.get_session_mode_duration()) < 0:
            session_start_time = 0
            self.led_green_pin.off()
            self.led_blue_pin.off()  # In case session manually ended when light on
            self._mode = "Off"  # Set off here rather than after playing sounds as this can get called again while sounds being played
            self.session_setpoint_reached = False
            # Clear heater-too_hot error when session ends
            if self.current_error and self.current_error[0] == "heater-too_hot":
                self.clear_error()
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
            # Clear heater-too_hot error when turning off the heater
            if self.current_error and self.current_error[0] == "heater-too_hot":
                self.clear_error()
        else:
            self.led_green_pin.on()
            self.pid.reset()
            print("PID Stats reset")

    def get_session_mode_duration(self):
        return utime.ticks_diff(utime.ticks_ms(), self.session_start_time)
    
    def set_error(self, error_code, error_message=None):
        """Set current error state. Pass None to clear error."""
        if error_code is None:
            self.current_error = None
            return
        if error_message is None:
            error_message = self.error_messages.get(error_code, "Unknown error")
        self.current_error = (error_code, error_message)
        self.last_error_time = utime.ticks_ms()
    
    def has_error(self):
        """Check if there's an active error."""
        return self.current_error is not None
    
    def clear_error(self):
        """Clear current error."""
        self.current_error = None
    
    def apply_profile(self, profile_config):

        # Update only the attributes that exist in the profile config
        if 'session_timeout' in profile_config:
            self.session_timeout = profile_config['session_timeout']
        if 'session_extend_time' in profile_config:
            self.session_extend_time = profile_config['session_extend_time']
        if 'session_reset_pid_when_near_setpoint' in profile_config:
            self.session_reset_pid_when_near_setpoint = profile_config['session_reset_pid_when_near_setpoint']
        if 'temperature_units' in profile_config:
            self.temperature_units = profile_config['temperature_units']
        if 'temperature_setpoint' in profile_config:
            self.temperature_setpoint = profile_config['temperature_setpoint']
            self.pid.setpoint = self.temperature_setpoint  # Update PID setpoint too
        if 'control' in profile_config:
            self.control = profile_config['control']
        if 'set_watts' in profile_config:
            self.set_watts = profile_config['set_watts']
        if 'set_duty_cycle' in profile_config:
            self.set_duty_cycle = profile_config['set_duty_cycle']
        if 'power_type' in profile_config:
            self.power_type = profile_config['power_type']
        if 'lipo_count' in profile_config:
            self.lipo_count = profile_config['lipo_count']
        if 'lipo_safe_volts' in profile_config:
            self.lipo_safe_volts = profile_config['lipo_safe_volts']
        if 'lead_safe_volts' in profile_config:
            self.lead_safe_volts = profile_config['lead_safe_volts']
        if 'mains_safe_volts' in profile_config:
            self.mains_safe_volts = profile_config['mains_safe_volts']
        if 'power_threshold' in profile_config:
            self.power_threshold = profile_config['power_threshold']
        if 'heater_on_temperature_difference_threshold' in profile_config:
            self.heater_on_temperature_difference_threshold = profile_config['heater_on_temperature_difference_threshold']
        if 'max_watts' in profile_config:
            self.max_watts = profile_config['max_watts']
        if 'heater_resistance' in profile_config:
            self.heater_resistance = profile_config['heater_resistance']
        if 'display_contrast' in profile_config:
            self.display_contrast = profile_config['display_contrast']
        if 'display_rotate' in profile_config:
            self.display_rotate = profile_config['display_rotate']
        if 'click_check_timeout' in profile_config:
            self.click_check_timeout = profile_config['click_check_timeout']
        if 'temperature_max_allowed_setpoint' in profile_config:
            self.temperature_max_allowed_setpoint = profile_config['temperature_max_allowed_setpoint']
        if 'pi_temperature_limit' in profile_config:
            self.pi_temperature_limit = profile_config['pi_temperature_limit']
        if 'pid_tunings' in profile_config:
            self.pid_tunings = profile_config['pid_tunings']
            self.pid.tunings = self.pid_tunings  # Update PID tunings immediately
        if 'pid_reset_high_temperature' in profile_config:
            self.pid_reset_high_temperature = profile_config['pid_reset_high_temperature']

        # If the profile requested a control mode, ensure it's enabled
        if 'control' in profile_config:
            desired = profile_config['control']
            if self.is_control_enabled(desired):
                self.control = desired
            else:
                enabled = self.get_enabled_controls()
                if enabled:
                    self.control = enabled[0]
                else:
                    self.control = 'duty_cycle'
        
        print(f"Profile applied to SharedState")

    # Control enable/disable helpers
    def enable_control(self, control_name):
        if control_name not in self.enabled_controls:
            self.enabled_controls.append(control_name)

    def disable_control(self, control_name):
        if control_name in self.enabled_controls:
            try:
                self.enabled_controls.remove(control_name)
            except ValueError:
                pass

    def is_control_enabled(self, control_name):
        return control_name in self.enabled_controls

    def get_enabled_controls(self):
        return list(self.enabled_controls)
    
    def set_profile_name(self, profile_name):
        """Update the profile name and refresh menu_options display."""
        self.profile = profile_name
        # Update first menu option to show current profile
        if self.menu_options:
            self.menu_options[0] = f"{self.profile}"
        print(f"Profile set to: {self.profile}")
    
    def initialize_defaults(self):
        """Return a dictionary with all hardcoded default configuration values.
        Used when loading profiles to ensure they start from a known baseline."""
        return {
            'session_timeout': 7 * 60 * 1000,
            'session_extend_time': 2 * 60 * 1000,
            'session_reset_pid_when_near_setpoint': True,
            'temperature_units': 'C',
            'temperature_setpoint': 165,
            'control': 'temperature_pid',
            'set_watts': 30,
            'set_duty_cycle': 50.0,
            'power_type': 'mains',
            'lipo_count': 4,
            'lipo_safe_volts': 3.3,
            'lead_safe_volts': 12.0,
            'mains_safe_volts': 28.0,
            'power_threshold': 0,
            'heater_on_temperature_difference_threshold': 20,
            'max_watts': 75,
            'heater_resistance': 0.49,
            'display_contrast': 255,
            'display_rotate': True,
            'click_check_timeout': 800,
            'temperature_max_allowed_setpoint': 250,
            'pi_temperature_limit': 60,
            'pid_tunings': (2.3, 0.03, 0),
            'pid_reset_high_temperature': 15,
        }
