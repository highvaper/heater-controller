"""
Hardware Test Suite
===================
Test script to verify all hardware components in the heater controller.
This script reads configuration from hardware.txt and tests each component systematically.

Run this script on your Raspberry Pi Pico to verify your hardware setup.

Using Thonny if you edit hardware.txt and upload you can rerun the tests without resetting each change.

Usage:
    import test_hardware
    test_hardware.test_hardware()           # Run all tests
    test_hardware.test_hardware('leds')     # Run only LED test
    test_hardware.test_hardware('leds', 'display')  # Run LED and display tests

Available tests:
    'leds'          - RGB LED outputs
    'buzzer'        - Buzzer output 
    'rotary'        - Rotary encoder and button
    'switches'      - Left, middle, and right switches
    'display'       - Display (I2C SSD1306)
    'thermocouple'  - MAX6675 thermocouple
    'heater'        - Heater control output - this will briefly activate the heater output!
    'adc'           - Voltage monitoring ADC
"""

import machine
from machine import Pin, SPI, I2C, ADC, PWM
import utime
import sys

import utils

# Test tracking
tests_passed = 0
tests_failed = 0
tests_skipped = 0

def test_result(name, passed, message=""):
    """Print test result and update counters."""
    global tests_passed, tests_failed, tests_skipped
    if passed is None:
        print(f"   ⊘ SKIPPED: {message}")
        tests_skipped += 1
    elif passed:
        print(f"   ✓ PASSED: {message}")
        tests_passed += 1
    else:
        print(f"   ✗ FAILED: {message}")
        tests_failed += 1

# ============================================================
# Individual Test Functions
# ============================================================

def test_leds(hw):
    """Test RGB LED outputs."""
    print("="*60)
    print("TEST: RGB LED Outputs")
    print("="*60)
    utime.sleep(3)
    
    led_pins = {
        'Red LED': hw.get('red_led'),
        'Green LED': hw.get('green_led'),
        'Blue LED': hw.get('blue_led')
    }

    for name, pin_num in led_pins.items():
        if pin_num is None:
            test_result(name, None, f"{name} not configured")
            continue
        
        try:
            led = Pin(pin_num, Pin.OUT)
            print(f"\nTesting {name} on GP{pin_num}...")
            
            # Blink 3 times
            for i in range(3):
                led.on()
                utime.sleep_ms(150)
                led.off()
                utime.sleep_ms(150)
            
            test_result(name, True, f"{name} on GP{pin_num} - Watch for 3 blinks")
        except Exception as e:
            test_result(name, False, f"{name} error: {e}")

    print()
    utime.sleep(3)

def test_buzzer(hw):
    """Test buzzer output."""
    print("="*60)
    print("TEST: Buzzer")
    print("="*60)
    utime.sleep(3)
    
    buzzer_pin = hw.get('buzzer')
    if buzzer_pin is None:
        test_result('Buzzer', None, "Buzzer not configured")
    else:
        try:
            print(f"\nTesting buzzer on GP{buzzer_pin}...")
            buzzer = PWM(Pin(buzzer_pin))
            
            # Test with 3 short beeps
            buzzer.freq(2000)
            for i in range(3):
                buzzer.duty_u16(32768)  # 50% duty cycle
                utime.sleep_ms(100)
                buzzer.duty_u16(0)
                utime.sleep_ms(100)
            
            buzzer.deinit()
            test_result('Buzzer', True, f"Buzzer on GP{buzzer_pin} - Listen for 3 beeps")
        except Exception as e:
            test_result('Buzzer', False, f"Buzzer error: {e}")

    print()
    utime.sleep(3)

