import utime
#import sys ? do we need this?

#from machine import ADC, Pin, I2C, Timer, WDT, PWM
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
from heaters import HeaterFactory, InductionHeater, ElementHeater
from machine import ADC

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


def get_input_volts(previous_reading):
    adc_pin = ADC(28)
    r1 = 910000   # 910kΩ
    r2 = 102000   # 102kΩ
    adc_value = adc_pin.read_u16()

    #print(str(adc_value))
    
    if adc_value in [512, 1536, 2560, 3584]:  #problematic_values for rp2040 adc reading
        return previous_reading

    voltage_adc = adc_value * (3.3 / 65535)  # Convert ADC value to voltage
    voltage_in = voltage_adc * (r1 + r2) / r2 #calculate input voltage
     
    if voltage_in < 4.0:
        correction = 0.220
    elif voltage_in < 8.0:
        correction = 0.180
    else:
        correction = 0.140
        
    if previous_reading == False: previous_reading = voltage_in  # for first reading

    #print(str(adc_value) + " " + str(voltage_adc) + " " + str(voltage_in))
    
    if previous_reading - (voltage_in - correction) > 1:  
        #its ok if it goes up we care more about max_duty cycle being too high
        #this is to cover the adc bug with the rp2040
        #maybe need to loop a few times and get average rather than just one reading as this still give od rreading sometimes
        
        #print("Retry Read Input Voltage:", voltage_in, "V")
        utime.sleep_ms(150)
        adc_value = adc_pin.read_u16()
        voltage_adc = adc_value * (3.3 / 65535)  # Convert ADC value to voltage
        voltage_in = voltage_adc * (r1 + r2) / r2 #calculate input voltage
        if previous_reading - (voltage_in - correction) > 1:  
            voltage_in = previous_reading - 0.3  # lets reduce by a little bit in case there really has been a drop
                                                 # next time round it will drop again and again but it safer 
                                                 # to drop in small amounts so we dont over power the mostfet in case its wrong
            #print("Retry Read Input Voltage dropped by 0.5v:", voltage_in, "V")
    
    #print("Input Voltage:", voltage_in, "V")
    return round(voltage_in - correction, 2)
    

def buzzer_play_tone(buzzer, frequency, duration):
    #need to do this as a separate thread as this blocks
    buzzer.freq(frequency)
    #buzzer.duty_u16(32768) # 50% duty cycle
    buzzer.duty_u16(10000) # 
    utime.sleep_ms(duration)
    buzzer.duty_u16(0) # Stop the buzzer