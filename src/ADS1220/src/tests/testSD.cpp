#include "include/ads1220_pins.hpp"
#include "include/config.hpp"

#include "pico/stdlib.h"
#include "hardware/spi.h"
#include <stdio.h>
#include <string.h>

// FatFS includes
#include "ff.h"
#include "hw_config.h"
#include "sd_card.h"

int main()
{
    stdio_init_all();
    sleep_ms(2000);  // Wait for USB serial
    
   // printf("\n=== SD Card Test ===\n");
    
    // Initialize LED for status
    gpio_init(25);
    gpio_set_dir(25, GPIO_OUT);
    gpio_put(25, 0);
    
    // Initialize SD card
    //printf("Initializing SD card...\n");
    sd_init_driver();
    sleep_ms(500);
    
    // Mount filesystem
    FATFS fs;
    FRESULT fr = f_mount(&fs, "0:", 1);
    
    if (fr != FR_OK)
    {
        //printf("SD Mount FAILED: %d\n", fr);
        //printf("Error codes: FR_OK=0, FR_DISK_ERR=1, FR_NOT_READY=3, FR_NO_FILESYSTEM=13\n");
        
        // Fast blink = error
        while (true)
        {
            gpio_put(25, 1);
            sleep_ms(100);
            gpio_put(25, 0);
            sleep_ms(100);
        }
    }
    
    //printf("SD Card mounted successfully!\n");
    gpio_put(25, 1);  // LED ON = success
    sleep_ms(5000);
    
    // Create and write test file
    //printf("\nCreating test file: test.txt\n");
    
    FIL file;
    fr = f_open(&file, "test.txt", FA_WRITE | FA_CREATE_ALWAYS);
    
    if (fr != FR_OK)
    {
        //printf("❌ File open FAILED: %d\n", fr);
        while (true)
        {
            gpio_put(25, 1);
            sleep_ms(200);
            gpio_put(25, 0);
            sleep_ms(200);
        }
    }
    
    //printf("File opened\n");

    sleep_ms(100);
    
    // Write test data
    const char *test_message = "Hello from Raspberry Pi Pico!\n"
                               "SD Card is working correctly.\n"
                               "Timestamp: ";
    
    UINT bytes_written;
    
    // Write text
    fr = f_write(&file, test_message, strlen(test_message), &bytes_written);
    if (fr != FR_OK || bytes_written != strlen(test_message))
    {
       // printf("❌ Write FAILED: %d\n", fr);
        f_close(&file);
        while (true) { tight_loop_contents(); }
    }
    
    // Write timestamp
    char time_buf[32];
    uint64_t time_us = time_us_64();
    snprintf(time_buf, sizeof(time_buf), "%llu us\n", time_us);
    fr = f_write(&file, time_buf, strlen(time_buf), &bytes_written);
    
    // Write some numbers
    for (int i = 0; i < 10; i++)
    {
        char line[64];
        snprintf(line, sizeof(line), "Line %d: Counter value = %d\n", i+1, i*100);
        f_write(&file, line, strlen(line), &bytes_written);
    }
    
    printf("Data written: %u bytes\n", bytes_written);
    
    // Important: Sync and close
    f_sync(&file);
    f_close(&file);
    
    printf("File closed and synced\n");
    
    // // Now try to read it back to verify
    // printf("\nReading back test.txt to verify...\n");
    
    // fr = f_open(&file, "test.txt", FA_READ);
    // if (fr == FR_OK)
    // {
    //     char read_buffer[256];
    //     UINT bytes_read;
        
    //     printf("--- File Contents ---\n");
    //     while (f_read(&file, read_buffer, sizeof(read_buffer)-1, &bytes_read) == FR_OK && bytes_read > 0)
    //     {
    //         read_buffer[bytes_read] = '\0';  // Null terminate
    //         printf("%s", read_buffer);
    //     }
    //     printf("--- End of File ---\n");
        
    //     f_close(&file);
    // }
    
    printf("\nTEST COMPLETE!\n");
    printf("Remove SD card and check 'test.txt' on your PC\n");
    
    // Success pattern: 3 blinks then solid
    for (int i = 0; i < 3; i++)
    {
        gpio_put(25, 0);
        sleep_ms(300);
        gpio_put(25, 1);
        sleep_ms(300);
    }
    
    // Keep LED on
    gpio_put(25, 1);
    
    while (true)
    {
        sleep_ms(1000);
    }
    
    return 0;
}