def test_rotary(hw):
    """Test rotary encoder and button."""
    print("="*60)
    print("TEST: Rotary Encoder & Button")
    print("="*60)
    utime.sleep(3)
    
    rotary_clk = hw.get('rotary_clk')
    rotary_dt = hw.get('rotary_dt')
    button_pin = hw.get('button')

    if rotary_clk is None or rotary_dt is None:
        test_result('Rotary Encoder', None, "Rotary encoder not configured")
    else:
        try:
            print(f"\nRotary encoder on GP{rotary_clk} (CLK) and GP{rotary_dt} (DT)")
            clk = Pin(rotary_clk, Pin.IN, Pin.PULL_UP)
            dt = Pin(rotary_dt, Pin.IN, Pin.PULL_UP)
            
            print("\n>>> ROTATE THE ENCODER LEFT, then RIGHT (you have 8 seconds)...")
            
            last_clk = clk.value()
            rotations = {'left': 0, 'right': 0}
            start_time = utime.ticks_ms()
            timeout = 10000  # 10 seconds
            
            while utime.ticks_diff(utime.ticks_ms(), start_time) < timeout:
                current_clk = clk.value()
                if current_clk != last_clk:
                    if dt.value() != current_clk:
                        rotations['right'] += 1
                    else:
                        rotations['left'] += 1
                    last_clk = current_clk
                utime.sleep_ms(1)
            
            print(f"   Left rotations detected: {rotations['left']}")
            print(f"   Right rotations detected: {rotations['right']}")
            
            if rotations['left'] > 0 and rotations['right'] > 0:
                test_result('Rotary Encoder', True, f"Rotation detected in both directions")
            elif rotations['left'] > 0 or rotations['right'] > 0:
                test_result('Rotary Encoder', False, f"Only one direction detected")
            else:
                test_result('Rotary Encoder', False, f"No rotation detected")
        except Exception as e:
            test_result('Rotary Encoder', False, f"Rotary encoder error: {e}")

    if button_pin is None:
        test_result('Rotary Button', None, "Rotary button not configured")
    else:
        try:
            print(f"\nRotary encoder button on GP{button_pin}")
            button = Pin(button_pin, Pin.IN, Pin.PULL_UP)
            
            initial_state = button.value()
            print(f"   Initial state: {'Released' if initial_state else 'Pressed'}")
            print(f"\n>>> PRESS the rotary encoder button (you have 8 seconds)...")
            
            # Wait for button press (looking for LOW since using PULL_UP)
            pressed = False
            start_time = utime.ticks_ms()
            timeout = 8000  # 8 seconds
            
            while utime.ticks_diff(utime.ticks_ms(), start_time) < timeout:
                if button.value() == 0:  # Button pressed (LOW)
                    pressed = True
                    print("   Button press detected!")
                    break
                utime.sleep_ms(10)
            
            if pressed:
                test_result('Rotary Button', True, f"Rotary button press detected")
            else:
                test_result('Rotary Button', False, f"No button press detected within 8 seconds")
        except Exception as e:
            test_result('Rotary Button', False, f"Rotary button error: {e}")

    print()
    utime.sleep(3)

def test_switches(hw):
    """Test switches."""
    print("="*60)
    print("TEST: Switches")
    print("="*60)
    utime.sleep(3)
    
    switches = {
        'Left Switch': hw.get('switch_left'),
        'Middle Switch': hw.get('switch_middle'),
        'Right Switch': hw.get('switch_right')
    }

    for name, pin_num in switches.items():
        if pin_num is None:
            test_result(name, None, f"{name} not configured")
            continue
        
        try:
            switch = Pin(pin_num, Pin.IN, Pin.PULL_UP)
            initial_state = switch.value()
            print(f"\n{name} on GP{pin_num}")
            print(f"   Initial state: {'OFF' if initial_state else 'ON'}")
            print(f"\n>>> PRESS the {name} (you have 8 seconds)...")
            
            # Wait for switch press (looking for LOW since using PULL_UP)
            pressed = False
            start_time = utime.ticks_ms()
            timeout = 8000  # 8 seconds
            
            while utime.ticks_diff(utime.ticks_ms(), start_time) < timeout:
                if switch.value() == 0:  # Switch pressed (LOW)
                    pressed = True
                    print("   Switch press detected!")
                    break
                utime.sleep_ms(10)
            
            if pressed:
                test_result(name, True, f"{name} press detected")
            else:
                test_result(name, False, f"{name} - No press detected within 8 seconds")
        except Exception as e:
            test_result(name, False, f"{name} error: {e}")

    print()
    utime.sleep(3)

