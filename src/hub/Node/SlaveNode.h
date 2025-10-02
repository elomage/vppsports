#ifndef SLAVENODE_H
#define SLAVENODE_H

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
#include "hardware/i2c.h"
#include <vector>
#include <string>

// I2C setup
#define I2C_SLAVE i2c0
#define I2C_IRQ I2C0_IRQ
#define SDA_PIN 4
#define SCL_PIN 5
#define I2C_SLAVE_ADDRESS 0x10
#define I2C_BAUD_RATE 400000

// Command codes
#define CMD_START     0x01
#define CMD_STOP      0x02
#define CMD_SEND_DATA 0x03

char uart_cmd[64];
int uart_index = 0;

extern std::vector<std::string> filelist;
size_t current_file_index = 0;
FIL send_file;
bool file_opened = false;

#define CHUNK_SIZE      256
#define MAX_FILENAME    64
#define BUFFER_SIZE     2048

#define CMD_NEXT_FILE   0x04  // Master: "Send me the next filename"
#define CMD_GET_FILE    0x05  // Master: "Open this file and prep to send"
#define CMD_GET_CHUNK   0x06  // Master: "Send me the next chunk"
#define CMD_DONE        0x07  // Slave: "All done"
#define CMD_ACK         0x08  // Used if you want explicit ack

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
FRESULT fr;
FATFS fs;
FIL file;

uint64_t start_time;

DIR dir;
FILINFO fno;
FRESULT res;

uint8_t chunk[CHUNK_SIZE];

#define HEADER_SIZE 3
#define FLAG_EOF    0x01

static inline bool file_is_at_eof(FIL *fp) {
    // FatFs provides f_tell/f_size
    return f_tell(fp) >= f_size(fp);
}

#endif

