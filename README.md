# Heater Controller

A MicroPython-based heater controller with PID control for temperature regulation and simple interface.

## Required Hardware

- Raspberry Pi Pico
- SSD1306 Display
- MAX6675 + K Type Thermocouple
- KY-040 Rotary Encoder
- DS18X20 Temperature Sensor (optional)
- Other bits: Push Button and LEDs, buzzer (optional)


For induction based heater
- 5-12V ZVS Low Voltage Induction Heater(s) + Coil(s)
- High-Power Mosfet Switch (one per induction coil)
- A suitable power supply for the ZVS circuits


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
    |---[GPIO 17] ---> [DS18X20 OneWire] //not really needed planned use to check on coil circuit temperatures
```

Note: This diagram excludes any power connections.


## Install Notes

First setup Pi Pico setup with MicroPython in Thonny.

https://www.raspberrypi.com/documentation/microcontrollers/micropython.html

https://thonny.org/


### Installing libraries

1. **Open Thonny**: Launch Thonny and ensure Pi Pico is connected

2. **Install simple-pid and ssd1306**: 
    - Go to `Tools` > `Manage Packages`.
    - Search for `simple-pid`.
    - Install the package.

### Upload files from repository

In Thonny, use the `Tools` > `Upload Files` option.

For development or testing, it's simpler to copy and paste the contents of `main.py` directly into the interpreter window rather than copying the file itself.