def test_display(hw):
    """Test display"""
    print("="*60)
    print("TEST: Display")
    print("="*60)
    utime.sleep(3)
    
    display_scl = hw.get('display_scl')
    display_sda = hw.get('display_sda')
    display_type = hw.get('display_type', 'SSD1306_128x32')

    if display_scl is None or display_sda is None:
        test_result('Display I2C', None, "Display pins not configured")
    elif display_type is None:
        test_result('Display I2C', None, "Display type not configured in hardware.txt")
    else:
        print(f"\nConfigured display type: {display_type}")
        
        # Determine display dimensions from type
        if display_type == 'SSD1306_128x32':
            display_width = 128
            display_height = 32
        elif display_type == 'SSD1306_128x64':
            display_width = 128
            display_height = 64
        else:
            test_result('Display I2C', False, f"Unknown display type: {display_type}")
            display_width = None
            display_height = None
        
        if display_width is not None:
            try:
                print(f"\nInitializing I2C on GP{display_sda} (SDA) and GP{display_scl} (SCL)...")
                i2c = I2C(0, scl=Pin(display_scl), sda=Pin(display_sda), freq=400000)
                
                # Scan for I2C devices
                devices = i2c.scan()
                print(f"   I2C devices found: {[hex(d) for d in devices]}")
                
                if not devices:
                    test_result('Display I2C', False, "No I2C devices detected")
                else:
                    # Try to initialize display
                    try:
                        from ssd1306 import SSD1306_I2C
                        display = SSD1306_I2C(display_width, display_height, i2c)
                        
                        print(f"\n   Testing {display_type} display ({display_width}x{display_height})")
                        
                        # Test patterns based on display type
                        if display_type == 'SSD1306_128x32':
                            # Test 1: Show test message for 128x32
                            print("\n   Pattern 1: Text display (128x32)")
                            display.fill(0)
                            display.text('HW TEST', 0, 0, 1)
                            display.text('Display OK!', 0, 12, 1)
                            display.text('128x32', 0, 24, 1)
                            display.show()
                            print("   >>> Display should show 3 lines of white text on black:")
                            print("       'HW TEST', 'Display OK!', '128x32'")
                            utime.sleep(3)
                            
                            # Test 2: Inverted display
                            print("\n   Pattern 2: Inverted display")
                            display.fill(1)
                            display.text('INVERTED', 28, 4, 0)
                            display.text('DISPLAY', 32, 16, 0)
                            display.show()
                            print("   >>> Display should show white background with black text:")
                            print("       'INVERTED' and 'DISPLAY' centered")
                            utime.sleep(3)
                            
                            # Test 3: Graphics test
                            print("\n   Pattern 3: Graphics test (128x32)")
                            display.fill(0)
                            # Draw border
                            display.rect(0, 0, 128, 32, 1)
                            display.rect(2, 2, 124, 28, 1)
                            # Draw X pattern
                            display.line(10, 6, 118, 26, 1)
                            display.line(118, 6, 10, 26, 1)
                            display.text('GFX OK', 48, 12, 1)
                            display.show()
                            print("   >>> Display should show:")
                            print("       - Double border rectangle")
                            print("       - X pattern (diagonal lines)")
                            print("       - 'GFX OK' text in center")
                            utime.sleep(3)
                            
                        elif display_type == 'SSD1306_128x64':
                            # Test 1: Show test message for 128x64
                            print("\n   Pattern 1: Text display (128x64)")
                            display.fill(0)
                            display.text('HW TEST', 0, 0, 1)
                            display.text('Display OK!', 0, 12, 1)
                            display.text('128x64', 0, 24, 1)
                            display.text('More lines!', 0, 36, 1)
                            display.text('Line 5', 0, 48, 1)
                            display.text('Line 6', 0, 56, 1)
                            display.show()
                            print("   >>> Display should show 6 lines of white text on black:")
                            print("       'HW TEST', 'Display OK!', '128x64',")
                            print("       'More lines!', 'Line 5', 'Line 6'")
                            utime.sleep(3)
                            
                            # Test 2: Inverted display
                            print("\n   Pattern 2: Inverted display")
                            display.fill(1)
                            display.text('INVERTED', 28, 12, 0)
                            display.text('DISPLAY', 32, 28, 0)
                            display.text('128x64', 36, 44, 0)
                            display.show()
                            print("   >>> Display should show white background with black text:")
                            print("       'INVERTED', 'DISPLAY', '128x64' centered vertically")
                            utime.sleep(1)
                            
                            # Test 3: Graphics test
                            print("\n   Pattern 3: Graphics test (128x64)")
                            display.fill(0)
                            # Draw border
                            display.rect(0, 0, 128, 64, 1)
                            display.rect(2, 2, 124, 60, 1)
                            # Draw X pattern
                            display.line(10, 10, 118, 54, 1)
                            display.line(118, 10, 10, 54, 1)
                            display.text('GFX OK', 44, 28, 1)
                            display.show()
                            print("   >>> Display should show:")
                            print("       - Double border rectangle (full height)")
                            print("       - X pattern (diagonal lines)")
                            print("       - 'GFX OK' text in center")
                            utime.sleep(3)
                        
                        # Test 4: Scrolling numbers (common for both)
                        print("\n   Pattern 4: Scrolling numbers")
                        print("   >>> Display should show 'TEST 1/5' through 'TEST 5/5'")
                        print("       changing every 300ms")
                        for i in range(5):
                            display.fill(0)
                            y_center = (display_height - 8) // 2  # Center text vertically
                            display.text(f'TEST {i+1}/5', 30, y_center, 1)
                            display.show()
                            utime.sleep_ms(300)
                        
                        # Final clear
                        print("\n   Pattern 5: Final message")
                        display.fill(0)
                        y_center = (display_height - 8) // 2
                        display.text('Test Complete!', 10, y_center, 1)
                        display.show()
                        print("   >>> Display should show 'Test Complete!'")
                        utime.sleep(1)
                        print("\n   All display tests complete!")
                        
                        test_result('Display I2C', True, f"{display_type} working at {hex(devices[0])}")
                    except ImportError:
                        test_result('Display I2C', None, f"I2C working but ssd1306 module not found")
                    except Exception as e:
                        test_result('Display I2C', False, f"Display init error: {e}")
            except Exception as e:
                test_result('Display I2C', False, f"I2C error: {e}")

    print()
    utime.sleep(3)

