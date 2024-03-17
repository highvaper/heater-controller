from machine import Pin
from max6675_utime import MAX6675

from errormessage import ErrorMessage

class Thermocouple:

    THERMOCOUPLE_ERROR_MESSAGES = {
        "thermocouple-setup":           "Error setting up thermocouple, cannot continue",
        "thermocouple-read_error":      "Error with the thermocouple read - Check it is not damaged or loosely connected",
        "thermocouple-invalid_reading": "Invalid temperature reading",
        "thermocouple-zero_reading":    "Temperature reading is 0 - Check the MAX6675 is correctly wired",
        "thermocouple-below_zero":      "Temperature reading is below 0C - Check the probe is not wired up backwards",
        "thermocouple-above_limit":     "Temperature reading is over 1000C - Check the probe for shorting"
    }
    def __init__(self, sck_pin_number, cs_pin_number, so_pin_number, heater_on_temperature_difference_threshold):
        print("Thermocouple Initialising ...")

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
            error_text = self.THERMOCOUPLE_ERROR_MESSAGES["thermocouple-setup"] + ": " + str(e)
            # Optionally, handle the error further or re-raise it
            raise


    def read_raw_temp(self):
        try:
            raw_temp = self.thermocouple_sensor.read()
            if self.thermocouple_sensor.error():
                raise ErrorMessage("thermocouple-read_error",self.THERMOCOUPLE_ERROR_MESSAGES["thermocouple-read_error"])
            if raw_temp is None:
                raise ErrorMessage("thermocouple-invalid_reading",self.THERMOCOUPLE_ERROR_MESSAGES["thermocouple-invalid_reading"])
            if raw_temp == 0:
                raise ErrorMessage("thermocouple-zero_reading",self.THERMOCOUPLE_ERROR_MESSAGES["thermocouple-zero_reading"] + " " + str(raw_temp))
            if raw_temp < 0:
                raise ErrorMessage("thermocouple-below_zero",self.THERMOCOUPLE_ERROR_MESSAGES["thermocouple-below_zero"] + " " + str(raw_temp))
            if raw_temp > 1000:
                raise ErrorMessage("thermocouple-above_limit",self.THERMOCOUPLE_ERROR_MESSAGES["thermocouple-above_limit"] + " " + str(raw_temp))

            self.raw_temp = raw_temp
        except Exception as e:
            #print(f"Error reading temperature: {e}")
            raise e
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


