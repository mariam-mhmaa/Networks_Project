#include <stdint.h>
#include <string.h>
#include "driver/uart.h"
#include "esp_err.h"
#include "esp_log.h"
#include "esp_system.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "protocol.h"
#include "production.h"

/* Debugger-visible only. No rejection/debug text is sent to UART0. */
static volatile uint32_t rejection_count;
static slip_decoder_t decoder;
static uint8_t encoded[SLIP_MAX_ENCODED];
static uint8_t response[ATR_MAX_DECODED];

static void send_record(const uint8_t *record, size_t length) {
    size_t total=slip_encode(record,length,encoded,sizeof(encoded)), sent=0;
    if (!total) esp_restart();
    while (sent<total) {
        int n=uart_write_bytes(UART_NUM_0,encoded+sent,total-sent);
        if (n<=0) esp_restart();
        sent+=n;
    }
}
static void send_production(uint32_t seq, const char *json, size_t length) {
    response[0]=response[1]=0;
    for (int i=0; i<4; ++i) response[2+i]=(uint8_t)(seq>>(24-i*8));
    response[6]=(uint8_t)(length>>8); response[7]=(uint8_t)length;
    memcpy(response+8,json,length);
    uint16_t crc=atr_crc16(response,length+8);
    response[length+8]=(uint8_t)(crc>>8); response[length+9]=(uint8_t)crc;
    send_record(response,length+10);
}

/* Production JSON on test_id 0; nonzero IDs retain the XOR regression path. */
void app_main(void)
{
    esp_log_level_set("*", ESP_LOG_NONE);
    if (!protocol_self_test()) {
        for (;;) vTaskDelay(pdMS_TO_TICKS(1000)); /* Fail closed, silently. */
    }
    const uart_config_t config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_param_config(UART_NUM_0, &config));
    ESP_ERROR_CHECK(uart_set_pin(UART_NUM_0, UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
    ESP_ERROR_CHECK(uart_driver_install(UART_NUM_0, 2048, 0, 0, NULL, 0));
    production_init(send_production);
    uint8_t bytes[128];
    for (;;) {
        int received = uart_read_bytes(UART_NUM_0, bytes, sizeof(bytes), pdMS_TO_TICKS(20));
        if (received < 0) {
            esp_restart();
        }
        for (int i = 0; i < received; ++i) {
            size_t length = 0;
            int result = slip_feed(&decoder, bytes[i], &length);
            if (result < 0) { ++rejection_count; continue; }
            if (result == 0) continue;
            uint8_t *record = decoder.data;
            if (!atr_validate(record, length)) {
                ++rejection_count;
                continue;
            }
            if (record[0] == 0 && record[1] == 0) {
                uint32_t seq=((uint32_t)record[2]<<24)|((uint32_t)record[3]<<16)|
                             ((uint32_t)record[4]<<8)|record[5];
                production_request(seq,record+8,length-10);
                production_poll();
                continue;
            }
            /* Act only after all lengths, CRC and reserved test_id are checked. */
            for (size_t j = 8; j < length - 2; ++j) record[j] ^= 0xA5;
            uint16_t crc = atr_crc16(record, length - 2);
            record[length - 2] = (uint8_t)(crc >> 8);
            record[length - 1] = (uint8_t)crc;
            send_record(record,length);
        }
        production_poll();
    }
}
