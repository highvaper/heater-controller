import utime
from machine import Timer, Pin
from rotary_irq_rp2 import RotaryIRQ
from customtimer import CustomTimer

class InputHandler:
    def __init__(self, rotary_clk_pin, rotary_dt_pin, button_pin, shared_state):
    
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
        
        print("InputHandler initialised.")

    def setup_rotary_values(self):
        if self.shared_state.rotary_last_mode != "menu" and self.shared_state.in_menu:
            self.rotary.set(value=self.shared_state.current_menu_position)
            self.previous_rotary_value = self.shared_state.current_menu_position
            self.rotary.set(min_val=0)
            self.rotary.set(max_val=len(self.shared_state.menu_options)-1)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_WRAP)
            self.shared_state.rotary_last_mode = "menu"
            print("setup rotarty menu" + str(self.rotary.value()))
        elif self.shared_state.rotary_last_mode != "Display Contrast" and self.shared_state.menu_options[self.shared_state.current_menu_position] == "Display Contrast":
            self.rotary.set(value=self.shared_state.display_contrast)
            self.previous_rotary_value = self.shared_state.display_contrast
            self.rotary.set(min_val=0)
            self.rotary.set(max_val=255)
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Display Contrast"
            print("setup rotarty contrast" + str(self.rotary.value()))

        elif self.shared_state.rotary_last_mode != "Show Settings" and self.shared_state.menu_options[self.shared_state.current_menu_position] == "Show Settings":
            self.rotary.set(value=self.shared_state.show_settings_line)
            self.previous_rotary_value = self.shared_state.show_settings_line
            self.rotary.set(min_val=0)
            self.rotary.set(max_val=35) #change to count of settings 
            self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
            self.shared_state.rotary_last_mode = "Show Settings"
            print("setup rotarty show settings" + str(self.rotary.value()))

        else:
            if self.shared_state.rotary_last_mode != "setpoint":
                self.rotary.set(value=self.shared_state.setpoint)
                self.previous_rotary_value = self.shared_state.setpoint
                self.rotary.set(min_val=1)
                self.rotary.set(max_val=self.shared_state.max_allowed_setpoint)  # Max temp - allow conversion to F?
                self.rotary.set(range_mode=RotaryIRQ.RANGE_BOUNDED)
                self.shared_state.rotary_last_mode = "setpoint"
                print("setup rotarty setpoint" + str(self.rotary.value()))

    def rotary_callback(self):
    
        if self.shared_state.in_menu:
            direction = 'up' if self.rotary.value() > self.previous_rotary_value else 'down'
            self.shared_state.rotary_direction = direction

        else:
            adjustment_rate = 10 if self.button_pressed else 0
            if self.rotary.value() > self.previous_rotary_value:
                self.rotary.set(value=self.rotary.value() + adjustment_rate)
            else:
                self.rotary.set(value=(self.rotary.value() - adjustment_rate))
            
            if self.shared_state.menu_options[self.shared_state.current_menu_position] == "Display Contrast":
                self.shared_state.display_contrast = self.rotary.value()
            elif self.shared_state.menu_options[self.shared_state.current_menu_position] == "Show Settings":
                self.shared_state.show_settings_line = self.rotary.value()
            else:
                self.shared_state.setpoint = self.rotary.value()

        self.previous_rotary_value = self.rotary.value()
        #print(f"{self.shared_state.rotary_last_mode} Prvious Rotary: {self.previous_rotary_value}, Rotary value: {self.rotary.value()}")
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

            if not self.click_check_timer.is_timer_running():
                self.click_check_timer.start()
        else: # Button is released
            self.rotary_used = False # Reset if rotary use between presses
            if self.button_pressed:
                print('Button released')
                self.button_pressed = False
                if not self.shared_state.in_menu and self.shared_state.get_mode() == 'Manual':
                    self.shared_state.set_mode("Off")
                    #print("Switching to Off mode")

    def check_click_count(self, timer):   
        if self.click_counter == 1:
            print('Single click detected')
            if not self.shared_state.in_menu and not self.rotary_used:
                print(str(self.shared_state.session_start_time))
                if self.shared_state.get_mode() == "Session":
                    if (self.shared_state.session_timeout - self.shared_state.get_session_mode_duration()) < 60000:
                        self.shared_state.session_start_time = self.shared_state.session_start_time + 60000

        elif self.click_counter == 2:
            print('Double click detected')
            if not self.shared_state.in_menu:
                self.shared_state.in_menu = True
                self.shared_state.rotary_direction = 'up' # Just Fake it and go to top of menu to force screen refresh
            else:
                #print('Ignoring double click already in menu')
                
        elif self.click_counter == 3:
            print('Triple click detected')
            if not self.shared_state.in_menu and not self.rotary_used:
                if self.shared_state.get_mode() == "Off" :
                    print("Switching to Session mode")
                    self.shared_state.set_mode("Session") 
                elif self.shared_state.get_mode() == "Session":
                    self.shared_state.set_mode("Off")
                    #print("Stopped Session mode")
                    
        elif self.click_counter == 4:
            print('Quadruple click detected')
            if not self.shared_state.in_menu and not self.rotary_used:
                if self.shared_state.get_mode() == "Off" :
                    print("Switching to Session mode for 1 minute")
                    self.shared_state.set_mode("Session") 
                    self.shared_state.session_start_time = (utime.ticks_ms() - (self.shared_state.session_timeout - 60000))
                #elif self.shared_state.get_mode() == "Session":
                #    self.shared_state.set_mode("Off")
        else:
            print(self.click_counter, ' clicks detected')
            
        self.click_counter = 0 # Reset the click counter
        if self.click_check_timer.is_timer_running():
            self.click_check_timer.stop()
            
        if self.button_pressed:
            print("Timer finished: Button still being held")
            if self.shared_state.get_mode() == 'Off' and not self.shared_state.in_menu and not self.rotary_used:
                self.shared_state.set_mode("Manual")
                print("Switching to Manual mode")
        else:
            self.rotary_used = False # Reset if rotary use between presses
            print("Timer finished: Button released")