def test_thermocouple(hw):
    """Test thermocouple (MAX6675)."""
    print("="*60)
    print("TEST: Thermocouple (MAX6675)")
    print("="*60)
    utime.sleep(3)
    
    tc_sck = hw.get('thermocouple_sck')
    tc_cs = hw.get('thermocouple_cs')
    tc_so = hw.get('thermocouple_so')

    if tc_sck is None or tc_cs is None or tc_so is None:
        test_result('Thermocouple', None, "Thermocouple pins not configured")
    else:
        try:
            print(f"\nThermocouple MAX6675:")
            print(f"   SCK: GP{tc_sck}")
            print(f"   CS:  GP{tc_cs}")
            print(f"   SO:  GP{tc_so}")
            
            # Setup pins
            sck = Pin(tc_sck, Pin.OUT)
            cs = Pin(tc_cs, Pin.OUT)
            so = Pin(tc_so, Pin.IN)
            
            # Keep CS high initially
            cs.on()
            utime.sleep_ms(100)
            
            # Read 16 bits from MAX6675
            cs.off()
            utime.sleep_ms(1)
            
            raw_data = 0
            for i in range(16):
                sck.on()
                utime.sleep_us(1)
                bit = so.value()
                raw_data = (raw_data << 1) | bit
                sck.off()
                utime.sleep_us(1)
            
            cs.on()
            
            # Extract temperature
            temp_raw = (raw_data >> 3) & 0xFFF
            temp_c = temp_raw * 0.25
            fault = raw_data & 1
            
            print(f"   Raw data: 0x{raw_data:04x}")
            print(f"   Temperature: {temp_c:.2f}°C")
            print(f"   Fault bit: {fault}")
            
            if fault:
                test_result('Thermocouple', False, "Thermocouple not connected (fault bit set)")
            elif temp_c < -50 or temp_c > 600:
                test_result('Thermocouple', False, f"Temperature out of range: {temp_c}°C")
            else:
                test_result('Thermocouple', True, f"Temperature reading: {temp_c:.2f}°C")
        except Exception as e:
            test_result('Thermocouple', False, f"Thermocouple error: {e}")

    print()
    utime.sleep(3)

def test_heater(hw):
    """Test heater control output."""
    print("="*60)
    print("TEST: Heater Control Output")
    print("="*60)
    utime.sleep(3)
    
    heater_pin = hw.get('heater')

    if heater_pin is None:
        test_result('Heater', None, "Heater pin not configured")
    else:
        try:
            print(f"\nHeater control on GP{heater_pin}")
            print("   WARNING: This will briefly activate heater output!")
            print("   Ensure heater is disconnected or in a safe state.")
            
            heater = Pin(heater_pin, Pin.OUT)
            heater.off()
            utime.sleep_ms(500)
            
            # Brief pulse
            print("   Pulsing heater output (100ms)...")
            heater.on()
            utime.sleep_ms(100)
            heater.off()
            
            test_result('Heater', True, f"Heater control on GP{heater_pin} - Check with multimeter or mosfet module diode")
        except Exception as e:
            test_result('Heater', False, f"Heater error: {e}")

    print()
    utime.sleep(3)

