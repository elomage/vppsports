# ADS1220 ADC Data logger
Data acquisition system for reading bending sensor measurements using the ADS1220 24-bit ADC module on Raspberry Pi Pico W.

## Overview

This project reads high-precision analog data from bending sensors via the ADS1220 ADC and logs the measurements to an SD card using the FatFS filesystem.

## Project Structure

```
ADS1220/
├── ADS1220.cpp           # Main application code
├── ads1220_pins.hpp      # GPIO pin definitions
├── config.hpp            # ADC and system configuration
├── lib/                  # External libraries
│   ├── ads1220/          # ADS1220 custom driver library
│   └── no-OS-FatFS-SD-SPI-RPi-Pico/  # SD card FatFS library
└── build/                # Build output directory
```
 
 Edit 'config.hpp' to modify:
 - ADC sampling rate
 - ADC gain settings
 - Buffer sizes
 - Debug/Production mode

## Building

1. Navigate to the build directory:
   ```sh
   cd build
   ```

2. Configure the project:
   ```sh
   cmake ..
   ```

3. Compile:
   ```sh
   make -j4
   ```

4. The compiled `.uf2` file will be in the `build/` directory
