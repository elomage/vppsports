add_library(ads1220 STATIC
    ads1220.cpp
)

target_include_directories(ads1220 PUBLIC
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_link_libraries(ads1220
    pico_stdlib
    hardware_spi
)

add_library(ads1220::ads1220 ALIAS ads1220)
