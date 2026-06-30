#include "pico/stdlib.h"
#include "hardware/spi.h"

// Project includes
#include "ads1220.hpp"
#include "include/ads1220_pins.hpp"
#include "include/config.hpp"

#include "bsp/board_api.h"
#include "tusb.h"
#include "usb_descriptors.h"

// To use shorter name when using structs with ADS1220 configuration register constants
using namespace ADS1220_REG;

// Hardware objects
static ADS1220 *adc = nullptr;

// System state and commands flags

volatile SystemState current_state = STATE_IDLE;
volatile bool button_pressed = false;

// Button debouncing
volatile uint64_t last_button_press_time = 0;
const uint DEBOUNCE_DELAY_MS = 200;

// Calibration data
struct CalibrationData
{
    int32_t min_raw1 = 2147483647;
    int32_t max_raw1 = -2147483648;
    int32_t min_raw2 = 2147483647;
    int32_t max_raw2 = -2147483648;
    uint64_t calibration_start_time = 0;
};

uint64_t calibration_start_time = 0;
CalibrationData calibration = {};

// ADS1220 MUX Channel 2 channels selected
bool current_channel_one = true;

// USB Callbacks from tinyUSB
void tud_mount_cb(void) {
    printf("USB device mounted\n");
}

void tud_umount_cb(void) {
    printf("USB device unmounted\n");
}

void tud_suspend_cb(bool remote_wakeup_en) {
    (void)remote_wakeup_en;
    printf("USB device suspended\n");
}

void tud_resume_cb(void) {
    printf("USB device resumed\n");
}

uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id, hid_report_type_t report_type, uint8_t *buffer, uint16_t reqlen) {
    (void)instance;
    (void)report_id;
    (void)report_type;
    (void)buffer;
    (void)reqlen;
    return 0;
}

void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id, hid_report_type_t report_type, uint8_t const *buffer, uint16_t bufsize) {
    (void)instance;
    (void)report_id;
    (void)report_type;
    (void)buffer;
    (void)bufsize;
}

void tud_hid_report_complete_cb(uint8_t instance, uint8_t const *report, uint16_t len) {
    (void)instance;
    (void)report;
    (void)len;
}

void hid_task(void)
{
    static uint32_t start_ms = 0;
    if (tusb_time_millis_api() - start_ms < 10)
    {
        return; // poll every 10ms
    }
    start_ms += 10;
}

void send_joystick_report(int8_t sensor1, int8_t sensor2)
{
    if (!tud_hid_ready())
    {
        return;
    }

    hid_gamepad_report_t report = {
        .x = sensor1, // Left sensor
        .y = sensor2, // Right sensor
        .z = 0,
        .rz = 0,
        .rx = 0,
        .ry = 0,
        .hat = 0,
        .buttons = 0};

    tud_hid_report(REPORT_ID_GAMEPAD, &report, sizeof(report));
}

// Helper function: linear mapping
long map_val(long x, long in_min, long in_max, long out_min, long out_max)
{
    if (in_max == in_min)
        return out_min;
    return (x - in_min) * (out_max - out_min) / (in_max - in_min) + out_min;
}

void button_callback(uint gpio, uint32_t events)
{
    uint64_t now = time_us_64();
    if ((now - last_button_press_time) > (DEBOUNCE_DELAY_MS * 1000))
    {
        last_button_press_time = now;
        button_pressed = true;
    }
}

void setup_button()
{
    gpio_init(MODE_SELECT_PIN);
    gpio_set_dir(MODE_SELECT_PIN, GPIO_IN);
    gpio_pull_up(MODE_SELECT_PIN);
    gpio_set_irq_enabled_with_callback(
        MODE_SELECT_PIN,
        GPIO_IRQ_EDGE_FALL,
        true,
        &button_callback);
}