def test_adc(hw):
    """Test voltage monitoring (ADC)."""
    print("="*60)
    print("TEST: Voltage Monitoring (ADC)")
    print("="*60)
    utime.sleep(3)
    
    adc_pin = hw.get('voltage_divider_adc')

    if adc_pin is None:
        test_result('ADC', None, "ADC pin not configured")
    else:
        try:
            print(f"\nVoltage divider ADC on GP{adc_pin}")
            
            # GP26-28 are ADC0-2 on Pico
            if adc_pin == 26:
                adc_channel = 0
            elif adc_pin == 27:
                adc_channel = 1
            elif adc_pin == 28:
                adc_channel = 2
            else:
                test_result('ADC', False, f"Invalid ADC pin: GP{adc_pin} (must be 26, 27, or 28)")
                adc_channel = None
            
            if adc_channel is not None:
                adc = ADC(adc_channel)
                
                # Read multiple samples
                samples = []
                for i in range(10):
                    samples.append(adc.read_u16())
                    utime.sleep_ms(10)
                
                avg_raw = sum(samples) // len(samples)
                voltage = (avg_raw / 65535.0) * 3.3
                
                print(f"   ADC Channel: {adc_channel}")
                print(f"   Raw value: {avg_raw}")
                print(f"   Voltage: {voltage:.3f}V")
                
                test_result('ADC', True, f"ADC reading: {voltage:.3f}V (adjust for divider ratio)")
        except Exception as e:
            test_result('ADC', False, f"ADC error: {e}")

    print()
    utime.sleep(3)

# ============================================================
# Main Test Function
# ============================================================

def test_hardware(*test_names):
    """
    Run hardware tests.
    
    Args:
        *test_names: Optional test names to run. If no arguments provided, runs all tests.
                    Valid test names: 'leds', 'buzzer', 'rotary', 'switches', 'display',
                                     'thermocouple', 'heater', 'adc'
    
    Examples:
        test_hardware()                          # Run all tests
        test_hardware('leds')                    # Run only LED test
        test_hardware('leds', 'display')         # Run LED and display tests
    """
    global tests_passed, tests_failed, tests_skipped
    tests_passed = 0
    tests_failed = 0
    tests_skipped = 0
    
    print("\n" + "="*60)
    print("   HEATER CONTROLLER HARDWARE TEST SUITE")
    print("="*60)
    print()

    # Load configuration
    print("Loading hardware configuration from hardware.txt...")
    hw = utils.load_hardware_config()
    if hw is None:
        print("✗ FATAL: Could not load hardware.txt")
        print("Please ensure hardware.txt exists in the same directory.")
        return

    print("✓ Configuration loaded successfully")
    print()
    
    # Map of test names to test functions
    available_tests = {
        'leds': test_leds,
        'buzzer': test_buzzer,
        'rotary': test_rotary,
        'switches': test_switches,
        'display': test_display,
        'thermocouple': test_thermocouple,
        'heater': test_heater,
        'adc': test_adc
    }
    
    # Determine which tests to run
    if test_names:
        # Run only specified tests
        tests_to_run = []
        for name in test_names:
            name = name.lower()
            if name in available_tests:
                tests_to_run.append((name, available_tests[name]))
            else:
                print(f"Warning: Unknown test '{name}'. Available tests: {', '.join(available_tests.keys())}")
        
        if not tests_to_run:
            print("No valid tests specified. Use one of:", ', '.join(available_tests.keys()))
            return
    else:
        # Run all tests
        tests_to_run = list(available_tests.items())
    
    # Execute tests
    for test_name, test_func in tests_to_run:
        try:
            test_func(hw)
        except Exception as e:
            print(f"✗ Error running {test_name} test: {e}")
            tests_failed += 1
    
    # Print summary
    print("="*60)
    print("   TEST SUMMARY")
    print("="*60)
    print(f"   Tests Passed:  {tests_passed}")
    print(f"   Tests Failed:  {tests_failed}")
    print(f"   Tests Skipped: {tests_skipped}")
    print(f"   Total Tests:   {tests_passed + tests_failed + tests_skipped}")
    print("="*60)

    if tests_failed == 0:
        print("\n✓ All configured hardware tests passed!")
    else:
        print(f"\n⚠ {tests_failed} test(s) failed. Check connections and configuration.")

    print("\nTest complete.")

# ============================================================
# Main Execution
# ============================================================

if __name__ == '__main__':
    # If run as main script, check for command line arguments
    if len(sys.argv) > 1:
        # Run specific tests from command line
        test_hardware(*sys.argv[1:])
    else:
        # Run all tests
        test_hardware()
