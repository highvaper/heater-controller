# Heater Controller

A MicroPython-based heater controller with PID control for temperature regulation and simple interface.

**Features:**
- PID temperature control (configurable tunings)
- Manual power/watts mode
- Session timer with auto-off and extension
- AutoSession mode with temperature profiles and time-based waypoints
- Temporary Max Watts dynamic power limiting
- Battery/mains voltage detection and safety cutoffs
- OLED display with menu system and graphs (temperature, voltage, watts)
- Rotary encoder and switches for user input
- LED status indicators
- Watchdog support for hardware safety

For detailed installation instructions, see [INSTALL.md](INSTALL.md).

## Required Hardware

- Raspberry Pi Pico
- SSD1306 Display
- MAX6675 + K Type Thermocouple
- KY-040 Rotary Encoder
- Other bits: Push Button and LEDs, buzzer (optional)


For induction based heater
- 5-12V ZVS Low Voltage Induction Heater(s) + Coil(s)
- High-Power Mosfet Switch (one per induction coil)
- A suitable power supply for the ZVS circuits

For element heater
- Nichrome coil or similar resistive element
- Suitable MOSFET and power supply


## Example Hardware Layout

```
[Raspberry Pi Pico]
    |
    |---[GPIO 18] ---> [LED]
    |
    |---[GPIO 6] ----> [MAX6675 SCK]
    |---[GPIO 7] ----> [MAX6675 CS]
    |---[GPIO 8] ----> [MAX6675 SO]
    |
    |---[GPIO 1] ----> [SSD1306 SDA]
    |---[GPIO 0] ----> [SSD1306 SCL]
    |
    |---[GPIO 12] ----> [Mosfet Switch] ----> [Induction Heater Coil 1]
    |---[GPIO 13] ----> [Mosfet Switch] ----> [Induction Heater Coil 2]
    |
    |---[GPIO 5] ----> [Rotary Encoder CLK]
    |---[GPIO 4] ----> [Rotary Encoder DT]
    |---[GPIO 14] ---> [Button]
    |
    |---[GPIO 16] ---> [Buzzer]
    |---[GPIO 21] ---> [SSD1306 SCL]
    |---[GPIO 20] ---> [SSD1306 SDA]
    |---[GPIO 22] ---> [Element Heater]
    |---[GPIO 23/24/25] ---> [Switches]
```

Note: This diagram excludes any power connections.



## Operating Modes

### Session Mode
- In Session mode, the heater runs for a preset time (default 7 minutes) and automatically turns off when the session ends or if safety limits are reached, the green LED will light during the session.
- The heater will also turn off if the temperature exceeds safe limits or battery voltage drops too low.
- When the setpoint temperature is reached, the red LED lights.
- You can extend the session by pressing the button in the last minute of the session.

### Temperature Mode
- The default mode uses PID control to maintain the setpoint temperature.
- The rotary encoder adjusts the setpoint.

### Watts Mode
- In watts mode, you can directly set the heater power in watts.
- If INA226 present then controller will use PID control to maintain the setpoint watts.
- If INA226 not present then controller will adjust duty cycle for watts based on a calculated value from user entered resistance and live input voltage.
- Use the rotary encoder to adjust the power level.

### Duty Cycle Mode
- In Duty Cycle mode, you have direct control over the PWM duty cycle (0-100%).
- Duty cycle is the percentage of time the heater is powered on per PWM cycle.
- This mode is useful for direct power control without temperature feedback.
- The rotary encoder adjusts the duty cycle in 0.1% increments when less than 10%.
- When a thermocouple is not available, the controller automatically falls back to Duty Cycle mode.
- Maximum duty cycle is constrained by the `heater_max_duty_cycle_percent` setting, which is calculated from your profile's `max_watts` and heater resistance.

### AutoSession Mode
- AutoSession allows running a temperature profile with time-based waypoints for automated temperature control during a session.
- Temperature profiles are defined with time/temperature pairs (e.g., `0:100,5:100,15:150,30:50`).
- The controller interpolates linearly between waypoints and automatically follows the temperature schedule.
- Profiles are loaded from the `profiles_autosession/` directory.
- You can adjust elapsed time during an active autosession using the rotary encoder.
- Each profile can define a custom `time_adjustment_step` to control rotary adjustment increments.


## Button and Rotary Actions

- Main switch/rotary decoder depress
 - **Single Click**: Enter menu or select menu item.
 - **Long Press (hold)**: On demand on/off.
 - **Double Click**: Enter menu.
 - **Triple Click**: Start/stop a session.
 - **Quadruple Click (4x fast)**: Start/stop a 1 minute session.
 - **Rotate Encoder**: Adjust setpoint (PID mode) or power (Watts mode), or navigate menu options.

- Middle button
 - **Single Click**: Display/adjust Temp Max Watts.
 - **Triple Click**: Start/stop an AutoSession
 - **Quadruple Click (4x fast)**: If AutoSession in progress will switch to normal sesson mode and start a new session
- If you depress the encoder while turning it will increase/decrease the value in x10 increments (not in Auto Session)

- Change mode switch cycles through the modes

### Menu Navigation
- Use the rotary encoder to scroll through menu options.
- Click the button to select an option.
- Menu options include Home Screen, Graphs, Settings, and more.

### LEDs
- **Green LED**: Heater active.
- **Red LED**: Within 10°C of setpoint in session mode.
- **Blue LED**: Indicates near end of session.




## Safety Notes

- Always verify correct wiring before powering the heater.
- Set appropriate resistance and wattage limits for your coil/element.


## Hardware Testing

```python
import test_hardware

# Run all tests with current hardware configuration
test_hardware.test_hardware()

# Run all tests with a specific hardware configuration
test_hardware.test_hardware(hardware_config='custom_setup')

# Run specific tests
test_hardware.test_hardware('leds')          # Test RGB LEDs
test_hardware.test_hardware('buzzer')        # Test buzzer
test_hardware.test_hardware('display')       # Test OLED display
test_hardware.test_hardware('thermocouple')  # Test MAX6675
test_hardware.test_hardware('rotary')        # Test rotary encoder
test_hardware.test_hardware('switches')      # Test push buttons
test_hardware.test_hardware('adc')           # Test voltage monitoring
test_hardware.test_hardware('heater')        # Test heater output (WARNING: activates heater!)

# Run multiple tests with specific hardware configuration
test_hardware.test_hardware('leds', 'display', 'thermocouple')
test_hardware.test_hardware('leds', 'buzzer', hardware_config='test_board')
```

The test suite will:
- Read your hardware configuration from `current_hardware.txt` (default) or from a specific configuration in `hardware_profiles/`
- Test each component systematically
- Report PASSED/FAILED/SKIPPED for each test
- Provide visual and interactive feedback
- Halt immediately if the specified hardware configuration cannot be loaded

### Hardware Configuration System

Hardware configurations are stored in the `hardware_profiles/` directory:
- `hardware_default.txt` - Fallback configuration
- `hardware_profiles/custom_name.txt` - Your custom configurations

The system reads `current_hardware.txt` to determine which configuration to load at boot. You can switch configurations by loading a profile that specifies different hardware, which will update `current_hardware.txt` and reboot.