void configure_sensor(ADS1220 &adc)
{
    uint8_t cfg0 = Config0::pack(ADC_MUX, ADC_GAIN, ADC_PGA_BYPASS);
    uint8_t cfg1 = Config1::pack(ADC_DATA_RATE, ADC_MODE, ADC_CONV_MODE, ADC_TEMP_MODE, ADC_BURNOUT);
    uint8_t cfg2 = Config2::pack(ADC_VREF, ADC_FIR, ADC_PSW, ADC_IDAC);
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

void init_hardware()
{
    printf("Initializing Hardware\n");

    // Initialize USB (COMMENTED OUT FOR TESTING)
    // board_init();
    // tusb_init();
    // printf("USB initialized\n");

    adc = new ADS1220(SPI_ADC, CS_PIN, DRDY_PIN);
    init_sensor(*adc);
    sleep_ms(100);

    configure_sensor(*adc);
    sleep_ms(100);

    adc->printRegisterValues();
    sleep_ms(100);
    printf("ADC initialized\n");
}

void check_server_commands()
{
    if (button_pressed)
    {
        button_pressed = false;
        printf("Button pressed! Starting CALIBRATION!\n");
        current_state = STATE_CALIBRATING;
        return;
    }
}

void handle_idle()
{
    printf("=== IDLE STATE - Press button to calibrate ===\n");
    uint64_t last_check = time_us_64();

    while (current_state == STATE_IDLE)
    {
        tud_task(); // COMMENTED OUT FOR TESTING

        // Non-blocking 100ms timer
        if (time_us_64() - last_check > 100000)
        {
            last_check = time_us_64();
            check_server_commands();
        }
    }
}

void handle_recording()
{
    printf("=== RECORDING STATE ===\n");

    adc->start();
    printf("ADC started\n");

    while (current_state == STATE_RECORDING)
    {
        // Check if button pressed to stop recording
        if (button_pressed)
        {
            button_pressed = false;
            current_state = STATE_IDLE;
            printf("Recording stopped by button\n");
            break;
        }

#ifdef DUAL_CHANNEL_MODE
        if (current_channel_one)
        {
            // Take the AIN0/AIN1 reading
            adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN0_AIN1, ADC_GAIN, ADC_PGA_BYPASS));
        }
        else
        {
            // Switch to AIN2/AIN3 for the next reading
            adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN2_AIN3, ADC_GAIN, ADC_PGA_BYPASS));
        }

        int32_t raw = adc->readDataRaw(true);

        if (raw != 1)
        {
            float voltage = adc->rawToVoltage(raw, VREF_VOLTAGE, ADC_GAIN);
            uint8_t channel = current_channel_one ? 0 : 1;
            printf("Ch%d Raw=%ld, Voltage=%.6f V (%.3f mV)\n", channel, raw, voltage, voltage * 1000.0f);
        }

        current_channel_one = !current_channel_one;
#else
        int32_t raw = adc->readDataRaw(true);

        if (raw != 1)
        {
            float voltage = adc->rawToVoltage(raw, VREF_VOLTAGE, ADC_GAIN);
            printf("Raw=%ld, Voltage=%.6f V (%.3f mV)\n", raw, voltage, voltage * 1000.0f);
        }
#endif

        sleep_ms(1);
    }

    adc->powerDown();
    printf("Recording stopped\n");
}

void handle_calibrating()
{
    printf("=== CALIBRATION STATE: Flex both directions for 10 seconds! ===\n");
    calibration.min_raw1 = 2147483647;
    calibration.max_raw1 = -2147483648;
    calibration.min_raw2 = 2147483647;
    calibration.max_raw2 = -2147483648;
    calibration.calibration_start_time = time_us_64();

    adc->start();
    adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN0_AIN1, ADC_GAIN, ADC_PGA_BYPASS));
    current_channel_one = true;

    // for 10 seconds
    while ((time_us_64() - calibration.calibration_start_time) < 10000000)
    {

        int32_t raw = adc->readDataRaw(true);

        if (current_channel_one)
        {
            // Switch to AIN2/AIN3 for the next reading
            adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN2_AIN3, ADC_GAIN, ADC_PGA_BYPASS));
        }
        else
        {
            // Take the AIN0/AIN1 reading
            adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN0_AIN1, ADC_GAIN, ADC_PGA_BYPASS));
        }

        tud_task(); // COMMENTED OUT FOR TESTING

        if (raw != 1)
        {
            if (current_channel_one)
            {
                if (raw < calibration.min_raw1)
                    calibration.min_raw1 = raw;
                if (raw > calibration.max_raw1)
                    calibration.max_raw1 = raw;
            }
            else
            {
                if (raw < calibration.min_raw2)
                    calibration.min_raw2 = raw;
                if (raw > calibration.max_raw2)
                    calibration.max_raw2 = raw;
            }
        }
        current_channel_one = !current_channel_one;
    }

    printf("Calibration complete! Min1: %ld, Max1: %ld | Min2: %ld, Max2: %ld\n",
           calibration.min_raw1, calibration.max_raw1,
           calibration.min_raw2, calibration.max_raw2);
    current_state = STATE_JOYSTICK;
}

