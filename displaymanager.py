import utime
import uasyncio as asyncio
#from customtimer import CustomTimer
from heaters import HeaterFactory, InductionHeater, ElementHeater

class DisplayManager:
    
    def __init__(self, display, shared_state):
    
        print("DisplayManager Initialising ...")
        self.display = display
        self.shared_state = shared_state
        self.display_heartbeat_y = 0
        self.growing = True
        self.scroll_position = 0
        self.display.contrast(self.shared_state.display_contrast)
        self.display.rotate(self.shared_state.display_rotate)

        self._home_task = None
        self._heartbeat_task_obj = None
        self._screen_task = None

        print("DisplayManager initialised.")


    def display_heartbeat(self):
        if self.growing:
            # Grow the rectangle from the top right corner
            self.display.fill_rect(127, 32 - self.display_heartbeat_y, 1, self.display_heartbeat_y + 1, 1)
            self.display_heartbeat_y += 1
            if self.display_heartbeat_y >= 32:
                self.display_heartbeat_y = 31 # Start shrinking
                self.growing = False
        else:
            # Shrink the rectangle from the bottom
            self.display.fill_rect(127, 32 - self.display_heartbeat_y, 1, self.display_heartbeat_y + 1, 1) # Ensure the rectangle is drawn before shrinking
            self.display.fill_rect(127, 32 - (self.display_heartbeat_y + 1), 1, 1, 0) # Clear the bottom pixel
            self.display_heartbeat_y -= 1
            if self.display_heartbeat_y <= 0:
                self.display_heartbeat_y = 0 # Reset to start growing again from the top
                self.growing = True
        self.display.show()


    async def _heartbeat_task(self, interval_ms=70):
        while True:
            try:
                # Only draw heartbeat on the home screen and when not in the menu
                if (not getattr(self.shared_state, 'in_menu', False)) and (getattr(self.shared_state, 'current_menu_position', 1) == 1):
                    self.display_heartbeat()
            except Exception:
                pass
            await asyncio.sleep_ms(interval_ms)

    def start_heartbeat(self, loop=None, interval_ms=70):
        if asyncio and loop is not None:
            self._heartbeat_task_obj = loop.create_task(self._heartbeat_task(interval_ms))
        else:
            self._heartbeat_task_obj = asyncio.get_event_loop().create_task(self._heartbeat_task(interval_ms))

    #async def _show_startup(self):
    #    # original blocking startup screen but async-friendly
    #    try:
    #        self.display.fill(0)

    #        self.display.text('MicroPython',  self.get_centered_text_start_position('MicroPython'), 0, 1)
    #        self.display.text('Heater', self.get_centered_text_start_position('Heater'), 8, 1)
    #        self.display.text('Controller', self.get_centered_text_start_position('Controller'), 16, 1)
    #        # Show currently loaded profile on last line
    #        profile_text = f"Profile: {self.shared_state.profile}"
    #        self.display.text(profile_text, self.get_centered_text_start_position(profile_text), 24, 1)
    #        self.display.show()
    #    except Exception:
    #        pass
    #    await asyncio.sleep_ms(2000)

    #def show_startup_screen(self):
    #    loop = asyncio.get_event_loop()
    #    loop.create_task(self._show_startup())
    #    return

    async def _home_task_fn(self, pid_components_getter, heater, interval_ms=200):
        while True:
            try:
                # Do not draw home screen while menu is active
                if getattr(self.shared_state, 'in_menu', False):
                    # yield/sleep to avoid busy loop
                    await asyncio.sleep_ms(interval_ms)
                    continue

                comps = pid_components_getter()
                self.show_screen_home_screen(comps, heater)
            except Exception:
                pass
            await asyncio.sleep_ms(interval_ms)

    def start_home(self, pid_components_getter, heater, loop=None, interval_ms=200):
        if self._home_task is not None:
            return
        try:
            if loop is None:
                loop = asyncio.get_event_loop()
            self._home_task = loop.create_task(self._home_task_fn(pid_components_getter, heater, interval_ms))
        except Exception:
            self._home_task = None

    def stop_home(self):
        try:
            if self._home_task is not None:
                self._home_task.cancel()
        except Exception:
            pass
        self._home_task = None
        # Cancel any on-screen screen task (e.g. graphs) when stopping home updates
        try:
            if self._screen_task is not None:
                self._screen_task.cancel()
        except Exception:
            pass
        self._screen_task = None


    def fill_display(self, text, x=0, y=0, invert=False):
        self.display.fill(0)
        self.display.text(text, x, y, 1)
        if invert:
            self.display.invert(True)
        self.display.show()
        if invert:
            self.display.invert(False)


    async def _display_error(self, message, duration=5, show_countdown=False):
        message_length = len(message) * 8 # Assuming each character is 8 pixels wide
        start_time = utime.ticks_ms()
        scroll_speed = 20 # Time in milliseconds to wait before moving to the next character
        message_scroll_position = 0
        message_display_time = (message_length + (128*8)) * scroll_speed # Total time to display the message

        while utime.ticks_diff(utime.ticks_ms(), start_time) < message_display_time:
            try:
                self.display.fill(0) # Clear the display

                # Scrolling logic for the message
                self.display.text(message, message_scroll_position, 12, 1)
                message_scroll_position -= 1
                if message_scroll_position < -message_length:
                    message_scroll_position = 128

                if show_countdown:
                    elapsed_time = utime.ticks_diff(utime.ticks_ms(), start_time) / 1000 # Convert to seconds
                    remaining_time = duration - elapsed_time
                    countdown_text = f"{int(remaining_time)}s"
                    countdown_length = len(countdown_text) * 8 
                    # Calculate the starting position for the countdown to center it
                    countdown_start_position = (128 - countdown_length) // 2
                    self.display.text(countdown_text, countdown_start_position, 24, 1)

                self.display.show()
            except Exception:
                pass

            await asyncio.sleep_ms(scroll_speed)

        try:
            self.display.fill(0)
            self.display.show()
        except Exception:
            pass


    def display_error(self, message, duration=5, show_countdown=False):
        loop = asyncio.get_event_loop()
        loop.create_task(self._display_error(message, duration, show_countdown))
        return


    def show_startup_screen(self):
        # Clear the display and show the first set of messages
        self.display.fill(0) 

        self.display.text('MicroPython',  self.get_centered_text_start_position('MicroPython'), 0, 1)
        self.display.text('Heater', self.get_centered_text_start_position('Heater'), 8, 1)
        self.display.text('Controller', self.get_centered_text_start_position('Controller'), 16, 1)
        profile_text = self.shared_state.profile
        self.display.text(profile_text, self.get_centered_text_start_position(profile_text), 24, 1)

        self.display.show()
        utime.sleep_ms(2000) # Wait for 2 seconds to display the first set of messages

    def show_watchdog_off_screen(self):
        # Clear the display and show the first set of messages
        self.display.fill(0) 

        self.display.text('Warning',  self.get_centered_text_start_position('Warning'), 0, 1)
        self.display.text('Watchdog', self.get_centered_text_start_position('Watchdog'), 8, 1)
        self.display.text('OFF', self.get_centered_text_start_position('OFF'), 16, 1)
        self.display.show()
        utime.sleep_ms(2000) # Wait for 2 seconds to display the first set of messages

    def show_screen_graph_bar(self):

        self.display.fill(0)

        temperature_readings = self.shared_state.temperature_readings
        if not temperature_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return
        
        # Calculate min and max temperatures once
        min_temp = min(temperature_readings.values())
        max_temp = max(temperature_readings.values())
        temp_range = max_temp - min_temp
        if temp_range == 0: temp_range = 1
        display_height = self.display.height

        # Calculate min and max times once
        min_time = min(temperature_readings.keys())
        max_time = max(temperature_readings.keys())
        x_range = max_time - min_time
        if x_range == 0: x_range = 1
        
        x_scale = self.display.width / x_range
        y_scale = display_height / temp_range

        for time, temp in temperature_readings.items():
            x = int((time - min_time) * x_scale)
            y = display_height - int((temp - min_temp) * y_scale)

            # Draw a rectangle for each temperature reading
            self.display.fill_rect(x, y, 1, int(temp * y_scale), 1)

        last_time, last_temp = max(temperature_readings.items(), key=lambda item: item[0])

        #last_temp_str = f"{last_temp:.1f}" # Adjust the precision as needed
        last_temp_str = str(last_temp) + "C"

        #text_x = self.display.width - len(last_temp_str) * 6 # Adjust the multiplier based on the text size
        #text_y = self.display.height - 8 # Adjust the offset based on the text size

        t = last_temp_str
        # Now have an LED to indicate we are in session/manual mode so lets save screen space
        #if self.shared_state.get_mode() == "Session":
        #    t = t + " Session: " + str(int((self.shared_state.session_timeout - self.shared_state.get_session_mode_duration())/1000))
        self.display.text(t, 0, 0, 1)
        
        text_x = 104  #Assuming 128 pix wide 
        if(last_temp > 99): text_x = 98
        self.display.text(last_temp_str, text_x, 24, 0)  # invert temp 

        self.display.show()

        
    def show_screen_graph_line(self):
        self.display.fill(0)

        temperature_readings = self.shared_state.temperature_readings
        if not temperature_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return

        min_time = min(temperature_readings.keys())
        max_time = max(temperature_readings.keys())
        x_range = max_time - min_time
        if x_range == 0: x_range = 1

        x_scale = self.display.width / x_range

        for time, temp in temperature_readings.items():
            x = int((time - min_time) * x_scale)
            y = self.display.height - int(temp / 10) # Adjust the y-coordinate to represent each pixel as 10°C

            # Draw a single pixel for each temperature reading
            self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        last_time, last_temp = max(temperature_readings.items(), key=lambda item: item[0])
        last_temp_str = str(last_temp) + "C"

        # Draw dotted setpoint line
        setpoint_y = self.display.height - int(self.shared_state.setpoint / 10) # Calculate the y-coordinate for the checkpoint
        dot_spacing = 4 # Adjust this value to change the spacing between dots
        for x in range(0, self.display.width, dot_spacing):
            self.display.pixel(x, setpoint_y, 1) 
            
        # Display the last temperature reading and other information
        t = last_temp_str
        # Now have an LED to indicate we are in session/manual mode so lets save screen space
        #if self.shared_state.get_mode() == "Session":
        #    t = t + " Session: " + str(int((self.shared_state.session_timeout - self.shared_state.get_session_mode_duration())/1000))
        self.display.text(t, 0, 0, 1)

        self.display.show()
            
    def show_screen_graph_setpoint(self):
        self.display.fill(0)

        temperature_readings = self.shared_state.temperature_readings
        if not temperature_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return

        setpoint = self.shared_state.setpoint
        display_height = self.display.height
        zoom_range = 15 # This range is not used in the adjusted method

        setpoint_y = display_height // 2 # Setpoint is in the middle of the screen

        for time, temp in temperature_readings.items():
            x = int((time - min(temperature_readings.keys())) * (self.display.width / (max(temperature_readings.keys()) - min(temperature_readings.keys()))))
            # Calculate the y-coordinate relative to the setpoint
            y = (setpoint_y + (temp - setpoint) * -1)
            # Ensure y-coordinate does not go below 0 or above the display height
            #y = max(min(y, display_height - 1), 0)
            if abs(temp - setpoint) < zoom_range:
                self.display.pixel(x, y, 1) # Draw the pixel

        # Draw dotted setpoint line
        dot_spacing = 4
        counter = 0
        for x in range(0, self.display.width, 1):
            if counter < 2: # Draw on pixels for the first 2 iterations
                self.display.pixel(x, setpoint_y, 1) # Draw an on pixel
            counter += 1 # Increment the counter
            if counter == 4: # Reset the counter after drawing 2 on and 2 off pixels
                counter = 0
