#ifndef CONFIGURATION_H
#define CONFIGURATION_H

#include <stdint.h>

#define DEBUG_MODE
//#define PRODUCTION_MODE

// ADC Configuration
// SPI Settings
#define ADC_SPI_FREQ 1000000
#define ADC_SPI_MODE 1 
#define ADC_BITS_TRANSFER 8

// Voltage reference
#define VREF_VOLTAGE (3.3f)

// CONFIG0
#define ADC_MUX ADS1220_REG::Config0::MUX_AIN0_AIN1
#define ADC_GAIN ADS1220_REG::Config0::GAIN_64
#define ADC_PGA_BYPASS false

// CONFIG1
#define ADC_DATA_RATE  ADS1220_REG::Config1::DR_330SPS
#define ADC_MODE       ADS1220_REG::Config1::MODE_NORMAL
#define ADC_CONV_MODE  true   // Continuous conversion
#define ADC_TEMP_MODE  false  // Temperature sensor off
#define ADC_BURNOUT    false  // Burn-out current off

// CONFIG2
#define ADC_VREF       ADS1220_REG::Config2::VREF_REFP0_REFN0
#define ADC_FIR        ADS1220_REG::Config2::FIR_NONE
#define ADC_PSW        false  // PSW open
#define ADC_IDAC       ADS1220_REG::Config2::IDAC_OFF

#define BUFFER_SIZE 4096
#define CHUNK_SIZE 512
#define BASE_FILENAME "brauciens"
#define MAX_FILENAME_LEN 32


// TODO
enum OperationMode {
    MODE_SENSOR = 0,
    MODE_SLAVE = 1
};

#pragma pack(push, 1)
struct ADCRecord {
    uint32_t timestamp_us;
    int32_t raw_value;
};

#pragma pack(pop)

extern volatile bool buffer_ready;
extern uint64_t start_time;
extern char filename[MAX_FILENAME_LEN];

#endif