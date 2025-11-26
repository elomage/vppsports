#pragma once

// define SPI ports
#define SPI_ADC spi0
#define SPI_SD spi1

// ADS1220 pins assignment for RPi Pico
#define MISO_PIN 16
#define MOSI_PIN 19
#define SCK_PIN  18
#define CS_PIN   17
#define DRDY_PIN 20

// PINS for SD-Card module
#define MISO_PIN_SD 12
#define MOSI_PIN_SD 11
#define SCK_PIN_SD 10
#define CS_PIN_SD 13

// TODO: Implement mode switching button
#define MODE_SELECT_PIN 21 // dummy button now
