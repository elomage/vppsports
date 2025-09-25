
#include "adxl357.h"

void core1_main() {
    while (true) {
        if (buffer_ready) {
            UINT bw;
            FRESULT res = f_write(&file, write_buffer, write_size, &bw);
            if (res != FR_OK || bw != write_size) {
                printf("Write error: %d\n", res);
            }
            f_sync(&file);
            buffer_ready = false;
        }
        sleep_ms(1);
    }
}

void init_sensor() {
    spi_init(SPI_PORT, 10 * 1000 * 1000);
    gpio_set_function(PIN_MISO, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK, GPIO_FUNC_SPI);
    gpio_init(PIN_CS);
    gpio_set_dir(PIN_CS, GPIO_OUT);
    gpio_put(PIN_CS, 1);
}

void init_sdcard() {
    spi_init(SPI_PORT_SD, 10 * 1000 * 1000);
    gpio_set_function(PIN_MISO_SD, GPIO_FUNC_SPI);
    gpio_set_function(PIN_MOSI_SD, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SCK_SD, GPIO_FUNC_SPI);
    gpio_init(PIN_CS_SD);
    gpio_set_dir(PIN_CS_SD, GPIO_OUT);
    gpio_put(PIN_CS_SD, 1);
}

void spi_write_register(uint8_t reg, uint8_t value) {
    uint8_t data[] = { static_cast<uint8_t>(reg << 1), value };
    gpio_put(PIN_CS, 0);
    spi_write_blocking(SPI_PORT, data, 2);
    gpio_put(PIN_CS, 1);
}

uint8_t spi_read_register(uint8_t reg) {
    uint8_t data[] = { static_cast<uint8_t>(0x01 | (reg << 1)), 0xFF };
    uint8_t recv[2] = {0};
    gpio_put(PIN_CS, 0);
    spi_write_read_blocking(SPI_PORT, data, recv, 2);
    gpio_put(PIN_CS, 1);
    return recv[1];
}

void measure_on() {
    spi_write_register(REG_POWER_CTL, 0x08);
}

void measure_off() {
    spi_write_register(REG_POWER_CTL, 0x00);
}

int32_t read_axis(uint8_t reg_high, uint8_t reg_mid, uint8_t reg_low) {
    uint32_t raw = (spi_read_register(reg_high) << 16) |
                   (spi_read_register(reg_mid) << 8) |
                   (spi_read_register(reg_low));

    raw >>= 4;
    if (raw & 0x80000) {
        raw |= 0xFFF00000;
    }
    return (int32_t)raw;
}

void reg_update(uint8_t reg, uint8_t val, uint8_t mask = 0x00) {
    uint8_t data = spi_read_register(reg);
    spi_write_register(reg, (data & ~mask) | val);
}

void set_measure_range(uint8_t measure_range) {
    reg_update(REG_RANGE, measure_range, 0xFF);
}

void generate_filename(char *buffer, size_t len, const char *base_name) {
    FILINFO fno;

    snprintf(buffer, len, "%s.BIN", base_name);
    while (f_stat(buffer, &fno) == FR_OK) {
        counter_filename++;
        snprintf(buffer, len, "%s_%d.BIN", base_name, counter_filename);
    }
}
// FOR DEBUG
// void read_print(uint8_t reg, const char* txt) {
//     uint8_t data = spi_read_register(reg);
//     printf("%s: 0x%02X %08b\n", txt, data, data);
// }

void set_odr(uint8_t odr_code) {
    reg_update(REG_FILTER, odr_code, 0x0F);
}

bool data_ready() {
    uint8_t status = spi_read_register(REG_STATUS);
    return status & DATA_READY_MASK;
}

float convert_to_g(int raw_reading, float sensitivity) {
    return (raw_reading * sensitivity) / 1000000.0;
}

int main() {
    stdio_init_all();
    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);

    init_sensor();
    sleep_ms(100);
    init_sdcard();
    sleep_ms(100);
    
    spi_write_register(REG_RESET, VAL_RESET);
    sleep_ms(100);
    set_measure_range(RANGE_10G);
    set_odr(READ_SPEED_500);

    // FOR DEBUG
    // sleep_ms(5000);
    // read_print(REG_POWER_CTL, "POWER_CTL");
    // read_print(REG_DEVID_AD, "DEVID_AD");
    // read_print(REG_DEVID_MST, "DEVID_MST");
    // read_print(REG_PARTID, "PARTID");
    // read_print(REG_REVID, "REVID");
    // read_print(REG_FIFO_SAMPLES, "FIFO_SAMPLES");
    // read_print(REG_STATUS, "STATUS");
    // read_print(REG_POWER_CTL, "POWER_CTL");
    // read_print(REG_RANGE, "MEASURE RANGE");
    // read_print(REG_FILTER, "FILTER");

    sleep_ms(100);

    fr = f_mount(&fs, "0:", 1);
    if (fr != FR_OK) {
        while (true) {
            gpio_put(25, 1);
            sleep_ms(500);
            gpio_put(25, 0);
            sleep_ms(2000);
        }
    }
    sleep_ms(100);

    generate_filename(filename, sizeof(filename), "brauciens");

    fr = f_open(&file, filename, FA_WRITE | FA_CREATE_ALWAYS);
    if (fr != FR_OK) {
        while (true){
            gpio_put(25, 1);
            sleep_ms(500);
            gpio_put(25, 0);
            sleep_ms(1000);
        }
    }
    sleep_ms(5000);
    multicore_launch_core1(core1_main);

    gpio_put(25, 1);
    start_time = time_us_64();
    measure_on();

    while (true) {
        if (!data_ready()) {
            continue;
        }

            elapsed_time = time_us_64() - start_time;
            elapsed_seconds = elapsed_time / 1000000.0;

            int32_t x = read_axis(XDATA3, XDATA2, XDATA1);
            int32_t y = read_axis(YDATA3, YDATA2, YDATA1);
            int32_t z = read_axis(ZDATA3, ZDATA2, ZDATA1);

            // FOR DEBUG
            // float acc_x = convert_to_g(x, SENSITIVITY_X);
            // float acc_y = convert_to_g(y, SENSITIVITY_Y);
            // float acc_z = convert_to_g(z, SENSITIVITY_Z);
            // printf("%.6f ,X: %.6fg, Y: %.6fg, Z: %.6fg\n", elapsed_seconds, acc_x, acc_y, acc_z);
        
            SensorRecord rec = {
                .timestamp_us = elapsed_time,
                .x = x,
                .y = y,
                .z = z
            };

            if (active_index + sizeof(SensorRecord) >= BUFFER_SIZE) {
                if (!buffer_ready) {
                    char* temp = active_buffer;
                    active_buffer = write_buffer;
                    write_buffer = temp;
            
                    write_size = active_index;
                    active_index = 0;
                    buffer_ready = true;
                } else {
                    sleep_ms(1);
                    continue;
                }
            }

            memcpy(active_buffer + active_index, &rec, sizeof(SensorRecord));
            active_index += sizeof(SensorRecord);
            
            sleep_ms(1);
    }

    f_close(&file);
    measure_off();
    return 0;
}
