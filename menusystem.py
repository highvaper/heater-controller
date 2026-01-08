import utime
from machine import Timer
from customtimer import CustomTimer

class MenuSystem:
    def __init__(self, display_manager, shared_state):
    
        #print("MenuSystem Initialising ...")
        
        self.display_manager = display_manager
        self.shared_state = shared_state
        self.menu_start_time = None 
        self.timeout_timer = CustomTimer(period=1000, mode=Timer.PERIODIC, callback=self.check_timeout)
        
        #self.last_displayed_position = self.shared_state.current_menu_position
        #self.last_navigation_time = 0
        #self.navigation_debounce_ms = 500

        #print("MenuSystem initialised.")



    def navigate_menu(self, direction):
            
        menu_length = len(self.shared_state.menu_options)
        
        if direction == 'up':
            self.shared_state.current_menu_position = (
                self.shared_state.current_menu_position + 1 
                if self.shared_state.current_menu_position < menu_length - 1 
                else menu_length - 1
            )
        elif direction == 'down':
            self.shared_state.current_menu_position = (
                self.shared_state.current_menu_position - 1 
                if self.shared_state.current_menu_position > 0 
                else 0
            )


        # Update last movement time
        #self.last_navigation_time = current_time
        
#        # Reset timeout timer and display updated menu
        if self.timeout_timer.is_timer_running():
            self.timeout_timer.stop()
        self.display_menu()


        
        # Reset timeout timer
#        if self.timeout_timer.is_timer_running():
#            self.timeout_timer.stop()
            
        # Only update display if we actually moved
#        print("Last display position:")
#        print(self.last_displayed_position)
#        print("Current menu position:")
#        print(self.shared_state.current_menu_position)

#        if self.shared_state.current_menu_position != self.last_displayed_position:
#            self.display_menu()
#            self.last_displayed_position = self.shared_state.current_menu_position
#            self.shared_state.previous_rotary_value = self.shared_state.current_menu_position
         
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
        #self.exit_menu() #see if this fixes issue
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
#        self.shared_state.current_menu_position = 0
        if self.timeout_timer.is_timer_running(): self.timeout_timer.stop()
        #print("Menu timeout reached, exiting menu.")