void handle_joystick()
{
    printf("=== JOYSTICK STATE: Dual Axis (Ch1->X, Ch2->Y) ===\n");
    adc->start();
    int32_t current_raw_ch1 = 0;
    int32_t current_raw_ch2 = 0;
    int32_t axis_X = 0;
    int32_t axis_Y = 0;

    while (current_state == STATE_JOYSTICK)
    {
        tud_task(); // COMMENTED OUT FOR TESTING

        // Check if button pressed to stop
        if (button_pressed)
        {
            button_pressed = false;
            current_state = STATE_IDLE;
            printf("Joystick stopped by button\n");
            break;
        }

        // Phase 1: Read CH1 (AIN0/AIN1)
        adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN0_AIN1, ADC_GAIN, ADC_PGA_BYPASS));

        while (!adc->isDataReady(false)) //while data is not ready(conversion going)
        {
            tight_loop_contents();
        }

        current_raw_ch1 = adc->readDataRaw(false);

        // Phase 2: Read CH2 (AIN2/AIN3)
        adc->writeRegister(CONFIG0, Config0::pack(ADS1220_REG::Config0::MUX_AIN2_AIN3, ADC_GAIN, ADC_PGA_BYPASS));

        while (!adc->isDataReady(false))
        {
            tight_loop_contents();
        }

        current_raw_ch2 = adc->readDataRaw(false);

        // Process and send if both reads valid
        if (current_raw_ch1 != 1 && current_raw_ch2 != 1)
        {
            axis_X = map_val(current_raw_ch1, calibration.min_raw1, calibration.max_raw1, -127, 127);
            axis_Y = map_val(current_raw_ch2, calibration.min_raw2, calibration.max_raw2, -127, 127);

            // Clamp values
            if (axis_X > 127)
                axis_X = 127;
            if (axis_X < -127)
                axis_X = -127;
            if (axis_Y > 127)
                axis_Y = 127;
            if (axis_Y < -127)
                axis_Y = -127;

            printf("Ch1(X): %ld | Ch2(Y): %ld\n", axis_X, axis_Y);
            send_joystick_report((int8_t)axis_X, (int8_t)axis_Y);
        }
    }
    adc->powerDown();
    printf("Joystick stopped\n");
}

void handle_transmitting()
{
    printf("=== TRANSMITTING STATE ===\n");
    while (current_state == STATE_TRANSMITTING)
    {
        // usb_task(); // Run constantly!
        //  Remove sleep_ms(100) here too
    }
}

int main()
{
    stdio_init_all();
    sleep_ms(2000); // Wait for serial connection to establish

    printf("\n\n=== PICO STARTED ===\n");

    board_init();
    tusb_rhport_init_t dev_init = {.role = TUSB_ROLE_DEVICE, .speed = TUSB_SPEED_AUTO};
    tusb_init(BOARD_TUD_RHPORT, &dev_init);
    board_init_after_tusb();
    printf("USB initialized\n");

    setup_button();
    sleep_ms(100);
    init_hardware();
    sleep_ms(100);

    current_state = STATE_IDLE;

    while (true)
    {
        tud_task();
        switch (current_state)
        {
        case STATE_IDLE:
            handle_idle();
            break;
        case STATE_RECORDING:
            handle_recording();
            break;
        case STATE_CALIBRATING:
            handle_calibrating();
            break;
        case STATE_JOYSTICK:
            handle_joystick();
            break;
        default:
            current_state = STATE_IDLE;
            break;
        }
    }

    return 0;
}
