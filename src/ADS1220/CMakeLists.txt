
# Generated CMake Pico project file

cmake_minimum_required(VERSION 3.13)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Initialise pico_sdk from installed location
# (note this can come from environment, CMake cache etc)

# == DO NOT EDIT THE FOLLOWING LINES for the Raspberry Pi Pico VS Code Extension to work ==
if(WIN32)
    set(USERHOME $ENV{USERPROFILE})
else()
    set(USERHOME $ENV{HOME})
endif()
set(sdkVersion 2.2.0)
set(toolchainVersion 14_2_Rel1)
set(picotoolVersion 2.2.0-a4)
set(picoVscode ${USERHOME}/.pico-sdk/cmake/pico-vscode.cmake)
if (EXISTS ${picoVscode})
    include(${picoVscode})
endif()
# ====================================================================================
set(PICO_BOARD pico_w CACHE STRING "Board type")

# Pull in Raspberry Pi Pico SDK (must be before project)
include(pico_sdk_import.cmake)

project(VPP C CXX ASM)

# Initialise the Raspberry Pi Pico SDK
pico_sdk_init()

# Add subsystems ADS1220 library and SD card
add_subdirectory(lib/ads1220)
add_subdirectory(lib/no-OS-FatFS-SD-SPI-RPi-Pico/FatFS_SPI build)


# Add a root-level executable that uses the ads1220 library
add_executable(ads1220_root
    ADS1220.cpp
)

target_include_directories(ads1220_root PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}
)

target_link_libraries(ads1220_root
    pico_stdlib
    pico_multicore
    ads1220::ads1220
    FatFs_SPI
    hardware_spi
    
)

# Enable stdio over USB for convenience (match example behavior)
pico_enable_stdio_usb(ads1220_root 1)

pico_add_extra_outputs(ads1220_root)

# --------------- Add test-write-read executable // TESTING ----------------------
# add_executable(test-read-write
#     test-read-write.cpp
# )

# target_include_directories(test-read-write PRIVATE
#     ${CMAKE_CURRENT_LIST_DIR}
# )

# target_link_libraries(test-read-write
#     pico_stdlib
#     hardware_spi
#     ads1220::ads1220
# )

# # Enable stdio over USB
# pico_enable_stdio_usb(test-read-write 1)
# pico_enable_stdio_uart(test-read-write 0)

# pico_add_extra_outputs(test-read-write)


