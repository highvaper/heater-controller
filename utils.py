import utime
#import sys ? do we need this?

#from machine import ADC, Pin, I2C, Timer, WDT, PWM
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
from heaters import HeaterFactory, InductionHeater, ElementHeater
from machine import ADC

def load_profile(profile_name, shared_state):

    # Start with defaults from SharedState.initialize_defaults()
    config = shared_state.initialize_defaults()
    
    try:
        with open('/profiles/' + profile_name +'.txt', 'r') as file:
            for line in file:
                if line.strip() and not line.startswith('#'):  # Ignore empty lines and comments
                    parts = line.strip().split('=', 1)  # Split on first '=' only
                    if len(parts) == 2:
                        key, value = parts
                        key = key.strip()
                        value = value.strip()
                        
                        # Type conversion based on expected types
                        try:
                            # Handle new key names (map to old attribute names for compatibility)
                            if key in ['session_timeout', 'session_extend_time', 'temperature_setpoint', 'power_threshold',
                                      'heater_on_temperature_difference_threshold', 'max_watts', 'click_check_timeout',
                                      'temperature_max_allowed_setpoint', 'set_watts', 'set_duty_cycle', 'lipo_count', 'pi_temperature_limit']:
                                config[key] = int(value)
                                if key == 'session_timeout':
                                    config[key] = int(value) * 1000  # Convert to milliseconds
                                elif key == 'session_extend_time':
                                    config[key] = int(value) * 1000  # Convert to milliseconds
                                elif key == 'temperature_setpoint':
                                    if int(value) > 0 and int(value) <= 300:
                                        config[key] = int(value)
                                    else:
                                        print(f"Warning: temperature_setpoint out of range (1-300): {value}")
                                elif key == 'temperature_max_allowed_setpoint':
                                    if int(value) > 0 and int(value) <= 300:
                                        config[key] = int(value)
                                    else:
                                        print(f"Warning: temperature_max_allowed_setpoint out of range (1-300): {value}")
                                elif key == 'max_watts':
                                    if int(value) > 0 and int(value) <= 150:
                                        config[key] = int(value)
                                    else:
                                        print(f"Warning: max_watts out of range (1-150): {value}")
                                elif key == 'setwatts':
                                    if int(value) >= 0 and int(value) <= 150:
                                        config[key] = int(value)
                                    else:
                                        print(f"Warning: setwatts out of range (0-150): {value}")
                                elif key == 'set_duty_cycle':
                                    if int(value) >= 0 and int(value) <= 100:
                                        config[key] = int(value)
                                    else:
                                        print(f"Warning: set_duty_cycle out of range (0-100): {value}")
                            elif key in ['heater_resistance', 'lipo_safe_volts', 'lead_safe_volts', 'mains_safe_volts']:
                                config[key] = float(value)
                            elif key in ['display_contrast']:
                                if 0 <= int(value) <= 255:
                                    config[key] = int(value)
                                else:
                                    print(f"Warning: display_contrast out of range (0-255): {value}")
                            elif key in ['temperature_units']:
                                if value in ['C', 'F']:
                                    config[key] = value
                                else:
                                    print(f"Warning: temperature_units must be 'C' or 'F': {value}")
                            elif key in ['control']:
                                if value in ['temperature_pid', 'watts']:
                                    config[key] = value
                                else:
                                    print(f"Warning: control mode must be 'temperature_pid', 'watts', or 'duty_cycle': {value}")
                            elif key in ['power_type']:
                                if value in ['mains', 'lipo', 'lead']:
                                    config[key] = value
                                else:
                                    print(f"Warning: power_type must be 'mains', 'lipo', or 'lead': {value}")
                            elif key in ['display_rotate', 'session_reset_pid_when_near_setpoint']:
                                config[key] = value.lower() in ['true', '1', 'yes']
                            elif key == 'pid_tunings':
                                # Parse PID tunings as comma-separated float values: P,I,D
                                tunings_str = value.split(',')
                                if len(tunings_str) == 3:
                                    config[key] = (float(tunings_str[0].strip()), float(tunings_str[1].strip()), float(tunings_str[2].strip()))
                                else:
                                    print(f"Warning: pid_tunings must be in format 'P,I,D' (got: {value})")
                        except (ValueError, TypeError) as e:
                            print(f"Warning: Could not parse {key}={value}: {e}")
    except OSError as e:
        print(f"Warning: Could not load profile '{profile_name}': {e}")
    
    return config


def list_profiles():
    try:
        import os
        profiles = []
        try:
            # Try to list directory contents
            for filename in os.listdir('/profiles/'):
                if filename.endswith('.txt'):
                    filename = filename[:-4]  # Remove .txt extension
                    profiles.append(filename)
            profiles.sort()
            return profiles
        except AttributeError:
            return []
    except Exception as e:
        print(f"Error listing profiles: {e}")
        return []


def apply_and_save_profile(profile_name, shared_state):

    if not profile_name:
        return False, "No profile name provided"
    
    try:
        print(f"Loading profile: {profile_name}")
        config = load_profile(profile_name, shared_state)
        shared_state.apply_profile(config)
        shared_state.set_profile_name(profile_name)
        shared_state.pid.reset() 
        # Save as current profile
        try:
            with open('/current_profile.txt', 'w') as f:
                f.write(profile_name)
            print(f"Saved current profile: {profile_name}")
        except OSError as e:
            print(f"Warning: Could not save current profile: {e}")
            return True, f"Profile loaded but not saved: {e}"
        
        return True, f"Loaded: {profile_name}"
    except Exception as e:
        print(f"Error loading profile: {e}")
        return False, f"Error loading profile"



def get_pi_temperature_or_handle_error(pi_temperature_sensor, display_manager, shared_state=None):
    try:
        ADC_voltage = pi_temperature_sensor.read_u16() * (3.3 / (65536))
        pi_temperature = 27 - (ADC_voltage - 0.706) / 0.001721
        return pi_temperature
    except Exception as e:
        error_message = str(e)
        print("Error reading PI temperature: " + error_message)
        if shared_state:
            shared_state.set_error("pi-unknown_error", "PI temperature read error: " + error_message)
        #while True:
         #   utime.sleep_ms(1000)
    return pi_temperature

def get_thermocouple_temperature_or_handle_error(thermocouple, heater, pidTimer, display_manager, shared_state=None):

    try:

        if isinstance(heater, InductionHeater):
            new_temperature, need_off_temperature = thermocouple.get_filtered_temp(heater.is_on())
        elif isinstance(heater, ElementHeater):
            new_temperature = thermocouple.read_raw_temp()
            need_off_temperature = False  # caller can throw this away if not needed
            
            # Check if an error was set during read
            if shared_state and shared_state.has_error():
                error_code, error_message = shared_state.current_error
                if error_code in ["thermocouple-invalid_reading", "thermocouple-zero_reading", "thermocouple-below_zero"]:
                    heater.off()
                    if pidTimer.is_timer_running():
                        pidTimer.stop()
                    print("Stopped heater - " + error_message)
                    # Don't return yet, let the error display in main loop
                    return -1, True
                elif error_code in ["thermocouple-above_limit", "thermocouple-read_error"]:
                    heater.off()
                    print("Pausing heater - " + error_message)
                    return -1, True
        else:
            raise ValueError("Unsupported heater type")
        return new_temperature, need_off_temperature
    
    except Exception as e:
        error_message = str(e)
        heater.off()
        if pidTimer.is_timer_running():
            pidTimer.stop()
        print("Stopped heater - Unknown Error: " + error_message)
        if shared_state:
            shared_state.set_error("unknown-error", error_message)
        return -1, True
                
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