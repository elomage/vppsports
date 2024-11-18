# VPPSports Mote

## Setup

* Project setup documentation - `https://www.raspberrypi.com/documentation/microcontrollers/c_sdk.html`
* After cloning the SDK, the submodules need to be updated (missing in the documentation): `git submodule update --init`

### First build

1) `mkdir build && cd build`
2) `PICO_SDK_PATH=/path/to/pico/sdk cmake ..`
3) `make mote`

