set(SHARED "${CMAKE_CURRENT_LIST_DIR}/../../../../shared/station")
idf_component_register(SRCS "main.c" "protocol.c" "serial_service.c"
    "${SHARED}/station_app.c" "${SHARED}/station_protocol.c" "${SHARED}/vendor/cjson/cJSON.c"
    INCLUDE_DIRS "." "${SHARED}"
    REQUIRES esp_driver_uart esp_timer esp_hw_support bootloader_support mbedtls)
target_compile_definitions(${COMPONENT_LIB} PRIVATE CJSON_NESTING_LIMIT=8 CJSON_HIDE_SYMBOLS)
