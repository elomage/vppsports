#include "hub_node.h"


void init_buttons() {
    gpio_init(BUTTON_START);
    gpio_set_dir(BUTTON_START, GPIO_IN);
    gpio_pull_up(BUTTON_START);

    gpio_init(BUTTON_STOP);
    gpio_set_dir(BUTTON_STOP, GPIO_IN);
    gpio_pull_up(BUTTON_STOP);

    gpio_init(BUTTON_SEND_DATA);
    gpio_set_dir(BUTTON_SEND_DATA, GPIO_IN);
    gpio_pull_up(BUTTON_SEND_DATA);
}

void init_sdcard() {
    spi_init(SPI_PORT_SD, 1000 * 1000);
    gpio_set_function(PIN_SCK_SD, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI_SD, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MISO_SD, GPIO_FUNC_SPI);

    gpio_init(PIN_CS_SD);
    gpio_set_dir(PIN_CS_SD, GPIO_OUT);
    gpio_put(PIN_CS_SD, 1);
}

void init_i2c() {
    i2c_init(i2c_port, 400 * 1000); // 400kHz I2C clock
    gpio_set_function(I2C_SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(I2C_SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(I2C_SDA_PIN);
    gpio_pull_up(I2C_SCL_PIN);
}

void send_command_to_all(uint8_t command) {
    uint8_t cmd_buf[1] = {command};

    for (int i = 0; i < slaveCount; ++i) {
        i2c_write_blocking(i2c_port, slave_addrs[i], cmd_buf, 1, false);
        printf("Sent command 0x%02X to slave 0x%02X\n", command, slave_addrs[i]);
        sleep_ms(10); // Short delay between writes
    }
}
#define MAX_FILENAME_LENGTH 64
uint8_t file_name_buf[MAX_FILENAME_LENGTH] = {0};

void send_command_to_slave(uint8_t slave_addr, uint8_t command) {
    uint8_t cmd_buf[1] = {command};
    i2c_write_blocking(i2c_port, slave_addr, cmd_buf, 1, false);
    printf("Sent command 0x%02X to slave 0x%02X\n", command, slave_addr);
}

void fetch_files_from_slaves() {
    for (int i = 0; i < slaveCount; ++i) {

        uint8_t cmd = CMD_SEND_DATA;
        i2c_write_blocking(i2c_port, slave_addrs[i], &cmd, 1, false); // initialize

        while (1) {
            cmd = CMD_NEXT_FILE;
            uint8_t fname_buf[MAX_FILENAME] = {0};
            i2c_write_blocking(i2c_port, slave_addrs[i], &cmd, 1, false);  // nostop=true!
            i2c_read_blocking(i2c_port, slave_addrs[i], fname_buf, MAX_FILENAME, false); // nostop=false!
            printf("Got filename: %s\n", fname_buf);

            if (strcmp((char*)fname_buf, "END") == 0)
                break;

            FIL file;
            FRESULT fr = f_open(&file, (const TCHAR*)fname_buf, FA_WRITE | FA_CREATE_ALWAYS);
            if (fr != FR_OK) {
                printf("Failed to create file: %s (FatFs error: %d)\n", fname_buf, fr);
                continue;
            }
            while (1) {
                printf("in chunk loop\n");
                cmd = CMD_GET_CHUNK;

                // RX buffer holds header + max data
                uint8_t rx_buf[HEADER_SIZE + CHUNK_SIZE];

                // Request next chunk
                i2c_write_blocking(i2c_port, slave_addrs[i], &cmd, 1, false); // nostop=true ok
                // Read header + padded data in one go
                int read_bytes = i2c_read_blocking(i2c_port, slave_addrs[i], rx_buf, HEADER_SIZE + CHUNK_SIZE, false);

                if (read_bytes != (HEADER_SIZE + CHUNK_SIZE)) {
                    printf("I2C read error: got %d bytes\n", read_bytes);
                    // handle / retry / abort
                    break;
                }

                // Parse header
                uint16_t len = (uint16_t)rx_buf[0] | ((uint16_t)rx_buf[1] << 8);
                uint8_t flags = rx_buf[2];
                printf("Master: read %d bytes (len=%u, flags=0x%02X)\n", read_bytes, len, flags);


                if (len > CHUNK_SIZE) {
                    printf("Protocol error: len=%u > CHUNK_SIZE\n", len);
                    // handle / abort
                    break;
                }

                // Write only 'len' bytes
                UINT bw = 0;
                FRESULT fr = f_write(&file, rx_buf + HEADER_SIZE, len, &bw);
                if (fr != FR_OK || bw != len) {
                    printf("Write error (fr=%d, bw=%u, expected=%u)\n", fr, bw, len);
                    break;
                }

                // If EOF flag set, we're done with this file
                if (flags & FLAG_EOF) {
                    printf("EOF reached for file: %s\n", fname_buf);
                    break;
                }
            }

            f_close(&file);
            printf("File written: %s\n", fname_buf);
        }
    }
    printf("All files transferred.\n");
}

int main() {
    stdio_init_all();
    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);
    sleep_ms(100);
    init_i2c();
    sleep_ms(100);
    init_buttons();
    sleep_ms(100);
    init_sdcard();
    sleep_ms(5000);

    fr = f_mount(&fs, "0:", 1);
    sleep_ms(10);
    if (fr != FR_OK) {
        printf("ERROR: Could not mount filesystem (%d)\r\n", fr);
        while (true);
    }
    
    sleep_ms(5000);
    printf("Starting...\n");
    while (true) {
        bool start_state = gpio_get(BUTTON_START);
        bool stop_state = gpio_get(BUTTON_STOP);
        bool send_data_state = gpio_get(BUTTON_SEND_DATA);

        if (!start_state && !sensors_busy) {
            sensors_busy = true;
            send_command_to_slave(SLAVE2_ADDR, CMD_START);
            sleep_ms(300);
        }

        if (!stop_state && sensors_busy) {
            sensors_busy = false;
            send_command_to_all(CMD_STOP);
            sleep_ms(300);
        }

        if (!send_data_state && !sensors_busy) {
            sleep_ms(300);
            sensors_busy = true;
            // send_command_to_slave(SLAVE2_ADDR, CMD_SEND_DATA);
            // fetch_files_from_slave(SLAVE2_ADDR);
            fetch_files_from_slaves();
            printf("done\n");
        }
    }
}