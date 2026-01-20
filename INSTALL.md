# Installation Guide

## Thonny IDE

### Step 1: Install Thonny

1. Download Thonny from: https://thonny.org/
2. Install Thonny on your system (Windows, macOS, or Linux) or use the Portable version which can be run from a folder without being installed.
3. Launch Thonny

### Step 2: Flash MicroPython (if not already done)

1. Connect your device while holding the BOOTSEL button
2. In Thonny, go to **Tools > Options > Interpreter**
3. Select **MicroPython (Raspberry Pi Pico)**
4. Click **Install or update MicroPython**
5. Select your device from the device list
6. Click **Install** and wait for completion
7. The device will reboot with MicroPython

### Step 3: Connect to Your Device

1. In Thonny, go to **Tools > Options > Interpreter**
2. Select **MicroPython (Raspberry Pi Pico)**
3. Choose the correct **Port** (usually auto-detected)
4. Click **OK**
5. You should see `>>>` in the Shell window at the bottom

### Step 4: Copy Files to the Device

Using Thonny's file explorer:

1. Go to **View > Files** to show the file explorer panel
2. The top pane shows files on your computer
3. The bottom pane shows files on the device

**Copy files:**
1. In the top pane, navigate to your heater-controller folder
2. Select these files and folders
3. Right-click and select **Upload to /**


### Step 5: Upload or Update Profiles

**To add a new profile:**
1. In the top pane, navigate to your `profiles/` or `profiles_autosession/` folder
2. Select your new profile file (e.g., `my_custom_profile.txt`)
3. Right-click and select **Upload to /profiles** or **Upload to /profiles_autosession**
4. The new profile will be available in the controller's menu

**To update an existing profile:**
1. Edit your profile file on your computer (in the heater-controller folder)
2. In Thonny's top pane, navigate to the edited profile
3. Right-click and select **Upload to /profiles** (or `/profiles_autosession`)
4. When prompted to overwrite, click **Yes**
5. The device will now use the updated profile

**To create a profile directly on the device:**
1. In the bottom pane (device files), navigate to `/profiles` or `/profiles_autosession`
2. Right-click and select **New file**
3. Name your file (e.g., `my_profile.txt`)
4. Edit the file in Thonny with your profile settings
5. Save with **Ctrl+S** or File > Save
6. The profile is immediately available on the device

**Profile file locations:**
- **Regular profiles** → `/profiles/` - Used for manual temperature/power control
- **AutoSession profiles** → `/profiles_autosession/` - Used for time-based temperature automation

### Step 6: Configuring Hardware Settings

**IMPORTANT:** Before first use, you must edit `hardware.txt` to match your actual GPIO pin connections if hardware configuration is different from the default.

**To edit hardware.txt before deployment:**
1. On your computer, open `hardware.txt` in a text editor
2. Update the GPIO pin numbers to match your wiring (see README.md for pin assignments)
3. Save the file
4. Upload to device: In Thonny, right-click `hardware.txt` → **Upload to /**

**To edit hardware.txt on the device:**
1. In the bottom pane (device files), double-click `hardware.txt`
2. Edit the GPIO pin assignments to match your hardware
3. Common settings to configure:
   - Display pins (SDA, SCL)
   - Thermocouple pins (SCK, CS, SO)
   - Heater output pins
   - LED pins (red, green, blue)
   - Rotary encoder pins
   - Button/switch pins
4. Save with **Ctrl+S**
5. Soft reset the device: Press **Ctrl+D** in the Shell or press the Stop button

### Step 7: Test the Installation

1. In Thonny's Shell window, type:
   ```python
   import test_hardware
   test_hardware.test_hardware()
   ```
2. This will run hardware tests to verify your setup

### Step 8: Test Normal Startup

1. In Thonny's Shell window, type:
   ```python
   import main
   ```
2. This will start the controller once for testing. You should see the display initialize and the controller start up.

3. **To test automatic startup**: 
   - Click the **Stop/Restart** button in Thonny (red stop icon), or
   - Press **Ctrl+D** in the Shell for a soft reset
   - The controller should automatically restart and run `main.py`

4. **To verify it works standalone**:
   - Disconnect from Thonny
   - Unplug the device from USB
   - Connect the device to your battery/power supply
   - The controller should start automatically

**Note:** MicroPython automatically runs `main.py` on every boot/reset, so once deployed, the controller will start whenever the device is powered on.

### Debugging and Watchdog Timer

**The Watchdog Timer Issue:**

The controller uses a hardware watchdog timer for safety. If the watchdog isn't fed regularly, it automatically reboots the device. This can make it difficult to connect with Thonny for debugging because the device keeps rebooting.

**Connecting to a Running Controller:**

If the controller is already running and you want to connect with Thonny:

1. Open Thonny and ensure it's set to connect to your device
2. Power on or reset your device
3. **Watch for the LED flash at startup** (happens in the first few seconds)
4. **Quickly click the Stop button** in Thonny (red stop icon) just as you see the LED flash
5. This interrupts `main.py` before the watchdog timer starts
6. You should now have access to the REPL (`>>>` prompt)

**Disabling the Watchdog for Debugging:**

To disable the watchdog and see all print output on your computer:

1. **Hold down the middle button** while powering on or resetting the device
2. Keep holding until you see "Watchdog: Off" message
3. The controller will start with the watchdog **disabled**
4. The device won't auto-reboot, allowing you to see errors and debug when starting using ```import main```

**Running with Print Output Visible:**

Once watchdog is disabled:

1. Press the **Stop button** in Thonny to interrupt the controller
2. In the Shell, type:
   ```python
   import main
   ```
3. The controller will start and all `print()` statements will appear in Thonny's Shell
4. You can see initialization messages, errors, and debug output
5. Use **Ctrl+C** to stop execution and return to the REPL

**When to Disable Watchdog:**
- ✓ When developing and debugging
- ✓ When you need to see detailed error messages
- ✓ When testing hardware and need the controller to stay connected
- ✗ Do NOT disable for normal operation (safety feature)

**Re-enabling Watchdog:**

Simply reset the device without holding any button, and the watchdog will be enabled normally.

### Updating Files with Thonny

**To update Python code or configuration files:**
1. Make changes to files on your computer
2. In Thonny's top pane, navigate to the modified file
3. Right-click and **Upload to /** (or appropriate directory like `/profiles`)
4. Confirm overwrite when prompted
5. Soft reset the device: Press **Ctrl+D** in the Shell, or disconnect and reconnect power

**Quick updates for common tasks:**
- **Update profile** → Edit `.txt` file, upload to `/profiles/` or `/profiles_autosession/`
- **Update hardware config** → Edit `hardware.txt`, upload to `/`
- **Update main code** → Edit `.py` file, upload to `/`, then soft reset
- **Add new profile** → Create `.txt` file, upload to `/profiles/` or `/profiles_autosession/`

**Tip:** After uploading profiles, you don't need to restart - they're loaded on-demand from the menu
