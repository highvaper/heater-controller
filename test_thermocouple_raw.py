import machine
import utime

# Test thermocouple raw read
# Copy and paste this into REPL or run directly

hardware_pin_termocouple_sck = 6
hardware_pin_termocouple_cs = 7 
hardware_pin_termocouple_so = 8

print("Thermocouple Raw Read Test")
print("=" * 40)
print(f"SCK pin: {hardware_pin_termocouple_sck}")
print(f"CS pin:  {hardware_pin_termocouple_cs}")
print(f"SO pin:  {hardware_pin_termocouple_so}")
print("=" * 40)

try:
    # Setup pins
    sck = machine.Pin(hardware_pin_termocouple_sck, machine.Pin.OUT)
    cs = machine.Pin(hardware_pin_termocouple_cs, machine.Pin.OUT)
    so = machine.Pin(hardware_pin_termocouple_so, machine.Pin.IN)
    
    print("✓ Pins initialized")
    
    # Keep CS high initially
    cs.on()
    utime.sleep_ms(100)
    print("✓ CS set high")
    
    # Read 16 bits from MAX6675
    cs.off()  # Pull CS low to start read
    utime.sleep_ms(1)  # Small delay
    
    raw_data = 0
    for i in range(16):
        sck.on()
        utime.sleep_us(1)
        bit = so.value()
        raw_data = (raw_data << 1) | bit
        sck.off()
        utime.sleep_us(1)
    
    cs.on()  # Pull CS high to end read
    print(f"✓ Raw data read: {raw_data:016b} (0x{raw_data:04x})")
    
    # Extract temperature (bits 15:3 are temperature, divide by 32 for 0.25°C resolution)
    temp_raw = (raw_data >> 3) & 0xFFF
    temp_c = temp_raw * 0.25
    
    # Check if thermocouple is connected (bit 0 = fault bit, should be 0)
    fault = raw_data & 1
    
    print(f"✓ Temperature: {temp_c:.2f}°C")
    print(f"✓ Fault bit: {fault} {'(thermocouple connected)' if fault == 0 else '(THERMOCOUPLE NOT CONNECTED!)'}")
    
    if temp_c < -50 or temp_c > 300:
        print("⚠ WARNING: Temperature out of reasonable range!")
    
except Exception as e:
    print(f"✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
