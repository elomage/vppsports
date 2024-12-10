cmake_minimum_required(VERSION 3.13)

# initialize the SDK based on PICO_SDK_PATH
# note: this must happen before project()
include(pico_sdk_import.cmake)

project(VPP_mote C CXX ASM)

# initialize the Raspberry Pi Pico SDK
pico_sdk_init()

# rest of your project

add_subdirectory(lib/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico/src/ build)

add_executable(mote
	main.cpp
	helper_funcs.cpp
	TimeKeeper.cpp
	LogKeeper.cpp
	UnitTests.cpp
	Config.cpp
	SDHandler.cpp
	hw_config.c
)

# Add pico_stdlib library which aggregates commonly used features
target_link_libraries(mote
	pico_stdlib
	pico_multicore
	no-OS-FatFS-SD-SDIO-SPI-RPi-Pico
)

pico_enable_stdio_usb(mote 1)
pico_enable_stdio_uart(mote 0)

# create map/bin/hex/uf2 file in addition to ELF.
pico_add_extra_outputs(mote)

