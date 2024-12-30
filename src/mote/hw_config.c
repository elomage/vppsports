#include "hw_config.h"
#include "env.h"

/**
 * @file hw_config.c
 *
 * Defines how to communicate with the SD card (see https://github.com/carlk3/no-OS-FatFS-SD-SDIO-SPI-RPi-Pico/tree/6bdb39f96fe8b897aff12bf3416e32515792e318/examples)
 */

static spi_t spi = {
    .hw_inst = SPI_SET,
    .miso_gpio = SPI_MISO_GPIO,
    .mosi_gpio = SPI_MOSI_GPIO,
    .sck_gpio = SPI_SCK_GPIO,
    .baud_rate = SPI_BAUD_RATE
};

static sd_spi_if_t spi_if = {
    .spi = &spi,
    .ss_gpio = SD_SPI_CS_GPIO
};

static sd_card_t sd_card = {
    .type = SD_IF_SPI,
    .spi_if_p = &spi_if
};

size_t sd_get_num() { return 1; }

sd_card_t *sd_get_by_num(size_t num) {
	if (num == 0) return &sd_card;
	else return NULL;
}

