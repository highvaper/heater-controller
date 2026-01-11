from machine import Pin
from max6675_utime import MAX6675

class Thermocouple:
    def __init__(self, sck_pin_number, cs_pin_number, so_pin_number, heater_on_temperature_difference_threshold, shared_state=None):
        print("Thermocouple Initialising ...")
        
        self.shared_state = shared_state

        self.sck = Pin(sck_pin_number, Pin.OUT)
        self.cs = Pin(cs_pin_number, Pin.OUT)
        self.so = Pin(so_pin_number, Pin.IN)

        self.heater_on_temperature_difference_threshold = heater_on_temperature_difference_threshold
        self.thermocouple_sensor = None
        self.last_known_safe_temp = None
        self.raw_temp = 0
        self.filtered_temp_counter = 0
        try:
            self.thermocouple_sensor = MAX6675(self.sck, self.cs, self.so)
            #utime.sleep_ms(350)
            #self.update_filtered_temp(False) # Initialize last_known_safe_temp
            print("Thermocouple initialised.")
        except Exception as e:
            error_msg = self.shared_state.error_messages.get("thermocouple-setup", "Thermocouple setup error") if self.shared_state else "Thermocouple setup error"
            error_text = error_msg + ": " + str(e)
            if self.shared_state:
                self.shared_state.set_error("thermocouple-setup", error_text)
            # Optionally, handle the error further or re-raise it
            raise


    def read_raw_temp(self):
        try:
            raw_temp = self.thermocouple_sensor.read()
            if self.thermocouple_sensor.error():
                error_msg = self.shared_state.error_messages.get("thermocouple-read_error", "Thermocouple read error") if self.shared_state else "Thermocouple read error"
                if self.shared_state:
                    self.shared_state.set_error("thermocouple-read_error", error_msg)
                return None
            if raw_temp is None:
                error_msg = self.shared_state.error_messages.get("thermocouple-invalid_reading", "Invalid reading") if self.shared_state else "Invalid reading"
                if self.shared_state:
                    self.shared_state.set_error("thermocouple-invalid_reading", error_msg)
                return None
            if raw_temp == 0:
                base_msg = self.shared_state.error_messages.get("thermocouple-zero_reading", "Zero reading") if self.shared_state else "Zero reading"
                error_msg = base_msg + " " + str(raw_temp)
                if self.shared_state:
                    self.shared_state.set_error("thermocouple-zero_reading", error_msg)
                return None
            if raw_temp < 0:
                base_msg = self.shared_state.error_messages.get("thermocouple-below_zero", "Below zero") if self.shared_state else "Below zero"
                error_msg = base_msg + " " + str(raw_temp)
                if self.shared_state:
                    self.shared_state.set_error("thermocouple-below_zero", error_msg)
                return None
            if raw_temp > 1000:
                base_msg = self.shared_state.error_messages.get("thermocouple-above_limit", "Above limit") if self.shared_state else "Above limit"
                error_msg = base_msg + " " + str(raw_temp)
                if self.shared_state:
                    self.shared_state.set_error("thermocouple-above_limit", error_msg)
                return None

            self.raw_temp = raw_temp
        except Exception as e:
            #print(f"Error reading temperature: {e}")
            if self.shared_state:
                base_msg = self.shared_state.error_messages.get("thermocouple-read_error", "Read error")
                self.shared_state.set_error("thermocouple-read_error", f"{base_msg}: {str(e)}")
            return None
        return raw_temp


    def update_filtered_temp(self, heater_on):
        raw_temp = self.read_raw_temp()
        #print(raw_temp)
        if heater_on:
            # Note temperatures drop when the induction heater is on 
            # so ignore for time being any sudden rises (more likely caused 
            # by probe moving and shorting/touching metal)
            temp_difference = raw_temp - self.last_known_safe_temp
            if temp_difference < 0:
                #We sometimes get here if there is a temp drop and heater is on
                #ie probe moved or heater not actually powered but ih is on.
                
                self.filtered_temp_counter += 1
                # Check if the difference is over 20 degrees
                if abs(temp_difference) > self.heater_on_temperature_difference_threshold:
                    return (self.last_known_safe_temp, self.filtered_temp_counter > 3)
                else:
                    #return (self.last_known_safe_temp + temp_difference, self.filtered_temp_counter > 3)
                    return (self.last_known_safe_temp + abs(temp_difference), self.filtered_temp_counter > 3)
            else:
                self.last_known_safe_temp = raw_temp
                self.filtered_temp_counter = 0
                return (raw_temp, False)
        else:
            self.last_known_safe_temp = raw_temp
            self.filtered_temp_counter = 0
            return (raw_temp, False)

    def get_filtered_temp(self, heater_on):
        filtered_temp, action_needed = self.update_filtered_temp(heater_on)
        return filtered_temp, action_needed


