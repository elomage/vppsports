#ifndef I2C_COMMANDS_H
#define I2C_COMMANDS_H

// I2C setup
#define I2C_SLAVE i2c0
#define I2C_IRQ I2C0_IRQ
#define I2C_SLAVE_ADDRESS 0x10
#define I2C_BAUD_RATE 400000

// Command codes
#define CMD_START 0x01
#define CMD_STOP 0x02
#define CMD_SEND_DATA 0x03
#define CMD_NEXT_FILE 0x04
#define CMD_GET_CHUNK 0x05

#define CHUNK_SIZE 256
#define HEADER_SIZE 3
#define FLAG_EOF 0x01
#define MAX_FILENAME 64

#endif