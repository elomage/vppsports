#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "pico/multicore.h"
#include <cstring>

// FatFS includes
#include "ff.h"
#include "diskio.h"
#include "rtc.h"
#include "f_util.h"
#include "hw_config.h"
#include "sd_card.h"

// Project includes
#include "ads1220.hpp"
#include "ads1220_pins.hpp"
#include "config.hpp"

// To use shorter name when using structs with ADS1220 configuration register constants
using namespace ADS1220_REG;

// Buffer management
static char buffer1[BUFFER_SIZE];
static char buffer2[BUFFER_SIZE];
static char *volatile active_buffer = buffer1;
static char *volatile write_buffer = buffer2;
static volatile int active_index = 0;
static volatile int write_size = 0;
volatile bool buffer_ready = false;

// SD card variables
static FRESULT fr;
static FATFS fs;
static FIL file;
static int counter_filename = 1;
char filename[MAX_FILENAME_LEN];
uint64_t start_time;

// Ride variables
double elapsed_seconds = 0;
uint32_t elapsed_time = 0;

void core1_main()
{
    while (true)
    {
        // if buffer ready, start writing to file then mark that buffer is not ready
        if (buffer_ready)
        {
            UINT bw;
            FRESULT res = f_write(&file, write_buffer, write_size, &bw);
            if (res != FR_OK || bw != write_size)
            {
                printf("Write error: %d\n", res);
            }
            f_sync(&file);
            buffer_ready = false; // Signal Core 0: Ready for next buffer
        }
        sleep_ms(1);
    }
}

void init_SD()
{
    spi_init(SPI_SD, 10 * 1000 * 1000); // 10 MHz
    gpio_set_function(MISO_PIN_SD, GPIO_FUNC_SPI);
    gpio_set_function(MOSI_PIN_SD, GPIO_FUNC_SPI);
    gpio_set_function(SCK_PIN_SD, GPIO_FUNC_SPI);
    gpio_init(CS_PIN_SD);
    gpio_set_dir(CS_PIN_SD, GPIO_OUT);
    gpio_put(CS_PIN_SD, 1);
}

void configure_sensor(ADS1220 &adc)
{
    uint8_t cfg0 = Config0::pack(ADC_MUX, ADC_GAIN, ADC_PGA_BYPASS);
    uint8_t cfg1 = Config1::pack(ADC_DATA_RATE, ADC_MODE, ADC_CONV_MODE, ADC_TEMP_MODE, ADC_BURNOUT);
    uint8_t cfg2 = Config2::pack(ADC_VREF, ADC_FIR, ADC_PSW, ADC_IDAC);
    // Write configurations
    adc.writeRegister(CONFIG0, cfg0);
    adc.writeRegister(CONFIG1, cfg1);
    adc.writeRegister(CONFIG2, cfg2);
}
void init_sensor(ADS1220 &adc)
{
    // Initialize SPI pins
    gpio_set_function(MISO_PIN, GPIO_FUNC_SPI);
    gpio_set_function(MOSI_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SCK_PIN, GPIO_FUNC_SPI);

    // Initialize ADC with SPI settings
    adc.init(ADC_SPI_FREQ, ADC_SPI_MODE, ADC_BITS_TRANSFER);
    printf("SPI Initialized\n");

    // Reset the ADC
    adc.reset();
    printf("ADC Reset\n");
}

void generate_filename(char *buffer, size_t len, const char *base_name)
{
    FILINFO fno;
    snprintf(buffer, len, "%s.BIN", base_name);

    // find the right counter for filenames
    while (f_stat(buffer, &fno) == FR_OK)
    {
        counter_filename++;
        snprintf(buffer, len, "%s_%d.BIN", base_name, counter_filename);
    }
    printf("Generated filename: %s\n", buffer);
}

int main()
{
    stdio_init_all();
    // Initialize LED
    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);
    gpio_put(25, 0);

    // Initialize ADS1220 object using SPI0 and pins defined in ads1220_pins.hpp
    ADS1220 adc(SPI_ADC, CS_PIN, DRDY_PIN);
    init_sensor(adc);
    sleep_ms(100);

    configure_sensor(adc);
    sleep_ms(100);

    // init_SD();
    // sleep_ms(100);

    // Verify configuration (DEBUG)
    adc.printRegisterValues();
    sleep_ms(100);

    // // Mount the filesystem SD card with dir 0:/
    // fr = f_mount(&fs, "0:", 1);
    // // if goes wrong blink the BUILT-IN LED
    // if (fr != FR_OK)
    // {
    //     while (true)
    //     {
    //         // long off = mount error
    //         gpio_put(25, 1);
    //         sleep_ms(500);
    //         gpio_put(25, 0);
    //         sleep_ms(500);
    //     }
    // }
    // printf("SD Card mounted\n");

    // generate_filename(filename, sizeof(filename), BASE_FILENAME);

    // // Create the file with correct name
    // fr = f_open(&file, filename, FA_WRITE | FA_CREATE_ALWAYS);
    // if (fr != FR_OK)
    // {
    //     while (true)
    //     {
    //         // Fast blink - file error
    //         gpio_put(25, 1);
    //         sleep_ms(200);
    //         gpio_put(25, 0);
    //         sleep_ms(200);
    //     }
    // }
    // printf("Recording to: %s\n", filename);

    // Launch SD writer on Core 1
    // multicore_launch_core1(core1_main);

    // LED solid ON = recording
    gpio_put(25, 1);
    start_time = time_us_64();
    // START DATA CONVERSIONS
    adc.start();
    printf("ADC started - recording at 330 SPS\n");

#ifdef DEBUG_MODE
    while (true)
    {
        int32_t raw = adc.readDataRaw(true);

        if (raw == 1)
        {
            printf("DRDY timeout or error!\n");
            continue;
        }
        else
        {
            // Use external 3.3 reference
            float voltage = adc.rawToVoltage(raw, VREF_VOLTAGE, ADC_GAIN);
            printf("Raw: %ld, Voltage: %.6f V (%.3f mV)\n", raw, voltage, voltage * 1000.0f);
        }

        sleep_ms(100);
    }
#endif

#ifdef PRODUCTION_MODE
    while (true)
    {
        elapsed_time = time_us_64() - start_time;
        elapsed_seconds = elapsed_time / 1000000.0;

        int32_t raw = adc.readDataRaw(true);

        // Skip errors
        if (raw == 1) {
            continue; 
        }

        ADCRecord rec = {
            .timestamp_us = elapsed_time,
            .raw_value = raw};

        if (active_index + sizeof(ADCRecord) >= BUFFER_SIZE)
        {
            // make the SWAP
            while (buffer_ready)
            {
                sleep_us(100);
            }
            char *temp = active_buffer;
            active_buffer = write_buffer;
            write_buffer = temp;

            write_size = active_index;
            active_index = 0;
            buffer_ready = true;
        }
        memcpy(active_buffer + active_index, &rec, sizeof(ADCRecord));
        active_index += sizeof(ADCRecord);
    }
#endif

    f_close(&file);
    adc.powerDown();
    return 0;
}

// TODO: swtich between the modes: SENSOR and SLAVE
// SENSOR - reads sensor data and save to SD card
// SLAVE - reads SD card and sends data to MASTER node
// void run_sensor_mode();
// void run_slave_mode();
