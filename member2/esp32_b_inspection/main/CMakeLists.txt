idf_component_register(SRCS "main.c" "tcp_frames.c" "tcp_service.c"
                         "inspection_app.c" "inspection_protocol.c" "vendor/cjson/cJSON.c"
                    PRIV_REQUIRES esp_wifi esp_event esp_netif nvs_flash lwip freertos esp_timer mbedtls
                    INCLUDE_DIRS ".")
target_compile_definitions(${COMPONENT_LIB} PRIVATE CJSON_NESTING_LIMIT=8 CJSON_HIDE_SYMBOLS)
