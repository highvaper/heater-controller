import utime
#import sys ? do we need this?

#from machine import ADC, Pin, I2C, Timer, WDT, PWM
from machine import ADC, Pin, I2C
from ssd1306 import SSD1306_I2C
from heaters import HeaterFactory, InductionHeater, ElementHeater

from errormessage import ErrorMessage #remove

def load_config(file_path='config.txt'):  #not used at the moment need to load to different profiles to shared state
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
        display_manager.display_error("pi-unknown_error:" + error_message,10,True) # need to move out of this?
        #while True:
         #   utime.sleep_ms(1000)
    return pi_temperature

def get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager):

    try:

        if isinstance(heater, InductionHeater):
            new_temperature, need_off_temperature = thermocouple.get_filtered_temp(heater.is_on())
        elif isinstance(heater, ElementHeater):
            new_temperature = thermocouple.read_raw_temp()
            need_off_temperature = False  # caller can throw this away if not needed
        else:
            raise ValueError("Unsupported heater type")
        return new_temperature, need_off_temperature
    
    except Exception as e:
        error_message = str(e)
        if "invalid_reading" in error_message or "zero_reading" in error_message or "below_zero" in error_message:
            heater.off()
            if pidTimer.is_timer_running():
                pidTimer.stop()
            print("Stopped heater - " + error_message)
            while True:
                display_manager.display_error("thermocouple-error:" + error_message)
                utime.sleep_ms(500)
        elif "above_limit" in error_message or "read_error" in error_message:
            heater.off()
            print("Pausing heater - " + error_message)
            return -1, True
        else:
            heater.off()
            if pidTimer.is_timer_running():
                pidTimer.stop()
            print("Stopped heater - Unknown Error: " + error_message)
            while True:
                display_manager.display_error("unknown_error:" + error_message)
                utime.sleep_ms(500)
                
def initialize_display(i2c_scl, i2c_sda, led_pin):
    
    try:
        i2c = I2C(0, scl=Pin(i2c_scl), sda=Pin(i2c_sda), freq=200000)
        display = SSD1306_I2C(128, 32, i2c)
    except Exception as e:
        error_text = "Start up failed - initialize_display failed " + str(e)
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
        #sys.exit()

    return display

def buzzer_play_tone(buzzer, frequency, duration):
    #need to do this as a separate thread as this blocks
    buzzer.freq(frequency)
    #buzzer.duty_u16(32768) # 50% duty cycle
    buzzer.duty_u16(10000) # 
    utime.sleep_ms(duration)
    buzzer.duty_u16(0) # Stop the buzzer