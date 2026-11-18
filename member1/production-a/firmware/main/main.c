#include "serial_service.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "bootloader_random.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
static a_serial serial;
void app_main(void) {
    esp_log_level_set("*", ESP_LOG_NONE);
    if (!protocol_self_test()) return;
    const uart_config_t config = {
        .baud_rate=115200, .data_bits=UART_DATA_8_BITS, .parity=UART_PARITY_DISABLE,
        .stop_bits=UART_STOP_BITS_1, .flow_ctrl=UART_HW_FLOWCTRL_DISABLE, .source_clk=UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    /* Ring exceeds a worst-case whole SLIP frame. The one owner checks free
     * space before enqueue, so UART publication never waits for the wire. */
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 4096, 4096, 0, NULL, 0));
    uint8_t random[16]; char boot[33];
    bootloader_random_enable(); esp_fill_random(random, sizeof(random)); bootloader_random_disable();
    const char hex[]="0123456789abcdef";
    for (unsigned i=0; i<16; ++i) { boot[2*i]=hex[random[i]>>4]; boot[2*i+1]=hex[random[i]&15]; }
    boot[32]=0; a_serial_init(&serial, boot);
    uint8_t bytes[128];
    for (;;) {
        s_protocol_tick(&serial.protocol, (uint64_t)(esp_timer_get_time()/1000));
        int n=uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), 0);
        if (n>0) a_serial_receive(&serial, bytes, (size_t)n);
        const uint8_t *out; size_t length, available=0;
        if (a_serial_front(&serial, &out, &length) &&
            uart_get_tx_buffer_free_size(UART_NUM_0, &available)==ESP_OK && available>=length) {
            int written=uart_write_bytes(UART_NUM_0, out, length);
            if (written==(int)length) a_serial_sent(&serial);
            else { /* Fail closed on an unexpected driver invariant failure. */
                for (;;) vTaskDelay(pdMS_TO_TICKS(1000));
            }
        }
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}
