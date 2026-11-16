idf_component_register(SRCS "main.c" "protocol.c" "production.c" "history.c" INCLUDE_DIRS "." REQUIRES esp_system esp_driver_uart esp_timer esp_hw_support bootloader_support)
