
import utime
#import sys ? do we need this?
import os
#from machine import ADC, Pin, I2C, Timer, WDT, PWM
from machine import Pin, I2C
from ssd1306 import SSD1306_I2C
from heaters import HeaterFactory, InductionHeater, ElementHeater
from machine import ADC

from autosession import AutoSessionTemperatureProfile


def create_autosession_log_file(profile_name, autosession_profile_name):
    """
    Create a new CSV file for autosession logging.
    Filename format: autosession_logs/profile_name_autosession_profile_name_0.csv
    Creates directory if it doesn't exist.
    Returns (file_object, filename) or (None, None) on error.
    """
    try:
        # Create directory if it doesn't exist
        try:
            os.mkdir('/autosession_logs')
        except OSError:
            pass  # Directory already exists
        
        # Find next available number to avoid overwriting
        counter = 0
        while True:
            filename = f'/autosession_logs/{profile_name}_{autosession_profile_name}_{counter}.csv'
            try:
                with open(filename, 'r'):
                    counter += 1
            except OSError:
                break
        
        # Create and write header
        f = open(filename, 'w')
        header = 'elapsed_s,heater_temp_c,setpoint_c,input_volts,power_percent,watts,pid_p,pid_i,pid_d\n'
        f.write(header)
        f.flush()
        print(f"Created autosession log: {filename}")
        return f, filename
    except Exception as e:
        print(f"Error creating autosession log file: {e}")
        return None, None

def log_autosession_data(log_file, log_buffer, elapsed_ms, heater_temperature, temperature_setpoint, input_volts, power_percent, watts, pid_p, pid_i, pid_d, autosession_log_buffer_flush_threshold, led_pin):
    """
    Buffer autosession data and flush when buffer reaches configured threshold.
    Returns updated buffer and file object (or None if closed).
    """
    try:
        if log_file is None:
            return log_buffer, log_file
        
        elapsed_s = elapsed_ms / 1000.0
        line = f'{elapsed_s:.1f},{int(heater_temperature)},{int(temperature_setpoint)},{input_volts:.2f},{int(power_percent)},{int(watts)},{pid_p:.4f},{pid_i:.4f},{pid_d:.4f}\n'
        log_buffer.append(line)
        
        # Flush when buffer reaches configured threshold
        if len(log_buffer) >= autosession_log_buffer_flush_threshold:
            for data_line in log_buffer:
                log_file.write(data_line)
            log_file.flush()
            log_buffer = []
            # On MicroPython, also call fsync if available for extra safety
            try:
                os.fsync(log_file.fileno())
            except (AttributeError, OSError):
                pass  # fsync not available on this platform
            #flash blue led to indicate log flush
            led_pin.on()
            utime.sleep_ms(50)
            led_pin.off()  
        return log_buffer, log_file
    except Exception as e:
        print(f"Error logging autosession data: {e}")
        return log_buffer, log_file

def flush_autosession_log(log_file, log_buffer):
    """Flush remaining buffered data and close file."""
    try:
        if log_file is not None:
            if log_buffer:
                for line in log_buffer:
                    log_file.write(line)
            log_file.flush()
            # On MicroPython, also call fsync if available for extra safety
            try:
                os.fsync(log_file.fileno())
            except (AttributeError, OSError):
                pass  # fsync not available on this platform
            log_file.close()
            print("Autosession log flushed and closed")
    except Exception as e:
        print(f"Error flushing autosession log: {e}")


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
                                      'temperature_max_allowed_setpoint', 'set_watts', 'lipo_count', 'pi_temperature_limit',
                                      'autosession_log_buffer_flush_threshold']:
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
                                elif key == 'autosession_log_buffer_flush_threshold':
                                    if int(value) > 0 and int(value) <= 200:
                                        config[key] = int(value)
                                    else:
                                        print(f"Warning: autosession_log_buffer_flush_threshold out of range (1-200): {value}")
                            elif key == 'set_duty_cycle':
                                # Allow decimal duty cycle values (e.g., 12.3 for 12.3%)
                                try:
                                    dc = float(value)
                                    if 0.0 <= dc <= 100.0:
                                        config[key] = dc
                                    else:
                                        print(f"Warning: set_duty_cycle out of range (0-100): {value}")
                                except ValueError:
                                    print(f"Warning: Could not parse set_duty_cycle value: {value}")
                            elif key == 'heater_resistance':
                                res_value = float(value)
                                if res_value < 0.3:
                                    print(f"Warning: heater_resistance too low (<0.3 ohms): {value}")
                                elif res_value > 2.5:
                                    print(f"Warning: heater_resistance too high (>2.5 ohms): {value}")
                                else:
                                    config[key] = res_value
                            elif key in ['lipo_safe_volts', 'lead_safe_volts', 'mains_safe_volts']:
                                config[key] = float(value)
                            elif key in ['display_contrast']:
                                if 0 <= int(value) <= 255:
                                    config[key] = int(value)
                                else:
                                    print(f"Warning: display_contrast out of range (0-255): {value}")
                            elif key in ['temperature_units', 'default_autosession_profile']:
                                # temperature_units: 'C' or 'F', default_autosession_profile: string profile name or empty
                                if key == 'temperature_units':
                                    if value in ['C', 'F']:
                                        config[key] = value
                                    else:
                                        print(f"Warning: temperature_units must be 'C' or 'F': {value}")
                                elif key == 'default_autosession_profile':
                                    # Accept any non-empty string as a profile name, or empty string for None
                                    config[key] = value if value else None
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
                            elif key in ['display_rotate', 'autosession_logging_enabled']:
                                config[key] = value.lower() in ['true', '1', 'yes']
                            elif key == 'pid_temperature_tunings':
                                # Parse PID tunings as comma-separated float values: P,I,D
                                tunings_str = value.split(',')
                                if len(tunings_str) == 3:
                                    config[key] = (float(tunings_str[0].strip()), float(tunings_str[1].strip()), float(tunings_str[2].strip()))
                                else:
                                    print(f"Warning: pid_temperature_tunings must be in format 'P,I,D' (got: {value})")
                        except (ValueError, TypeError) as e:
                            print(f"Warning: Could not parse {key}={value}: {e}")
    except OSError as e:
        print(f"Warning: Could not load profile '{profile_name}': {e}")
    
    return config


