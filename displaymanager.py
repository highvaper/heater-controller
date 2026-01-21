import utime
import uasyncio as asyncio
from machine import reset
#from customtimer import CustomTimer
from heaters import HeaterFactory, InductionHeater, ElementHeater

class DisplayManager:
    # Default display dimensions (can be overridden by driver classes)
    width = 128
    height = 32
    
    def __init__(self, display, shared_state):
    
        print("DisplayManager Initialising ...")
        self.display = display
        self.shared_state = shared_state
        
        # Get display dimensions from driver class attributes
        self.display_width = self.__class__.width
        self.display_height = self.__class__.height
        
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
        max_x = self.display_width - 1
        max_y = self.display_height
        if self.growing:
            # Grow the rectangle from the top right corner
            self.display.fill_rect(max_x, max_y - self.display_heartbeat_y, 1, self.display_heartbeat_y + 1, 1)
            self.display_heartbeat_y += 1
            if self.display_heartbeat_y >= max_y:
                self.display_heartbeat_y = max_y - 1 # Start shrinking
                self.growing = False
        else:
            # Shrink the rectangle from the bottom
            self.display.fill_rect(max_x, max_y - self.display_heartbeat_y, 1, self.display_heartbeat_y + 1, 1) # Ensure the rectangle is drawn before shrinking
            self.display.fill_rect(max_x, max_y - (self.display_heartbeat_y + 1), 1, 1, 0) # Clear the bottom pixel
            self.display_heartbeat_y -= 1
            if self.display_heartbeat_y <= 0:
                self.display_heartbeat_y = 0 # Reset to start growing again from the top
                self.growing = True
        self.display.show()


    async def _heartbeat_task(self, interval_ms=70):
        while True:
            try:
                # Only draw heartbeat on the home screen and when not in the menu, no errors showing, and temporary_max_watts screen not active
                if (not getattr(self.shared_state, 'in_menu', False)) and (getattr(self.shared_state, 'current_menu_position', 1) == 1) and (not self.shared_state.has_error()) and (not getattr(self.shared_state, 'temporary_max_watts_screen_active', False)):
                    self.display_heartbeat()
            except Exception:
                pass
            await asyncio.sleep_ms(interval_ms)

    def start_heartbeat(self, loop=None, interval_ms=70):
        if asyncio and loop is not None:
            self._heartbeat_task_obj = loop.create_task(self._heartbeat_task(interval_ms))
        else:
            self._heartbeat_task_obj = asyncio.get_event_loop().create_task(self._heartbeat_task(interval_ms))


    async def _home_task_fn(self, heater, interval_ms=200):
        while True:
            try:
                # Do not draw home screen while menu is active
                if getattr(self.shared_state, 'in_menu', False):
                    # yield/sleep to avoid busy loop
                    await asyncio.sleep_ms(interval_ms)
                    continue

                self.show_screen_home_screen(heater)
            except Exception:
                pass
            await asyncio.sleep_ms(interval_ms)

    def start_home(self, heater, loop=None, interval_ms=200):
        if self._home_task is not None:
            return
        try:
            if loop is None:
                loop = asyncio.get_event_loop()
            self._home_task = loop.create_task(self._home_task_fn(heater, interval_ms))
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
        # Reset screen option tracking so async tasks are recreated when returning
        if hasattr(self, '_current_screen_option'):
            delattr(self, '_current_screen_option')


    def fill_display(self, text, x=0, y=0, invert=False):
        self.display.fill(0)
        self.display.text(text, x, y, 1)
        if invert:
            self.display.invert(True)
        self.display.show()
        if invert:
            self.display.invert(False)


    def show_startup_screen(self):
        # Clear the display and show the first set of messages
        self.display.fill(0) 

        self.display.text('MicroPython',  self.get_centered_text_start_position('MicroPython'), 0, 1)
        self.display.text('Heater', self.get_centered_text_start_position('Heater'), 8, 1)
        profile_text = self.shared_state.profile
        self.display.text(profile_text, self.get_centered_text_start_position(profile_text), 16, 1)
        hardware_text = self.shared_state.hardware
        self.display.text(hardware_text, self.get_centered_text_start_position(hardware_text), 24, 1)

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

    def show_low_disk_space_screen(self, free_kb):
        # Flash the low disk space warning
        for _ in range(6):  # Flash 5 times
            # Show warning
            self.display.fill(0)
            self.display.text('Warning',  self.get_centered_text_start_position('Warning'), 0, 1)
            self.display.text('Low Disk', self.get_centered_text_start_position('Low Disk'), 8, 1)
            free_text = str(int(free_kb)) + 'KB'
            self.display.text(free_text, self.get_centered_text_start_position(free_text), 16, 1)
            self.display.show()
            utime.sleep_ms(1500)
            
            # Clear screen
            self.display.fill(0)
            self.display.show()
            utime.sleep_ms(800)

    def show_error(self):
        """Display current error on screen."""
        if not self.shared_state.has_error():
            return
        
        error_code, error_message = self.shared_state.current_error
        self.display.fill(0)
        
        # Display error code
        self.display.text("ERROR", self.get_centered_text_start_position("ERROR"), 0, 1)
        
        # Display error message with word wrapping
        max_lines = 3
        chars_per_line = 16
        words = error_message.split()
        lines = []
        current_line = ""
        
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
                self.display.text(line, 0, 8 + (i * 8), 1)
        
        self.display.show()

    def show_screen_graph_bar(self):

        self.display.fill(0)

        temperature_readings = self.shared_state.temperature_readings
        if not temperature_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return
        
        # Calculate min and max temperatures once
        min_temp = min(temperature_readings)
        max_temp = max(temperature_readings)
        temp_range = max_temp - min_temp
        if temp_range == 0: temp_range = 1
        display_height = self.display_height

        # Scale based on number of readings
        x_scale = self.display_width / len(temperature_readings)
        y_scale = display_height / temp_range

        for i, temp in enumerate(temperature_readings):
            x = int(i * x_scale)
            y = display_height - int((temp - min_temp) * y_scale)

            # Draw a rectangle for each temperature reading
            self.display.fill_rect(x, y, 1, int(temp * y_scale), 1)

        # Last reading is at the end of deque
        last_temp = temperature_readings[-1]

        #last_temp_str = f"{last_temp:.1f}" # Adjust the precision as needed
        last_temp_str = str(last_temp) + "C"

        #text_x = self.display.width - len(last_temp_str) * 6 # Adjust the multiplier based on the text size
        #text_y = self.display.height - 8 # Adjust the offset based on the text size

        t = last_temp_str
        # Now have an LED to indicate we are in session/manual mode so lets save screen space
        #if self.shared_state.get_mode() == "Session":
        #    t = t + " Session: " + str(int((self.shared_state.session_timeout - self.shared_state.get_session_mode_duration())/1000))
        self.display.text(t, 0, 0, 1)
        
        text_x = self.display_width - 24  # Position near right edge
        if(last_temp > 99): text_x = self.display_width - 30
        self.display.text(last_temp_str, text_x, self.display_height - 8, 0)  # invert temp 

        self.display.show()

        
    def show_screen_graph_line(self):
        self.display.fill(0)

        temperature_readings = self.shared_state.temperature_readings
        if not temperature_readings:
            self.display.text("No data yet", 0, 0, 1)
            self.display.show()
            return

        x_scale = self.display_width / len(temperature_readings)

        for i, temp in enumerate(temperature_readings):
            x = int(i * x_scale)
            y = self.display_height - int(temp / 10) # Adjust the y-coordinate to represent each pixel as 10°C

            # Draw a single pixel for each temperature reading
            self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        # Last reading is at the end of deque
        last_temp = temperature_readings[-1]
        last_temp_str = str(last_temp) + "C"

        # Draw setpoint line from readings (shows historical changes)
        setpoint_readings = self.shared_state.temperature_setpoint_readings
        if setpoint_readings:
            x_scale_setpoint = self.display_width / len(setpoint_readings)
            dot_spacing = 4  # Draw every 4th pixel for dotted line
            for i, setpoint in enumerate(setpoint_readings):
                x = int(i * x_scale_setpoint)
                # Only draw at dotted intervals
                if x % dot_spacing == 0:
                    setpoint_y = self.display_height - int(setpoint / 10)
                    if 0 <= setpoint_y < self.display_height:
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

        setpoint = self.shared_state.temperature_setpoint
        display_height = self.display_height
        zoom_range = 15 # This range is not used in the adjusted method

        setpoint_y = display_height // 2 # Setpoint is in the middle of the screen

        x_scale = self.display_width / len(temperature_readings) if temperature_readings else 1
        for i, temp in enumerate(temperature_readings):
            x = int(i * x_scale)
            # Calculate the y-coordinate relative to the setpoint
            y = int(setpoint_y + (temp - setpoint) * -1)
            # Ensure y-coordinate does not go below 0 or above the display height
            #y = max(min(y, display_height - 1), 0)
            if abs(temp - setpoint) < zoom_range:
                self.display.pixel(x, y, 1) # Draw the pixel

        # Draw setpoint line from readings (shows historical changes)
        setpoint_readings = self.shared_state.temperature_setpoint_readings
        if setpoint_readings:
            x_scale_setpoint = self.display_width / len(setpoint_readings)
            dot_spacing = 4  # Draw every 4th pixel for dotted line
            for i, sp in enumerate(setpoint_readings):
                x = int(i * x_scale_setpoint)
                # Only draw at dotted intervals
                if x % dot_spacing == 0:
                    # Calculate y relative to center (setpoint_y)
                    sp_y = int(setpoint_y + (sp - setpoint) * -1)
                    if 0 <= sp_y < display_height:
                        self.display.pixel(x, sp_y, 1)
