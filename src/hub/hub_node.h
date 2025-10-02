#ifndef HUB_NODE_H
#define HUB_NODE_H

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "hardware/spi.h"
#include "pico/stdlib.h"
#include <vector>
#include "ff.h"

#include "rtc.h"
#include "f_util.h"
#include "hw_config.h"
#include "sd_card.h"
#include "hw_config.c"

#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/gpio.h"
#include "hardware/i2c.h"

#include "pico/time.h"

// Button GPIOs
#define BUTTON_START 0
#define BUTTON_STOP 1
#define BUTTON_SEND_DATA 2

// SPI for SD Card
#define SPI_PORT_SD spi1
#define PIN_SCK_SD 10
#define PIN_MOSI_SD 11
#define PIN_MISO_SD 12
#define PIN_CS_SD 13

// I2C Master
#define i2c_port i2c0
#define I2C_SDA_PIN 4
#define I2C_SCL_PIN 5
#define I2C_BAUD_RATE 100000

// I2C Slave Addresses
#define SLAVE1_ADDR 0x10
#define SLAVE2_ADDR 0x11

uint8_t slave_addrs[] = { SLAVE1_ADDR, SLAVE2_ADDR };

int slaveCount (sizeof(slave_addrs)/sizeof(slave_addrs[0]));

// #define SLAVE3_ADDR 0x12

// Command codes
#define CMD_START     0x01
#define CMD_STOP      0x02
#define CMD_SEND_DATA 0x03

#define CMD_NEXT_FILE   0x04  // Master: "Send me the next filename"
#define CMD_GET_FILE    0x05  // Master: "Open this file and prep to send"
#define CMD_GET_CHUNK   0x06  // Master: "Send me the next chunk"
#define CMD_DONE        0x07  // Slave: "All done"
#define CMD_ACK         0x08  // Used if you want explicit ack

#define CHUNK_SIZE      256
#define MAX_FILENAME    64

// #define UART_BAUD_RATE 900000
#define UART_BAUD_RATE 1000000

FRESULT fr;
FATFS fs;

UINT bw;

bool sensors_busy = false;


#define HEADER_SIZE 3
#define FLAG_EOF    0x01


#endif