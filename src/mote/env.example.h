#ifndef __ENV_H__
#define __ENV_H__

/**
 * @file env.example.h
 *
 * This is an example file of the environment file. This file should be duplicated as env.h
 * before the first build. Anything stored in the env.h file is local configuration, and git isn't
 * concerned with any changes to the file.
 *
 * If any new vars are defined in env.h, their definition should also be included in the
 * env.example.h file (with the actual values left empty, if needed), to keep the template updated.
 */

#define API_KEY ""

//Comment these lines out to disable them
#define VPP_DEBUG
#define VPP_LOG_ERR
#define VPP_LOG_WARN
#define VPP_LOG_INFO

#define SPI_SET spi0
#define SPI_SCK_GPIO 2
#define SPI_MOSI_GPIO 3
#define SPI_MISO_GPIO 4
#define SPI_BAUD_RATE 125 * 1000 * 1000 / 4  //31250000 Hz

#define SD_SPI_CS_GPIO 5

#endif