#        for x in range(0, self.display.width, dot_spacing):
#            self.display.pixel(x, setpoint_y, 1)

        # Last reading is at the end of deque
        last_temp = temperature_readings[-1] if temperature_readings else 0
        t = str(last_temp) + "C"

        # Now have an LED to indicate we are in session/manual mode so lets save screen space
        #if self.shared_state.get_mode() == "Session":
        #    t = t + " Session: " + str(int((self.shared_state.session_timeout - self.shared_state.get_session_mode_duration())/1000))

        self.display.text(t, 0, 0, 1)
        
        t = "SP:" + str(self.shared_state.temperature_setpoint) + "C"
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

        x_scale = self.display_width / len(watt_readings)
        y_scale = self.shared_state.max_watts / self.display_height
        for i, watt in enumerate(watt_readings):
            x = int(i * x_scale)
            y = self.display_height - int(watt / y_scale) # Adjust the y-coordinate to represent each pixel as 10W

            # Draw a single pixel for each watt reading
            self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        # Last reading is at the end of deque
        last_watt = watt_readings[-1]
        last_watts_str = str(last_watt) + "W"

        x_scale = self.display_width / len(temperature_readings)

        for i, temp in enumerate(temperature_readings):
            x = int(i * x_scale)
            y = self.display_height - int(temp / 10) # Adjust the y-coordinate to represent each pixel as 10°C

            # Draw a dotted line
            if(x % 2) == 0:
                self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        # Last reading is at the end of deque
        last_temp = temperature_readings[-1]
        last_temp_str = str(last_temp) + "C"

        # Draw setpoint line from readings (shows historical changes)
        setpoint_readings = self.shared_state.temperature_setpoint_readings
        if setpoint_readings:
            x_scale_setpoint = self.display_width / len(setpoint_readings)
            dot_spacing = 4  # Draw every 4th pixel for dotted line
            for i, setpoint in enumerate(setpoint_readings):
                x = int(i * x_scale_setpoint)
                # Only draw at dotted intervals
                if x % dot_spacing == 0:
                    setpoint_y = self.display_height - int(setpoint / 10)
                    if 0 <= setpoint_y < self.display_height:
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

        x_scale = self.display_width / len(watt_readings)
        y_scale = self.shared_state.max_watts / self.display_height
        for i, watt in enumerate(watt_readings):
            x = int(i * x_scale)
            y = self.display_height - int(watt / y_scale) # Adjust the y-coordinate to represent each pixel as 10W

            # Draw a single pixel for each watt reading
            self.display.pixel(x, y, 1) # Assuming 1 is the color for the pixel

        # Last reading is at the end of deque
        last_watt = watt_readings[-1]
        last_watts_str = str(last_watt) + "W"

        # Draw dotted setpoint line
