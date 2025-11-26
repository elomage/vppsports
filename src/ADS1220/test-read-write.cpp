#include "ads1220.hpp"
#include "ads1220_pins.hpp"

#include "pico/stdlib.h"
#include "hardware/spi.h"

using namespace ADS1220_REG;

#define VREF_VOLTAGE (3.3f)

int main()
{
    stdio_init_all();

    // Initialize ADS1220 object using SPI0 and pins defined in ads1220_pins.hpp
    ADS1220 adc(spi0, CS_PIN, DRDY_PIN);

    gpio_set_function(MISO_PIN, GPIO_FUNC_SPI);
    gpio_set_function(MOSI_PIN, GPIO_FUNC_SPI);
    gpio_set_function(SCK_PIN, GPIO_FUNC_SPI);

    adc.init(1000000, 1, 8);

    uint8_t cfg0 = Config0::pack(
        Config0::MUX_AIN0_AIN1,
        Config0::GAIN_128,
        Config0::PGA_BYPASS_OFF);

    uint8_t cfg1 = Config1::pack(
        Config1::DR_1000SPS,
        Config1::MODE_NORMAL,
        Config1::CM_SINGLE,
        Config1::TS_ON,
        Config1::BCS_ON
    );

    adc.reset();
    adc.writeRegister(CONFIG0, cfg0);
    adc.writeRegister(CONFIG1, cfg1);
    adc.start();


    while (true)
    {
        adc.printRegisterValues();
    }

    return 0;
}
