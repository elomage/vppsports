# VPPSports Mote

## Setup

* Project setup documentation - `https://www.raspberrypi.com/documentation/microcontrollers/c_sdk.html`
* After cloning the SDK, the submodules need to be updated (missing in the documentation): `git submodule update --init`

### First build

1) `git submodule update --init` - update/download submodules
2) `cp env.example.h env.h` and update the values in `env.h`
3) `mkdir build && cd build`
4) `PICO_SDK_PATH=/path/to/pico/sdk cmake ..`
5) `make mote`

## Notes

### TODO

* Create unit tests for the SD card
* Currently a lot of the failures end in fatal errors for debugging purposes, perhaps some of these failures can be handled non-fatally in the production environment

### Considerations/Possible future problems

* The Log object encoding doesn't currently support multiple versions in the same way as Settings, Sensor and RideConfig objects do. Updating the way that logs are stored may cause problems after updates, if older version logfiles need to be read (consider using the version approach implemented in the aforementioned objects (saving the encoding version id before the object))