#        for x in range(0, self.display.width, dot_spacing):
#            self.display.pixel(x, setpoint_y, 1)

        last_time, last_temp = max(temperature_readings.items(), key=lambda item: item[0])
        t = str(last_temp) + "C"

        # Now have an LED to indicate we are in session/manual mode so lets save screen space
        #if self.shared_state.get_mode() == "Session":
        #    t = t + " Session: " + str(int((self.shared_state.session_timeout - self.shared_state.get_session_mode_duration())/1000))

        self.display.text(t, 0, 0, 1)
        
        t = "SP:" + str(self.shared_state.setpoint) + "C"
        self.display.text(t, 0, 24, 1)
        
        self.display.show()


    def show_screen_temp_watts_line(self):
        self.display.fill(0)

        watt_readings = self.shared_state.watt_readings
        if not watt_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return

        temperature_readings = self.shared_state.temperature_readings
        if not temperature_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return

        min_time = min(watt_readings.keys())
        max_time = max(watt_readings.keys())
        x_range = max_time - min_time
        if x_range == 0: x_range = 1

        x_scale = self.display.width / x_range
        y_scale = self.shared_state.max_watts / self.display.height
        for time, watt in watt_readings.items():
            x = int((time - min_time) * x_scale)
            y = self.display.height - int(watt / y_scale) # Adjust the y-coordinate to represent each pixel as 10W

            # Draw a single pixel for each watt reading
            self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        last_time, last_watt = max(watt_readings.items(), key=lambda item: item[0])
        last_watts_str = str(last_watt) + "W"


        min_time = min(temperature_readings.keys())
        max_time = max(temperature_readings.keys())
        x_range = max_time - min_time
        if x_range == 0: x_range = 1

        x_scale = self.display.width / x_range

        for time, temp in temperature_readings.items():
            x = int((time - min_time) * x_scale)
            y = self.display.height - int(temp / 10) # Adjust the y-coordinate to represent each pixel as 10°C

            # Draw a dotted line
            if(x % 2) == 0:
                self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        last_time, last_temp = max(temperature_readings.items(), key=lambda item: item[0])
        last_temp_str = str(last_temp) + "C"

        # Draw dotted setpoint line
        setpoint_y = self.display.height - int(self.shared_state.setpoint / 10) # Calculate the y-coordinate for the checkpoint
        dot_spacing = 4 # Adjust this value to change the spacing between dots
        for x in range(0, self.display.width, dot_spacing):
            self.display.pixel(x, setpoint_y, 1) 
            
        t = last_temp_str + " " + last_watts_str
        self.display.text(t, 0, 0, 1)

        self.display.show()
        

    def show_screen_watts_line(self):
        self.display.fill(0)

        watt_readings = self.shared_state.watt_readings
        if not watt_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return

        min_time = min(watt_readings.keys())
        max_time = max(watt_readings.keys())
        x_range = max_time - min_time
        if x_range == 0: x_range = 1

        x_scale = self.display.width / x_range
        y_scale = self.shared_state.max_watts / self.display.height
        for time, watt in watt_readings.items():
            x = int((time - min_time) * x_scale)
            y = self.display.height - int(watt / y_scale) # Adjust the y-coordinate to represent each pixel as 10W

            # Draw a single pixel for each watt reading
            self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        last_time, last_watt = max(watt_readings.items(), key=lambda item: item[0])
        last_watts_str = str(last_watt) + "W"

        # Draw dotted setpoint line