#        setpoint_y = self.display.height - int(self.shared_state.temperature_setpoint / 10) # Calculate the y-coordinate for the checkpoint
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

    def show_screen_temporary_max_watts(self):
        self.show_standard_screen("Temporary Max Watts",str(self.shared_state.temporary_max_watts) + "W")
        
    def show_standard_screen(self,text,value):
        self.display.fill(0)
        self.display.text(text,  self.get_centered_text_start_position(text), 0, 1)
        self.display.text(value, self.get_centered_text_start_position(value), 10, 1)
        self.display.show()
        #utime.sleep_ms(5000)
        #self.shared_state.current_menu_position = 1 # Set next sceen to Main 
    

    def get_centered_text_start_position(self, text):
        display_width = self.display_width
        text_width = len(text) * 6
        return (display_width - text_width) // 2


    def show_screen_home_screen(self, heater):
        self.display.fill(0)
        shared_state = self.shared_state

        if self.shared_state.control == 'watts':
            t = "P: " + str(shared_state.watts) + "W (" + str(int(shared_state.set_watts)) + "W)"
            self.display.text(t, 0, 0)
            t = "V: " + "{:.1f}".format(shared_state.input_volts) + "V"
            if shared_state.temperature_units == 'F':
                t = t + " T: " + str(int(32 + (1.8 * shared_state.heater_temperature))) + "F"
            else:
                t = t + " T: " + str(int(shared_state.heater_temperature)) + "C"
            self.display.text(t, 0, 8)
        elif self.shared_state.control == 'duty_cycle':
            # Show duty-cycle: use integer display when set value > 10%,
            # otherwise show one decimal (0.1% resolution).
            if shared_state.set_duty_cycle > 10:
                t = "DC: {}% ({}%)".format(int(heater.get_power()), int(shared_state.set_duty_cycle))
            else:
                t = "DC: {:.1f}% ({:.1f}%)".format(heater.get_power(), shared_state.set_duty_cycle)            
            self.display.text(t, 0, 0)
            t = "V: " + "{:.1f}".format(shared_state.input_volts) + "V"
            if shared_state.temperature_units == 'F':
                t = t + " T: " + str(int(32 + (1.8 * shared_state.heater_temperature))) + "F"
            else:
                t = t + " T: " + str(int(shared_state.heater_temperature)) + "C"
            self.display.text(t, 0, 8)
        else:
            if shared_state.temperature_units == 'F':
                t = "T: " + str(int(32 + (1.8 * shared_state.heater_temperature))) + "F (" + str(int(32 + (1.8 * shared_state.temperature_setpoint))) + "F)"
            else:
                t = "T: " + str(int(shared_state.heater_temperature)) + "C (" + str(int(shared_state.temperature_setpoint)) + "C)"
            self.display.text(t, 0, 0)
            t = "V: " + "{:.1f}".format(shared_state.input_volts) + "V"
            if isinstance(heater, ElementHeater):
                t = t + " P: " + str(shared_state.watts) + "W"
            self.display.text(t, 0, 8)



        t = "M: " + shared_state.get_mode()
        if shared_state.get_mode() == "autosession":
            # Show Auto Session with profile name
            if shared_state.autosession_profile_name:
                t = "M: " + shared_state.autosession_profile_name
            else:
                t = "M: Auto Session"
        elif shared_state.get_mode() == "Session":
            if shared_state.session_timeout is not None and shared_state.session_timeout > 0:
                t = t + " " + str(int((shared_state.session_timeout - shared_state.get_session_mode_duration())/1000)) + "s"
        self.display.text(t, 0, 16)

        if self.shared_state.control == 'temperature_pid':
            if shared_state.get_mode() == "autosession":
                # When autosession is running, display elapsed and remaining time
                elapsed_ms = utime.ticks_diff(utime.ticks_ms(), shared_state.autosession_start_time)
                elapsed_ms = max(0, elapsed_ms)  # Clamp to 0
                elapsed_s = int(elapsed_ms / 1000)
                remaining_ms = shared_state.autosession_profile.get_duration_ms() - elapsed_ms
                remaining_s = max(0, int(remaining_ms / 1000))
                t = str(elapsed_s) + "s/" + str(remaining_s) + "s"
            else:
                # Normal PID stats display
                p, i, d = self.shared_state.pid.components
                if d > 0:
                    t = "{:d} {:d} {:d}".format(int(p), int(i), int(d))
                else:
                    t = "{:d} {:d}".format(int(p), int(i))
                if heater.is_on() and isinstance(heater, ElementHeater):
                    t = t + " P: " + "{:.d}".format(int(heater.get_power()))
                    
            self.display.text(t, 0, 24)

    def show_screen_show_settings(self):
        self.display.fill(0)
        
        vars_dict = dict(self.shared_state.__dict__.items())        
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
        display_text = f"{profile_name}"
        
        # Show on first line
        self.display.text(display_text, 0, 0, 1)
        
        # Show position on second line  
        self.display.text(position_text, 0, 8, 1)
        
        self.display.show()

    def show_screen_autosession_profiles(self):
        self.display.fill(0)
        autosession_list = self.shared_state.autosession_profile_list
        if not autosession_list:
            self.display.text("No autosession", 0, 0, 1)
            self.display.text("profiles found", 0, 8, 1)
            self.display.show()
            return
        idx = self.shared_state.autosession_profile_selection_index
        if idx >= len(autosession_list):
            idx = len(autosession_list) - 1
            self.shared_state.autosession_profile_selection_index = idx
        profile_name = autosession_list[idx]
        position_text = f"{idx + 1}/{len(autosession_list)}"
        display_text = f"{profile_name}"
        self.display.text(display_text, 0, 0, 1)
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


    def show_screen_start_autosession(self):
        """Start autosession, update menu, and return to home screen."""
        if self.shared_state.autosession_profile:
            self.shared_state.set_mode("autosession")
        self.shared_state.update_menu_options()
        self.shared_state.current_menu_position = 0  # Reset to Home Screen
        self.display.fill(0)
        self.display.text("Starting Autosession...", 0, 16)
        self.display.show()
        utime.sleep_ms(500)

    def show_screen_stop_autosession(self):
        """Stop autosession, update menu, and return to home screen."""
        self.shared_state.set_mode("Off")
        self.shared_state.update_menu_options()
        self.shared_state.current_menu_position = 0  # Reset to Home Screen
        self.display.fill(0)
        self.display.text("Stopping Autosession...", 0, 16)
        self.display.show()
        utime.sleep_ms(500)

    def show_screen_reboot(self):
        """Display reboot message and perform system reboot."""
        self.display.fill(0)
        self.display.text("Rebooting...", 0, 16)
        self.display.show()
        utime.sleep_ms(1000)
        reset()


    def display_screen(self, option):
        method_name = f"show_screen_{option}"
        method = getattr(self, method_name, None)
        if method:
            # Keep graph-like and interactive screens displayed in a small async loop so they yield
            graph_options = {'graph_bar', 'graph_line', 'graph_setpoint', 'temp_watts_line', 'watts_line', 'profiles', 'show_settings', 'autosession_profiles'}
            #if asyncio and option in graph_options:
            if option in graph_options:
                try:
                    loop = asyncio.get_event_loop()
                    
                    # Check if we already have a running task for this exact screen
                    if hasattr(self, '_screen_task') and self._screen_task is not None and hasattr(self, '_current_screen_option') and self._current_screen_option == option:
                        # Task already running for this screen, don't recreate
                        return
                    
                    # Cancel any existing screen task (different screen)
                    try:
                        if self._screen_task is not None:
                            self._screen_task.cancel()
                    except Exception:
                        pass

                    # Track which screen we're displaying
                    self._current_screen_option = option

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


