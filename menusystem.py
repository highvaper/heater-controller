import utime
from machine import Timer
from customtimer import CustomTimer

class MenuSystem:
    def __init__(self, display_manager, shared_state):
    
        print("MenuSystem Initialising ...")
        
        self.display_manager = display_manager
        self.shared_state = shared_state
        self.menu_start_time = None 
        self.timeout_timer = CustomTimer(period=1000, mode=Timer.PERIODIC, callback=self.check_timeout)
        print("MenuSystem initialised.")


#    def navigate_menu(self, direction):
#        if direction == 'up':
#            if self.shared_state.current_menu_position > 1:
#                self.shared_state.current_menu_position -= 1
#                #self.shared_state.current_menu_position = max(0, self.shared_state.current_menu_position - 1)
#        elif direction == 'down':
#            if self.shared_state.current_menu_position < len(self.shared_state.menu_options) - 1:
#                self.shared_state.current_menu_position += 1
#                #self.shared_state.current_menu_position = min(len(self.shared_state.menu_options) - 1, self.shared_state.current_menu_position + 1)
#       #print("Menu navigated, resetting timeout.")
#        if self.timeout_timer.is_timer_running(): self.timeout_timer.stop()
#        self.display_menu() 
    def navigate_menu(self, direction):
        if direction == 'up':
            # Decrement the current menu position, allowing it to loop around to the bottom
            self.shared_state.current_menu_position -= 1
            if self.shared_state.current_menu_position < 0:
                # If the current menu position is less than 0, set it to the last index of the menu options
                self.shared_state.current_menu_position = len(self.shared_state.menu_options) - 1
        elif direction == 'down':
            # Increment the current menu position, allowing it to loop around to the top
            self.shared_state.current_menu_position += 1
            if self.shared_state.current_menu_position >= len(self.shared_state.menu_options):
                # If the current menu position is greater than or equal to the length of the menu options, set it to 0
                self.shared_state.current_menu_position = 0
        # Stop the timeout timer and display the menu
        if self.timeout_timer.is_timer_running(): self.timeout_timer.stop()
        self.display_menu()


        
    def handle_menu_selection(self):
        middle_line = self.shared_state.current_menu_position
        #print(f"Middle line of the menu: {middle_line}")
        self.display_selected_option()


    def display_selected_option(self):
        selected_option = self.shared_state.menu_options[self.shared_state.current_menu_position]
        selected_option = selected_option.replace(' ', '_')
        selected_option = selected_option.lower()
        if selected_option == "home_screen":
            self.exit_menu()
            return
        self.display_manager.display_screen(selected_option)
        self.exit_menu()


    def display_menu(self):
        self.menu_start_time = utime.ticks_ms()
        #print("Starting timeout timer.")
        if not self.timeout_timer.is_timer_running(): self.timeout_timer.start()
        self.display_manager.show_screen_menu()


    def check_timeout(self, timer):
        elapsed_time = utime.ticks_diff(utime.ticks_ms(), self.menu_start_time)
        #print("Checking timeout, elapsed time:", elapsed_time)
        if elapsed_time >= self.shared_state.menu_timeout:
            self.exit_menu()
        #else:
        #    print("Timeout not reached yet.")


    def exit_menu(self):
        self.menu_start_time = None
        self.shared_state.in_menu = False
        #self.shared_state.current_menu_position = 1
        if self.timeout_timer.is_timer_running(): self.timeout_timer.stop()
        #print("Menu timeout reached, exiting menu.")
