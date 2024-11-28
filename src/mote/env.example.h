#ifndef __ENV_H__
#define __ENV_H__

#define API_KEY ""

#define VPP_DEBUG
#define VPP_LOG_ERR
#define VPP_LOG_WARN
#define VPP_LOG_INFO

#define SPI_SET spi0
#define SPI_SCK_GP 2
#define SPI_MOSI_GP 3
#define SPI_MISO_GP 4
#define SPI_BAUD_RATE 125 * 1000 * 1000 / 4  //31250000 Hz

#define SD_SPI_CS_GP 5

#endif