def list_profiles():
    try:
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
        
        # Load autosession profile if specified in the profile
        if shared_state.default_autosession_profile:
            print(f"Loading default autosession profile from profile: {shared_state.default_autosession_profile}")
            success, message = apply_and_save_autosession_profile(shared_state.default_autosession_profile, shared_state)
            print(message)
        
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


# AUTOSESSION PROFILE SUPPORT
def load_autosession_profile(profile_name):
    try:
        with open('/profiles_autosession/' + profile_name + '.txt', 'r') as file:
            profile_string = file.read().strip()
            return profile_string
    except OSError as e:
        print(f"Warning: Could not load autosession profile '{profile_name}': {e}")
        return None

def list_autosession_profiles():
    profiles = []
    try:
        for filename in os.listdir('/profiles_autosession/'):
            if filename.endswith('.txt'):
                profiles.append(filename[:-4])
        profiles.sort()
    except Exception as e:
        print(f"Error listing autosession profiles: {e}")
    return profiles

# Helper to load and save autosession profile, like apply_and_save_profile
def apply_and_save_autosession_profile(profile_name, shared_state):
    if not profile_name:
        return False, "No autosession profile name provided"
    try:
        print(f"Loading autosession profile: {profile_name}")
        profile_string = load_autosession_profile(profile_name)
        if not profile_string:
            return False, f"Autosession profile '{profile_name}' not found"
        # Find the first non-comment, non-blank line starting with 'temperature_profile='
        temp_profile_line = None
        time_adjustment_step = 10  # Default to 10 seconds if not specified
        
        for line in profile_string.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('temperature_profile='):
                temp_profile_line = line
            elif line.startswith('time_adjustment_step='):
                try:
                    time_adjustment_step = int(line.split('=', 1)[1].strip())
                except (ValueError, IndexError):
                    print(f"Warning: Could not parse time_adjustment_step, using default 10 seconds")
                    time_adjustment_step = 10
        
        if temp_profile_line:
            profile_value = temp_profile_line.split('=', 1)[1].strip()
        else:
            profile_value = profile_string.strip()
        
        shared_state.autosession_profile = AutoSessionTemperatureProfile(profile_value)
        shared_state.autosession_profile_name = profile_name
        shared_state.autosession_time_adjustment_step = time_adjustment_step
        print(f"Autosession profile set to: {profile_name}")
        print(f"Autosession time adjustment step: {time_adjustment_step} seconds")
        # Save as current autosession profile
        try:
            with open('/current_autosession_profile.txt', 'w') as f:
                f.write(profile_name)
            print(f"Saved current autosession profile: {profile_name}")
        except OSError as e:
            print(f"Warning: Could not save current autosession profile: {e}")
            return True, f"Autosession profile loaded but not saved: {e}"
        return True, f"Loaded autosession: {profile_name}"
    except Exception as e:
        print(f"Error loading autosession profile: {e}")
        return False, f"Error loading autosession profile"
    
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
            if thermocouple is not None:
                new_temperature = thermocouple.read_raw_temp()
            else:  
                new_temperature = 0
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
    #for time being just return here - we will make this asunchronous later
    return
    #need to do this asynchronously as this blocks
    buzzer.freq(frequency)
    #buzzer.duty_u16(32768) # 50% duty cycle
    buzzer.duty_u16(10000) # 
    utime.sleep_ms(duration)

    buzzer.duty_u16(0) # Stop the buzzer
