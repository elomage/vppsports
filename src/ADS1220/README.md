# Project structure

Project is organized into multiple folders:

- `/include` - Commonly used header files 

- `/lib` - Custom written ADC1220 communication library and the SD card library

- `/src` - The main programs orgnized by function:
    - `adc/` - Core ADC reading logic
    - `joystick/` - Joystick/USB HID interface
    - `tests/` - Testing utilities (SD card, checking the communication on PCB)

## Configuration

 TO ENABLE THE JOYSTICK MODE USE DEFINE INTO `include/ads1220_pins.hpp` FILE (to use right pins)

 YOU CAN DEFINE THE NUM OF USED ADCS AND THE DUAL CHANNEL MODE  IN `include/config.hpp` FILE (AT THE MOMENT MAX 4 ADCS):
- Set `NUM_ADCS` (1,2,3, or 4)
- Enable/Disable `DUAL_CHANNEL_MODE` by commenting out 

| NUM OF ADCs | SINGLE MODE (channels) | DUAL CHANNEL MODE (channels) |
|---:|---:|---:|
| 1 | 1 | 2 |
| 2 | 2 | 4 |
| 3 | 3 | 6 |
| 4 | 4 | 8 |

Practically measured **655 Hz** on each channel using 4 ADCs and DUAL CHANNEL MODE