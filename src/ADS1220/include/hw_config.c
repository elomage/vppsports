#include "hw_config.h"
#include "ads1220_pins.hpp"

static spi_t spi[] = {
    {
        .hw_inst = SPI_SD,                 // spi1
        .miso_gpio = MISO_PIN_SD,          // 12
        .mosi_gpio = MOSI_PIN_SD,          // 11
        .sck_gpio = SCK_PIN_SD,            // 10
        .baud_rate = 125 * 1000 * 1000 / 4  // 31250000 Hz
    }};

/* SPI Interface */
static sd_spi_if_t spi_if[] = {
    {
    .spi = spi,  // Pointer to the SPI driving this card
    .ss_gpio = CS_PIN_SD  // The SPI slave select GPIO for this SD card
    }
};

static sd_card_t sd_card[] = {
    {
        .type = SD_IF_SPI,
        .spi_if_p = &spi_if[0] // Pointer to the SPI interface driving this card
    }};

size_t sd_get_num()
{
    return count_of(sd_card);
}

sd_card_t *sd_get_by_num(size_t num)
{
    if (num < sd_get_num())
        return &sd_card[num];
    return NULL;
}

size_t spi_get_num()
{
    return count_of(spi);
}

spi_t *spi_get_by_num(size_t num)
{
    if (num < spi_get_num())
        return &spi[num];
    return NULL;
}