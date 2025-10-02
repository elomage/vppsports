#include "SlaveNode.h"
std::vector<std::string> filelist;

void init_led() {
    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);
    gpio_put(25, 0);
}

void i2c_slave_setup() {
    i2c_init(I2C_SLAVE, I2C_BAUD_RATE);  // 100 kHz
    i2c_set_slave_mode(I2C_SLAVE, true, I2C_SLAVE_ADDRESS);
    gpio_set_function(SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(SDA_PIN);
    gpio_pull_up(SCL_PIN);

}

void stopReading() {
    printf("STOP command received\n");
    gpio_put(25, 0);
}
void startReading() {
    printf("START command received\n");
    gpio_put(25, 1);
}

void build_filelist() {
    filelist.clear();
    FRESULT res;
    DIR dir;
    FILINFO fno;
    res = f_opendir(&dir, "0:");
    if (res == FR_OK) {
        while (f_readdir(&dir, &fno) == FR_OK && fno.fname[0]) {
            if (!(fno.fattrib & AM_DIR)) {
                filelist.push_back(fno.fname);
            }
        }
        f_closedir(&dir);
    }
    current_file_index = 0;
}

const char* get_next_filename() {
    if (current_file_index < filelist.size()) {
        return filelist[current_file_index++].c_str();
    }
    return "END";
}

bool open_send_file(const char* fname) {
    if (file_opened) {
        f_close(&send_file);
        file_opened = false;
    }
    if (f_open(&send_file, fname, FA_READ) == FR_OK) {
        file_opened = true;
        return true;
    }
    return false;
}

static int build_chunk_and_header(uint8_t *tx_buf, uint8_t *flags_out) {
    UINT br = 0;
    uint8_t flags = 0;

    // Read up to CHUNK_SIZE into the data area of tx_buf
    FRESULT res = f_read(&send_file, tx_buf + HEADER_SIZE, CHUNK_SIZE, &br);

    if (res != FR_OK) {
        br = 0;
        flags |= FLAG_EOF;
    } else {
        // If fewer than CHUNK_SIZE were read, we’re at EOF
        if (br < CHUNK_SIZE) {
            flags |= FLAG_EOF;
        } else if (br < CHUNK_SIZE || f_eof(&send_file)) {
            // Full chunk read; check if we just reached EOF exactly at a multiple of CHUNK_SIZE
            flags |= FLAG_EOF;
        }
    }

    // Zero pad remainder to keep fixed transfer length stable (optional but tidy)
    if (br < CHUNK_SIZE) {
        memset(tx_buf + HEADER_SIZE + br, 0, CHUNK_SIZE - br);
    }

    // Fill header
    tx_buf[0] = (uint8_t)(br & 0xFF);
    tx_buf[1] = (uint8_t)((br >> 8) & 0xFF);
    tx_buf[2] = flags;

    *flags_out = flags;

    printf("Slave: br=%u, fptr=%lu, fsize=%lu, flags=0x%02X\n",
       (unsigned)br, (unsigned long)f_tell(&send_file),
       (unsigned long)f_size(&send_file), flags);
       
    return (int)br;
}

int main() {
    stdio_init_all();
    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);
    sleep_ms(1000);
    
    fr = f_mount(&fs, "0:", 1);
    if (fr != FR_OK) {
        while (true) {
            gpio_put(25, 1);
            sleep_ms(500);
            gpio_put(25, 0);
            sleep_ms(2000);
        }
    }
    sleep_ms(5000);

    printf("Initializing I2C slave...\n");
    i2c_slave_setup();

    while (true) {
    if (i2c_get_read_available(I2C_SLAVE)) {
        uint8_t command = i2c_read_byte_raw(I2C_SLAVE);
        // printf("Received I2C command: 0x%02X\n", command);
        if (command == CMD_START) {
            printf("START command received\n");
            // startReading();
        } else if (command == CMD_STOP) {
            printf("STOP command received\n");
            // stopReading();
        } else if (command == CMD_SEND_DATA) {
            build_filelist();
        } else if (command == CMD_NEXT_FILE) {
            printf("Slave: got CMD_NEXT_FILE\n");
            const char* fname = get_next_filename();
            printf("Slave: sending filename: %s\n", fname);
            i2c_write_raw_blocking(I2C_SLAVE, (const uint8_t*)fname, MAX_FILENAME);
            open_send_file(fname);
        }
        else if (command == CMD_GET_CHUNK) {
            printf("Slave: got CMD_GET_CHUNK\n");
            // Prepare a single TX buffer with header + data
            static uint8_t tx_buf[HEADER_SIZE + CHUNK_SIZE];

            if (!file_opened) {
                // No file open => send zero-length, EOF
                tx_buf[0] = 0;
                tx_buf[1] = 0;
                tx_buf[2] = FLAG_EOF;
                memset(tx_buf + HEADER_SIZE, 0, CHUNK_SIZE);
                i2c_write_raw_blocking(I2C_SLAVE, tx_buf, HEADER_SIZE + CHUNK_SIZE);
                continue;
            }

            uint8_t flags = 0;
            int len = build_chunk_and_header(tx_buf, &flags);

            // Send header + padded data in one transaction
            i2c_write_raw_blocking(I2C_SLAVE, tx_buf, HEADER_SIZE + CHUNK_SIZE);

            // Close file if EOF flagged
            if (flags & FLAG_EOF) {
                f_close(&send_file);
                file_opened = false;
            }
        }
    }
    
    tight_loop_contents();
    }
}
