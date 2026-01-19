import utime
from machine import Timer, Pin
from rotary_irq_rp2 import RotaryIRQ
from customtimer import CustomTimer

class InputHandler:
    def __init__(self, rotary_clk_pin, rotary_dt_pin, button_pin, switch_control_pin, middle_button_pin, shared_state):
    
        print("InputHandler Initialising ...")
        self.rotary = RotaryIRQ(pin_num_clk=rotary_clk_pin, pin_num_dt=rotary_dt_pin, reverse=True, range_mode=RotaryIRQ.RANGE_BOUNDED)
        self.shared_state = shared_state

        self.rotary.add_listener(self.rotary_callback)
        self.rotary_used = False
        
        self.button = Pin(button_pin, Pin.IN, Pin.PULL_UP)
        self.button_pressed = False
        self.button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self.button_state_changed)
        self.last_button_press_time = 0

        self.click_counter = 0 
        self.click_check_timer = CustomTimer(period=self.shared_state.click_check_timeout, mode=Timer.ONE_SHOT, callback=self.check_click_count)
        
        self.previous_rotary_value = self.rotary.value() # Initialize the previous rotary value


        self.switch_control_button = Pin(switch_control_pin, Pin.IN, Pin.PULL_UP)
        self.switch_control_button_pressed = False
        self.switch_control_button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self.switch_control_button_state_changed)

        self.middle_button = Pin(middle_button_pin, Pin.IN, Pin.PULL_UP)
        self.middle_button_pressed = False
        self.middle_button.irq(trigger=Pin.IRQ_FALLING | Pin.IRQ_RISING, handler=self.middle_button_state_changed)
        self.middle_button_click_counter = 0
        self.middle_button_last_press_time = 0
        self.middle_button_click_check_timer = CustomTimer(period=self.shared_state.click_check_timeout, mode=Timer.ONE_SHOT, callback=self.check_middle_button_click_count)
        
        print("InputHandler initialised.")

    def setup_rotary_values(self):
        if self.shared_state.rotary_last_mode != "menu" and self.shared_state.in_menu:
            self.rotary.set(value=self.shared_state.current_menu_position)
            self.previous_rotary_value = self.shared_state.current_menu_position
            self.rotary.set(min_val=0)
            self.rotary.set(max_val=len(self.shared_state.menu_options)-1)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_WRAP)
            self.shared_state.rotary_last_mode = "menu"
            #print("setup rotarty menu" + str(self.rotary.value()))
        elif not self.shared_state.in_menu and self.shared_state.rotary_last_mode != "autosession" and self.shared_state.get_mode() == "autosession":
            # Setup rotary for autosession time adjustment - PRIORITY over setpoint when autosession is running
            # Rotary position represents current position in the profile (0 = start, max = end)
            if self.shared_state.autosession_profile:
                profile_duration_ms = self.shared_state.autosession_profile.get_duration_ms()
                # Use configurable autosession_time_adjustment_step from profile config (in seconds, convert to ms)
                step_ms = self.shared_state.autosession_time_adjustment_step * 1000
                max_steps = int(profile_duration_ms / step_ms)
            else:
                max_steps = 600  # Fallback if no profile
            
            self.rotary.set(value=0)
            self.previous_rotary_value = 0
            self.rotary.set(min_val=0)           # Start of profile
            self.rotary.set(max_val=max_steps)   # End of profile
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "autosession"
            #print(f"setup rotary autosession time adjustment: 0 to {max_steps} steps (step_size={self.shared_state.autosession_time_adjustment_step}s)")
        elif self.shared_state.rotary_last_mode != "Profiles" and self.shared_state.menu_options[self.shared_state.current_menu_position] == "Profiles":
            # Handle profile selection like show_settings
            self.rotary.set(value=self.shared_state.profile_selection_index)
            self.previous_rotary_value = self.shared_state.profile_selection_index
            self.rotary.set(min_val=0)
            max_profiles = len(self.shared_state.profile_list) - 1 if self.shared_state.profile_list else 0
            self.rotary.set(max_val=max_profiles)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Profiles" 
            #print(f"setup rotary profiles: index={self.rotary.value()}, max={max_profiles}")
        elif self.shared_state.rotary_last_mode != "Autosession Profiles" and self.shared_state.menu_options[self.shared_state.current_menu_position] == "Autosession Profiles":
            # Handle autosession profile selection
            self.rotary.set(value=self.shared_state.autosession_profile_selection_index)
            self.previous_rotary_value = self.shared_state.autosession_profile_selection_index
            self.rotary.set(min_val=0)
            max_autosession = len(self.shared_state.autosession_profile_list) - 1 if self.shared_state.autosession_profile_list else 0
            self.rotary.set(max_val=max_autosession)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Autosession Profiles"
            #print(f"setup rotary autosession profiles: index={self.rotary.value()}, max={max_autosession}")
        elif self.shared_state.rotary_last_mode != "Display Contrast" and self.shared_state.menu_options[self.shared_state.current_menu_position] == "Display Contrast":
            self.rotary.set(value=self.shared_state.display_contrast)
            self.previous_rotary_value = self.shared_state.display_contrast
            self.rotary.set(min_val=0)
            self.rotary.set(max_val=255)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Display Contrast"
            #print("setup rotarty contrast" + str(self.rotary.value()))

        elif self.shared_state.temporary_max_watts_screen_active and self.shared_state.rotary_last_mode != "Temporary Max Watts":
            self.rotary.set(value=self.shared_state.temporary_max_watts)
            self.previous_rotary_value = self.shared_state.temporary_max_watts
            self.rotary.set(min_val=0)
            self.rotary.set(max_val=self.shared_state.max_watts)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Temp Max Watts"
            #print("setup rotary temporary_max_watts" + str(self.rotary.value()))

        elif self.shared_state.rotary_last_mode != "Show Settings" and self.shared_state.menu_options[self.shared_state.current_menu_position] == "Show Settings":
            self.rotary.set(value=self.shared_state.show_settings_line)
            self.previous_rotary_value = self.shared_state.show_settings_line
            self.rotary.set(min_val=0)
            # Calculate max settings count - count all attributes in shared_state
            settings_count = len(self.shared_state.__dict__.keys()) - 1
            self.rotary.set(max_val=settings_count)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Show Settings"
            #print("setup rotarty show settings" + str(self.rotary.value()))

        else:
            #need to update to temperature-setpoint and for when we have watts-pid control
            if self.shared_state.rotary_last_mode != "setpoint":
                if self.shared_state.control == 'watts':
                    self.rotary.set(value=self.shared_state.set_watts)
                    self.previous_rotary_value = self.shared_state.set_watts
                    self.rotary.set(min_val=0)
                    self.rotary.set(max_val=self.shared_state.max_watts)
                elif self.shared_state.control == 'duty_cycle':
                    # Rotary works in integer steps; map 0-1000 to 0.0-100.0% (0.1% steps)
                    self.rotary.set(value=int(self.shared_state.set_duty_cycle * 10))
                    self.previous_rotary_value = int(self.shared_state.set_duty_cycle * 10)
                    self.rotary.set(min_val=0)
                    self.rotary.set(max_val=1000)
                else:
                    self.rotary.set(value=self.shared_state.temperature_setpoint)
                    self.previous_rotary_value = self.shared_state.temperature_setpoint
                    self.rotary.set(min_val=1)
                    self.rotary.set(max_val=self.shared_state.temperature_max_allowed_setpoint)  # Max temp - allow conversion to F?
                
                self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
                self.shared_state.rotary_last_mode = "setpoint"
                #print("setup rotarty setpoint" + str(self.rotary.value()))

    def rotary_callback(self):
        current_menu_option = self.shared_state.menu_options[self.shared_state.current_menu_position] if self.shared_state.current_menu_position < len(self.shared_state.menu_options) else None
    
        # PRIORITY: Check for autosession mode FIRST before anything else
        if not self.shared_state.in_menu and self.shared_state.get_mode() == "autosession":
            # Handle autosession time adjustment - this takes precedence over all other modes
            # Adjust the start time directly so all elapsed calculations automatically use the adjusted time
            current_value = self.rotary.value()
            delta = current_value - self.previous_rotary_value
            step_ms = self.shared_state.autosession_time_adjustment_step * 1000  # Convert configured step (seconds) to milliseconds
            time_adjustment = delta * step_ms
            self.shared_state.autosession_start_time -= time_adjustment  # Move start time backward to advance profile, forward to rewind
            #print(f"Autosession rotary: current={current_value}, prev={self.previous_rotary_value}, delta={delta}, time_adj={time_adjustment}ms, new_start_time={self.shared_state.autosession_start_time}")
            self.previous_rotary_value = current_value
            return  # Exit early - don't process as normal setpoint
        
        if self.shared_state.in_menu:
            direction = 'up' if self.rotary.value() > self.previous_rotary_value else 'down'
            self.shared_state.rotary_direction = direction

        else:
            # Not in menu - could be on a display screen like show_settings or profile
            if self.shared_state.rotary_last_mode == "Profiles":
                # Handle profile selection
                self.shared_state.profile_selection_index = self.rotary.value()
            elif self.shared_state.rotary_last_mode == "Autosession Profiles":
                # Handle autosession profile selection
                self.shared_state.autosession_profile_selection_index = self.rotary.value()
            elif self.shared_state.rotary_last_mode == "Display Contrast":
                # Update display contrast
                self.shared_state.display_contrast = self.rotary.value()
            elif self.shared_state.rotary_last_mode == "Temp Max Watts":
                # Update temporary_max_watts and reset timeout
                self.shared_state.temporary_max_watts = self.rotary.value()
                self.shared_state.temporary_max_watts_start_time = utime.ticks_ms()
                #print(f"Temporary Max Watts updated to: {self.shared_state.temporary_max_watts}")
            elif self.shared_state.rotary_last_mode == "Show Settings":
                # Update show settings line
                self.shared_state.show_settings_line = self.rotary.value()
            else:
                # Regular setpoint/watts adjustment
                # Determine adjustment per rotary detent.
                # For duty_cycle (rotary scale 0-1000 = 0.0-100.0%), use 10 tenths (1%) steps when under 10.0%,
                # otherwise use 100 tenths (10%) steps. Apply this regardless of button state.
                if self.shared_state.control == 'duty_cycle':
                    cur = self.rotary.value()
                    if self.button_pressed:
                        # Button pressed: larger jumps (1% under 10%, 10% above)
                        if cur < 100:  # less than 10.0%
                            adjustment_rate = 10
                        else:
                            adjustment_rate = 100
                    else:
                        # Button not pressed: fine adjustments (0.1% under 10%, 1% above)
                        if cur < 100:
                            adjustment_rate = 1
                        else:
                            adjustment_rate = 10
                else:
                    # Non-duty controls: accelerate when button is held, otherwise single-step only
                    adjustment_rate = 10 if self.button_pressed else 0

                if self.rotary.value() > self.previous_rotary_value:
                    self.rotary.set(value=self.rotary.value() + adjustment_rate)
                else:
                    self.rotary.set(value=(self.rotary.value() - adjustment_rate))
                
                if self.shared_state.control == 'watts':
                    self.shared_state.set_watts = self.rotary.value()
                elif self.shared_state.control == 'duty_cycle':
                    # Convert rotary integer (tenths of percent) back to float percent
                    self.shared_state.set_duty_cycle = float(self.rotary.value()) / 10.0
                else:
                    self.shared_state.temperature_setpoint = self.rotary.value()

        self.previous_rotary_value = self.rotary.value()
        if self.button_pressed: self.rotary_used = True

    def button_state_changed(self, pin):
        current_time = utime.ticks_ms() 
        if pin.value() == 0: # Button is pressed
            if not self.button_pressed: # Only process the press if the button was not already pressed
                self.button_pressed = True 
                time_since_last_press = current_time - self.last_button_press_time
                if time_since_last_press < self.shared_state.click_check_timeout:
                    self.click_counter += 1
                else:
                    self.click_counter = 1 # Reset the counter if the time since last press is more than 750ms
                    
                self.last_button_press_time = current_time # Update the last button press time

                if self.shared_state.in_menu:
                    self.shared_state.menu_selection_pending = True

            # Restart timer on each click to extend the detection window
            if self.click_check_timer.is_timer_running():
                self.click_check_timer.stop()
            self.click_check_timer.start()
        else: # Button is released
            self.rotary_used = False # Reset if rotary use between presses
            if self.button_pressed:
                #print('Button released')
                self.button_pressed = False
                if not self.shared_state.in_menu and self.shared_state.get_mode() == 'Manual':
                    self.shared_state.set_mode("Off")
                    #print("Switching to Off mode")

    def check_click_count(self, timer):   
        if self.click_counter == 1:
            #print('Single click detected')
            if self.shared_state.in_menu and not self.rotary_used:
                # User selected a menu item - exit menu to display the selected screen
                self.shared_state.in_menu = False
                self.shared_state.menu_selection_pending = True
            elif not self.shared_state.in_menu and not self.rotary_used:
                # Handle profile selection click - just set flag, let main loop handle display
                if self.shared_state.rotary_last_mode == "Profiles":
                    self.shared_state.profile_load_pending = True
                elif self.shared_state.rotary_last_mode == "Autosession Profiles":
                    self.shared_state.autosession_profile_load_pending = True
                # Handle session extend in last minute
                elif self.shared_state.get_mode() == "Session":
                    if (self.shared_state.session_timeout - self.shared_state.get_session_mode_duration()) < 60000:
                        self.shared_state.session_start_time = self.shared_state.session_start_time + self.shared_state.session_extend_time

        elif self.click_counter == 2:
            #print('Double click detected')
            if not self.shared_state.in_menu:
                self.shared_state.in_menu = True
                self.shared_state.rotary_direction = 'up' # Just Fake it and go to top of menu to force screen refresh
            #else:
                #print('Ignoring double click already in menu')
                
        elif self.click_counter == 3:
            #print('Triple click detected')
            # Allow menu and navigation even when autosession active, but prevent starting a new session
            if not self.shared_state.in_menu and not self.rotary_used:
                if self.shared_state.get_mode() != "autosession":  # Only allow Session start if autosession not active
                    if self.shared_state.get_mode() == "Off" :
                        #print("Switching to Session mode")
                        self.shared_state.set_mode("Session") 
                    elif self.shared_state.get_mode() == "Session":
                        self.shared_state.set_mode("Off")
                        #print("Stopped Session mode")
                else:
                    # Autosession is active, allow menu and navigation
                    if self.shared_state.get_mode() == "Session":
                        self.shared_state.set_mode("Off")
                        #print("Stopped Session mode")
                    
        elif self.click_counter == 4:
            #print('Quadruple click detected')
            if not self.shared_state.in_menu and not self.rotary_used:
                if self.shared_state.get_mode() == "Off" :
                    #print("Switching to Session mode for 1 minute")
                    self.shared_state.set_mode("Session") 
                    self.shared_state.session_start_time = (utime.ticks_ms() - (self.shared_state.session_timeout - 60000))
                #elif self.shared_state.get_mode() == "Session":
                #    self.shared_state.set_mode("Off")
        #else:
            #print(self.click_counter, ' clicks detected')
            
        self.click_counter = 0 # Reset the click counter
        if self.click_check_timer.is_timer_running():
            self.click_check_timer.stop()
            
        if self.button_pressed:
            #print("Timer finished: Button still being held")
            if self.shared_state.get_mode() == 'Off' and not self.shared_state.in_menu and not self.rotary_used:
                self.shared_state.set_mode("Manual")
                #print("Switching to Manual mode")
        else:
            self.rotary_used = False # Reset if rotary use between presses
            #print("Timer finished: Button released")
 
    def check_middle_button_click_count(self, timer):
        """Handle middle button click detection for temporary_max_watts and autosession."""
        if self.middle_button_click_counter == 1:
            # Single-click: Show temporary_max_watts screen
            if not self.shared_state.in_menu and not self.rotary_used:
                self.shared_state.middle_button_pressed = True
        
        elif self.middle_button_click_counter == 3:
            # Triple-click detected: activate/deactivate autosession
            if not self.shared_state.in_menu and not self.rotary_used:
                if self.shared_state.autosession_profile and self.shared_state.get_mode() != "autosession":
                    # Activate autosession - save current temperature_setpoint first
                    self.shared_state.saved_temperature_setpoint = self.shared_state.temperature_setpoint
                    self.shared_state.set_mode("autosession")
                elif self.shared_state.get_mode() == "autosession":
                    # Deactivate autosession and restore saved temperature_setpoint
                    self.shared_state.set_mode("Off")
                    self.shared_state.temperature_setpoint = self.shared_state.saved_temperature_setpoint
                    self.shared_state.pid.setpoint = self.shared_state.temperature_setpoint
                    self.shared_state.rotary_last_mode = None

        
        elif self.middle_button_click_counter == 4:
            # Quadruple-click detected: stop autosession and switch to normal session
            if not self.shared_state.in_menu and not self.rotary_used:
                if self.shared_state.get_mode() == "autosession":
                    # Safely stop autosession first (allows log file to be flushed and closed)
                    # then start a normal session and restore saved temperature_setpoint
                    self.shared_state.set_mode("Off")
                    self.shared_state.temperature_setpoint = self.shared_state.saved_temperature_setpoint
                    self.shared_state.pid.setpoint = self.shared_state.temperature_setpoint
                    # Reset rotary_last_mode so it reconfigures for the new mode
                    self.shared_state.rotary_last_mode = None
                    self.shared_state.set_mode("Session")
        
        self.middle_button_click_counter = 0  # Reset the click counter
        if self.middle_button_click_check_timer.is_timer_running():
            self.middle_button_click_check_timer.stop()
 
    def switch_control_button_state_changed(self, pin):
        if pin.value() == 0: # Button is pressed
                self.switch_control_button_pressed = True
        else:
                self.switch_control_button_pressed = False
                
        if self.switch_control_button_pressed:
            enabled = self.shared_state.get_enabled_controls()
            if not enabled:
                # Fallback to duty_cycle if nothing enabled
                new_control = 'duty_cycle'
            else:
                try:
                    idx = enabled.index(self.shared_state.control)
                    new_control = enabled[(idx + 1) % len(enabled)]
                except ValueError:
                    # Current control not in enabled list, pick first
                    new_control = enabled[0]

            # Set new control and update rotary to appropriate value
            self.shared_state.control = new_control
            self.shared_state.pid.reset()
            if new_control == 'watts':
                self.rotary.set(value=self.shared_state.set_watts)
                self.previous_rotary_value = self.shared_state.set_watts
            elif new_control == 'duty_cycle':
                # Map float percent to rotary integer (tenths of percent)
                self.rotary.set(value=int(self.shared_state.set_duty_cycle * 10))
                self.previous_rotary_value = int(self.shared_state.set_duty_cycle * 10)
            else:  # temperature_pid
                self.rotary.set(value=self.shared_state.temperature_setpoint)
                self.previous_rotary_value = self.shared_state.temperature_setpoint
            # Force rotary_last_mode to None so setup_rotary_values will update the limits
            self.shared_state.rotary_last_mode = None

    def middle_button_state_changed(self, pin):
        if pin.value() == 0: # Button is pressed
            if not self.middle_button_pressed:
                self.middle_button_pressed = True
                
                # Track clicks for click detection
                current_time = utime.ticks_ms()
                time_since_last_press = utime.ticks_diff(current_time, self.middle_button_last_press_time)
                
                if time_since_last_press < self.shared_state.click_check_timeout:
                    self.middle_button_click_counter += 1
                else:
                    self.middle_button_click_counter = 1  # Reset the counter if the time since last press is more than timeout
                    
                self.middle_button_last_press_time = current_time  # Update the last button press time

                # Restart timer on each click to extend the detection window
                if self.middle_button_click_check_timer.is_timer_running():
                    self.middle_button_click_check_timer.stop()
                self.middle_button_click_check_timer.start()
        else: # Button is released
            self.middle_button_pressed = False


