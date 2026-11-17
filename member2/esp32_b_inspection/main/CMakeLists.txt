idf_component_register(SRCS "main.c" "tcp_frames.c" "tcp_service.c"
                    PRIV_REQUIRES esp_wifi esp_event esp_netif nvs_flash lwip freertos
                    INCLUDE_DIRS ".")
