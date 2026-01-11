from machine import Pin, Timer, PWM
import utime

class BaseHeater(object):
    def __init__(self):
        self._is_on = False
    def on(self):
        raise NotImplementedError("Subclasses must implement this method")

    def off(self):
        raise NotImplementedError("Subclasses must implement this method")

    def is_on(self):
        return self._is_on

class InductionHeater(BaseHeater):
    def __init__(self, coil_pins=None, timer=None):
        super().__init__() # Initialise the BaseHeater attributes
        print("InductionHeater Initialising ...")
        self.coil_pins = coil_pins
        self.coils = []
        self.switched_on_coil = None
        self.switch_coil_period = 750 # Time between switching coils
        self.timer = timer # Store the external timer
        self.timer_running = False # Flag to track if the timer is running
        self.coils_init()
        self.last_coil_on = 0
        print("InductionHeater initialised.")

    def coils_init(self):
        if len(self.coil_pins) == 0:
            raise ValueError('No coils defined')
        coil_no = 0
        for coil_pin in self.coil_pins:
            self.coils.append(Pin(coil_pin, Pin.OUT))
            self.coils[coil_no].off()
            coil_no += 1

    def on(self, power=None):
        if self.coils:
            self.switched_on_coil = (self.last_coil_on + 1) % len(self.coils)
            self.coils[self.switched_on_coil].on()
            self.last_coil_on = self.switched_on_coil
            if not self.timer_running:
                self.timer.init(period=self.switch_coil_period, mode=Timer.PERIODIC, callback=self.change_coil)
                self.timer_running = True
            self._is_on = True

    def off(self):
        for coil in self.coils:
            coil.off()
        self.switched_on_coil = None
        if self.timer_running:
            self.timer.deinit()
            self.timer_running = False
        self._is_on = False


    def change_coil(self, timer):
        for coil in self.coils: # Ensure all heaters are off
            coil.off()
            
        self.switched_on_coil = (self.last_coil_on + 1) % len(self.coils)
        self.coils[self.switched_on_coil].on()
        self.last_coil_on = self.switched_on_coil
        print("Last on coil:" + str(self.last_coil_on))
#        if self.switched_on_coil is not None:
#            self.coils[self.switched_on_coil].off()
#            self.switched_on_coil = (self.switched_on_coil + 1) % len(self.coils)  # Could be modified for other setups eg if 4 coils then do even then odd 
#            self.coils[self.switched_on_coil].on()
#        else:
#            self.coils[0].on()
#            self.switched_on_coil = 0
#        #print(self.switched_on_coil)

# BaseHeater class provides this
#    def is_on(self): # Returns True if the heater is on, False otherwise.
#        #return self.switched_on_coil is not None
#        return self.is_on




class ElementHeater(BaseHeater): 
    def __init__(self, element_pin):
        super().__init__() 
        print("ElementHeater Initialising ...")
        self.element = Pin(element_pin, Pin.OUT)
        self.pwm = PWM(self.element) 
        self.pwm.freq(50) # Maybe too much? need to see how this goes with nichrome
        self.pwm.duty_u16(0) # Initialize PWM duty cycle to 0 (off)
        self._power = 0
        self.max_duty_cycle_percent = 0
        self.max_duty_cycle = 0
        print("ElementHeater initialised.")

    def on(self, power=100): # Default to full power (now 100)
        self._is_on = True
        self.set_power(power)


    def off(self):
        self.pwm.duty_u16(0) # Set PWM duty cycle to 0 (off)
        self._is_on = False

    def set_max_duty_cycle(self, max_duty_cycle_percent):
        self.max_duty_cycle = int(65535 * (max_duty_cycle_percent / 100)) 
        self.max_duty_cycle_percent = max_duty_cycle_percent

    def set_power(self, power):
        power = min(power, self.max_duty_cycle_percent)
        duty_cycle = int(power * 655.35)
        duty_cycle = min(duty_cycle, self.max_duty_cycle)
        #print(duty_cycle)
        self.pwm.duty_u16(duty_cycle)
        self._is_on = power > 0
        self._power = power

    def get_power(self):
        return self._power

#class ElementHeater(BaseHeater): 
#    def __init__(self, element_pin):
#        super().__init__() # Initialise the BaseHeater attributes
#        print("ElementHeater Initialising ...")
#        self.element = Pin(element_pin, Pin.OUT)
#        self.element.off()
#        print("ElementHeater initialised.")
#
#    def on(self):
#        self.element.on()
#        self._is_on = True
#
#    def off(self):
#        self.element.off()
#        self._is_on = False


class HeaterFactory:
    def create_heater(heater_type, *args, **kwargs):
        if heater_type == 'induction':
            return InductionHeater(*args, **kwargs)
        elif heater_type == 'element':
            return ElementHeater(*args, **kwargs)
        else:
            raise ValueError(f"Invalid heater type: {heater_type}")


#ihTimer = Timer() # Assuming ihTimer is initialized elsewhere
#heater = HeaterFactory.create_heater('induction', coil_pins=(12, 13), timer=ihTimer)