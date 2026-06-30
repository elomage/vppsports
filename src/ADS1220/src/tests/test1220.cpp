#include "pico/stdlib.h"
#include "hardware/spi.h"
#include "hardware/gpio.h"
#include <stdio.h>

#include "include/config.hpp"
#include "ads1220.hpp"

// To use shorter name when using structs with ADS1220 configuration register constants
using namespace ADS1220_REG;

#define MISO_PIN 16
#define MOSI_PIN 19
#define SCK_PIN 18
#define CS1_PIN 17
#define DRDY_PIN 20

static ADS1220 *adc = nullptr;

int main()
{
    stdio_init_all();
    sleep_ms(3000);

    gpio_set_function(MISO_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SCK_PIN, GPIO_FUNC_SPI);
    gpio_set_function(MOSI_PIN, GPIO_FUNC_SPI);

    adc = new ADS1220(spi0, CS1_PIN, DRDY_PIN);

    sleep_ms(1000);

    // Initialize ADC with SPI settings
    adc->init(ADC_SPI_FREQ, ADC_SPI_MODE, ADC_BITS_TRANSFER);
    printf("SPI Initialized for ADC\n");

    // Reset the ADC
    adc->reset();
    printf("ADC Reset\n");

    sleep_ms(1000);

    uint8_t cfg0 = Config0::pack(ADC_MUX, ADC_GAIN, ADC_PGA_BYPASS);
    uint8_t cfg1 = Config1::pack(ADC_DATA_RATE, ADC_MODE, ADC_CONV_MODE, ADC_TEMP_MODE, ADC_BURNOUT);
    uint8_t cfg2 = Config2::pack(ADC_VREF, ADC_FIR, ADC_PSW, ADC_IDAC);
    // Write configurations
    adc->writeRegister(CONFIG0, cfg0);
    adc->writeRegister(CONFIG1, cfg1);
    adc->writeRegister(CONFIG2, cfg2);

    sleep_ms(100);

    printf("cfg0=0x%02X cfg1=0x%02X cfg2=0x%02X\n", cfg0, cfg1, cfg2);

    adc->printRegisterValues();

    printf("Starting SPI transactions - capture now!\n");
    sleep_ms(500);

    adc->start();

    while (true)
    {

        int32_t raw = adc->readDataRaw(true);

        if (raw == 1)
        {
            printf("DRDY timeout or error!\n");
            continue;
        }

        printf("Value: %d\n", raw);

        sleep_ms(200); // pause between transactions so capture is readable
    }

    return 0;
}