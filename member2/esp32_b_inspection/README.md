# ESP32 B Inspection Station

This project is the inspection station for MCT431 Milestone 1. The current
firmware connects to Wi-Fi and reports its IPv4 address over the USB serial
monitor. Inspection jobs and TCP communication will be added in later steps.

## Configure the first Wi-Fi test

1. Turn on the iPhone Personal Hotspot. Enable **Maximize Compatibility** if
   available, so the hotspot uses 2.4 GHz and WPA2.
2. Connect the PC to that hotspot.
3. Open this folder in VS Code and run **ESP-IDF: SDK Configuration Editor**.
4. Under **Inspection Station Wi-Fi**, enter the hotspot name and password,
   then save. Do not put the password in source code or a shared message.
5. Build the project, flash the ESP32 through COM3 using UART, and open the
   serial monitor. Look for `Wi-Fi connected; IPv4 address: ...`.

The local `sdkconfig` and `build/` files are ignored by Git because they can
contain the hotspot password. Firmware binaries also embed the configured
network credentials, so do not share them as public artifacts.

The Wi-Fi connection proves that the ESP32 obtained an address. It does not
yet prove that the PC can reach it through TCP; that is the next milestone.

## First hotspot test

On 2026-11-17, ESP32 B joined the iPhone hotspot using WPA2 and received
`172.20.10.3`. The PC was connected to the same SSID. This address is assigned
by the hotspot and may change, so check the serial log again before the TCP
test.