#        setpoint_y = self.display.height - int(self.shared_state.setpoint / 10) # Calculate the y-coordinate for the checkpoint
#       dot_spacing = 4 # Adjust this value to change the spacing between dots
#        for x in range(0, self.display.width, dot_spacing):
#            self.display.pixel(x, setpoint_y, 1) 
            
        # Display the last watt reading and other information
        t = last_watts_str
        self.display.text(t, 0, 0, 1)

        self.display.show()
        

    def show_screen_display_contrast(self):
        self.display.contrast(self.shared_state.display_contrast)  # Set contast to current value
        self.show_standard_screen("Display Contrast",str(self.shared_state.display_contrast))
        
    def show_standard_screen(self,text,value):
        self.display.fill(0)
        self.display.text(text,  self.get_centered_text_start_position(text), 0, 1)
        self.display.text(value, self.get_centered_text_start_position(value), 10, 1)
        self.display.show()
        #utime.sleep_ms(5000)
        #self.shared_state.current_menu_position = 1 # Set next sceen to Main 
    

    def get_centered_text_start_position(self, text):
        display_width = self.display.width
        text_width = len(text) * 6
        return (display_width - text_width) // 2


    def show_screen_home_screen(self, pid_components, heater):
        self.display.fill(0)
        shared_state = self.shared_state

        if self.shared_state.control == 'watts':
            t = "P: " + str(shared_state.watts) + "W (" + str(int(shared_state.setwatts)) + "W)"
            self.display.text(t, 0, 0)
            t = "V: " + "{:.1f}".format(shared_state.input_volts) + "V"
            if shared_state.temperature_units == 'F':
                t = t + " T: " + str(int(32 + (1.8 * shared_state.heater_temperature))) + "F"
            else:
                t = t + " T: " + str(int(shared_state.heater_temperature)) + "C"
            self.display.text(t, 0, 8)
        else:
            if shared_state.temperature_units == 'F':
                t = "T: " + str(int(32 + (1.8 * shared_state.heater_temperature))) + "F (" + str(int(32 + (1.8 * shared_state.setpoint))) + "F)"
            else:
                t = "T: " + str(int(shared_state.heater_temperature)) + "C (" + str(int(shared_state.setpoint)) + "C)"
            self.display.text(t, 0, 0)
            t = "V: " + "{:.1f}".format(shared_state.input_volts) + "V"
            if isinstance(heater, ElementHeater):
                t = t + " P: " + str(shared_state.watts) + "W"
            self.display.text(t, 0, 8)



        t = "M: " + shared_state.get_mode()
        if shared_state.get_mode() == "Session":
            t = t + " " + str(int((shared_state.session_timeout - shared_state.get_session_mode_duration())/1000)) + "s"

        # Add PI temperature to menu somewhere
        #pi_temperature = shared_state.get_pi_temperature()
        #if shared_state.temperature_units == 'F':
        #    t = "Mode: " + str(int(32 + (1.8 * pi_temperature))) + "F"
        #else:
        #    t = "Mode: " + str(int(pi_temperature)) + "C"
        
        self.display.text(t, 0, 16)
        if self.shared_state.control == 'pid':
            p, i, d = pid_components
            if d > 0:
                t = "{:d} {:d} {:d}".format(int(p), int(i), int(d))
            else:
                t = "{:d} {:d}".format(int(p), int(i))
            if heater.is_on() and isinstance(heater, ElementHeater):
                t = t + " P: " + "{:.d}".format(int(heater.get_power()))
                
            self.display.text(t, 0, 24)

    def show_screen_show_settings(self):
        self.display.fill(0)
        
        exclude_vars = {'temperature_readings','input_volts_readings','watt_readings','menu_options','error_messages'}  
        vars_dict = {k: v for k, v in self.shared_state.__dict__.items() if k not in exclude_vars}        
        vars_dict = dict(vars_dict.items())
        
        items_list = list(vars_dict.items())
        items_list = sorted(items_list, key=lambda x: x[0])
        if self.shared_state.show_settings_line < len(items_list):
            current_item = items_list[self.shared_state.show_settings_line]
            var_name, value = current_item
        else:
            var_name = "End"
            value = self.shared_state.show_settings_line
            #self.shared_state.show_settings_line = 0 #reset

        display_text = f"{var_name}: {value}"

        # Calculate text dimensions
        max_lines = 4    # Screen can show 4 lines
        chars_per_line = 16  # Characters that fit per line (128/8)
        
        # Split text into lines
        words = display_text.split()
        lines = []
        current_line = ""
            
        # Build lines word by word
        for word in words:
            if len(current_line) + len(word) + 1 <= chars_per_line:
                current_line += " " + word if current_line else word
            else:
                lines.append(current_line)
                current_line = word
                if len(lines) >= max_lines:
                    break
        
        if current_line and len(lines) < max_lines:
            lines.append(current_line)        

        for i, line in enumerate(lines):
            if i < max_lines:
                self.display.text(line, 0, i * 8, 1)

        self.display.show()

    
    def show_screen_profiles(self):
        self.display.fill(0)
        
        profile_list = self.shared_state.profile_list
        if not profile_list:
            self.display.text("No profiles", 0, 0, 1)
            self.display.text("found", 0, 8, 1)
            self.display.show()
            return
        
        # Get current profile name
        idx = self.shared_state.profile_selection_index
        if idx >= len(profile_list):
            idx = len(profile_list) - 1
            self.shared_state.profile_selection_index = idx
        
        profile_name = profile_list[idx]
        position_text = f"{idx + 1}/{len(profile_list)}"
        #print("Profile:", profile_name, "Position:", position_text)
        # Display profile name
        display_text = f"{profile_name}"
        
        # Show on first line
        self.display.text(display_text, 0, 0, 1)
        
        # Show position on second line  
        self.display.text(position_text, 0, 8, 1)
        
        self.display.show()


    def show_screen_menu(self):
        #print("DisplayManager: show_screen_menu() called")
        self.display.fill(0)

        # Calculate the range to ensure the selected option is always in the middle
        # Adjust the range based on the current menu position
        if self.shared_state.current_menu_position == 0:
            start_index = 0
            end_index = min(3, len(self.shared_state.menu_options))
        elif self.shared_state.current_menu_position == len(self.shared_state.menu_options) - 1:
            start_index = max(0, len(self.shared_state.menu_options) - 3)
            end_index = len(self.shared_state.menu_options)
        else:
            start_index = self.shared_state.current_menu_position - 1
            end_index = self.shared_state.current_menu_position + 2

        # Display the options within the calculated range
        for i in range(start_index, end_index):
            y_position = (i - start_index) * 8
            if i == self.shared_state.current_menu_position:
                # Simulate boldness by displaying the text twice, slightly offset
                self.display.text(self.shared_state.menu_options[i], 0, y_position, 1)
                self.display.text(self.shared_state.menu_options[i], 1, y_position, 1)   # Pretend bold
                self.display.text(self.shared_state.menu_options[i], 1, y_position+1, 1) # Pretend bold
            else:
                self.display.text(self.shared_state.menu_options[i], 0, y_position, 1)

        self.display.show()




    def display_screen(self, option):
        method_name = f"show_screen_{option}"
        method = getattr(self, method_name, None)
        if method:
            # Keep graph-like and interactive screens displayed in a small async loop so they yield
            graph_options = {'graph_bar', 'graph_line', 'graph_setpoint', 'temp_watts_line', 'watts_line', 'profiles', 'show_settings'}
            #if asyncio and option in graph_options:
            if option in graph_options:
                try:
                    loop = asyncio.get_event_loop()
                    # Cancel any existing screen task
                    try:
                        if self._screen_task is not None:
                            self._screen_task.cancel()
                    except Exception:
                        pass

                    # Draw once immediately
                    method()

                    async def _screen_loop():
                        while getattr(self.shared_state, 'current_menu_position', 1) > 1 and not getattr(self.shared_state, 'in_menu', False):
                            try:
                                method()
                            except Exception:
                                pass

                            await asyncio.sleep_ms(300)

                    self._screen_task = loop.create_task(_screen_loop())
                    return
                except Exception:
                    # scheduling failed; fall back to single draw
                    pass
            # default: single synchronous draw
            method()
