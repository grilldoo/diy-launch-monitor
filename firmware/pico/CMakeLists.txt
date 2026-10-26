# Pico firmware build. Requires the Pico SDK:
#   export PICO_SDK_PATH=/path/to/pico-sdk
#   cmake -B build -DPICO_BOARD=pico2 && cmake --build build
# then copy build/lm_timing_controller.uf2 to the Pico in BOOTSEL mode.
cmake_minimum_required(VERSION 3.13)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(lm_timing_controller C CXX ASM)
set(CMAKE_C_STANDARD 11)
pico_sdk_init()

add_executable(lm_timing_controller src/main.c src/lm_timing.c)
target_link_libraries(lm_timing_controller pico_stdlib hardware_gpio hardware_sync)
pico_enable_stdio_usb(lm_timing_controller 1)
pico_enable_stdio_uart(lm_timing_controller 0)
pico_add_extra_outputs(lm_timing_controller)