class DisplayManagerFactory:
    """Factory to create DisplayManager with optional driver overrides."""
    
    @staticmethod
    def create_display_manager(display_type, display, shared_state):
        """Create a DisplayManager, optionally extended with driver-specific overrides.
        
        Args:
            display_type: String like 'SSD1306_128x32' or 'SSD1306_128x64'
            display: The display hardware object
            shared_state: The shared state object
            
        Returns:
            DisplayManager instance (possibly with driver overrides)
        """
        print(f"DisplayManagerFactory: Attempting to load driver '{display_type}'")
        # Import driver dynamically
        driver_class = None
        try:
            if display_type == 'SSD1306_128x64':
                from displaydrivers.SSD1306_128x64 import SSD1306_128x64_Driver
                driver_class = SSD1306_128x64_Driver
                print(f"DisplayManagerFactory: Successfully loaded SSD1306_128x64_Driver")
            else:
                from displaydrivers.SSD1306_128x32 import SSD1306_128x32_Driver
                driver_class = SSD1306_128x32_Driver  # Default driver
                print(f"DisplayManagerFactory: Successfully loaded SSD1306_128x32_Driver")
        except ImportError as e:
            print(f"DisplayManagerFactory: Failed to import driver - {e}")
        
        if driver_class is not None:
            # Create a combined class that inherits from driver first (for overrides)
            # then DisplayManager for defaults
            class CombinedDisplayManager(driver_class, DisplayManager):
                pass
            print(f"DisplayManagerFactory: Creating combined DisplayManager with driver (width={driver_class.width}, height={driver_class.height})")
            return CombinedDisplayManager(display, shared_state)
        else:
            # No driver found, use base DisplayManager
            print(f"DisplayManagerFactory: Falling back to base DisplayManager (width={DisplayManager.width}, height={DisplayManager.height})")
            return DisplayManager(display, shared_state)
            return DisplayManager(display, shared_state)
