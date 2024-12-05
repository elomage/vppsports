# VPPSports Mote

## Setup

* Project setup documentation - `https://www.raspberrypi.com/documentation/microcontrollers/c_sdk.html`
* After cloning the SDK, the submodules need to be updated (missing in the documentation): `git submodule update --init`

### First build

1) `git submodule update --init` - update/download submodules
2) `mkdir build && cd build`
3) `PICO_SDK_PATH=/path/to/pico/sdk cmake ..`
4) `make mote`

