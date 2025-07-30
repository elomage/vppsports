#ifndef ADXL_H
#define ADXL_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "hardware/spi.h"
#include "hardware/uart.h"
#include "pico/stdlib.h"
#include <vector>
#include "ff.h"
#include "pico/time.h"
#include "diskio.h"
#include "rtc.h"
#include "f_util.h"
#include "hw_config.h"
#include "sd_card.h"
#include "hw_config.c"
#include "pico/multicore.h"

#define SPI_PORT spi0
#define SPI_PORT_SD spi1

// Pins for ADXL375 (SPI)
#define PIN_MISO 16
#define PIN_MOSI 19
#define PIN_SCK 18
#define PIN_CS 17

// Pins for SD Card (SPI)
#define PIN_MISO_SD 12
#define PIN_MOSI_SD 11
#define PIN_SCK_SD 10
#define PIN_CS_SD 13

// ADXL375 Registers
#define REG_DEVID_AD 0x00
#define REG_DEVID_MST 0x01
#define REG_PARTID 0x02
#define REG_REVID 0x03
#define REG_STATUS 0x04
#define REG_FIFO_SAMPLES 0x29
#define REG_RANGE 0x2C
#define REG_POWER_CTL 0x2D
#define REG_RESET 0x2F
#define REG_FILTER 0x28

#define XDATA3 0x08
#define XDATA2 0x09
#define XDATA1 0x0A
#define YDATA3 0x0B
#define YDATA2 0x0C
#define YDATA1 0x0D
#define ZDATA3 0x0E
#define ZDATA2 0x0F
#define ZDATA1 0x10

// Device Values
#define VAL_RESET 0x52
#define DATA_READY_MASK 0x01

// Sensitivity
#define SENSITIVITY_X 19.5
#define SENSITIVITY_Y 19.5
#define SENSITIVITY_Z 19.5

#define DEVID_AD 0xAD
#define DEVID_MST 0x1D
#define RANGE_10G 0x01
#define RANGE_20G 0x02
#define RANGE_40G 0x03
#define MEASURE_MODE 0x00

#define READ_SPEED_4000 0x00
#define READ_SPEED_2000 0x01
#define READ_SPEED_1000 0x02
#define READ_SPEED_500 0x03
#define READ_SPEED_250 0x04

#define BUFFER_SIZE 2048

#define CHUNK_SIZE 512

char buffer1[BUFFER_SIZE];
char buffer2[BUFFER_SIZE];

char* volatile active_buffer = buffer1;
char* volatile write_buffer = buffer2;
volatile int active_index = 0;
volatile int write_size = 0;
volatile bool buffer_ready = false;

double elapsed_seconds = 0;
uint32_t elapsed_time = 0;
int counter_filename = 1;
char filename[32];
uint64_t start_time;

FRESULT fr;
FATFS fs;
FIL file;

#pragma pack(push, 1)
struct SensorRecord {
    uint32_t timestamp_us;
    int32_t x;
    int32_t y;
    int32_t z;
};
#pragma pack(pop)

#endif

