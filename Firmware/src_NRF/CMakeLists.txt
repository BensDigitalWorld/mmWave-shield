# Copyright (c) 2024 ETH Zurich
# SPDX-License-Identifier: Apache-2.0

cmake_minimum_required(VERSION 3.20.0)

# Enable shields
set(SHIELD "mmWaveShield")

set(CONF_FILE prj.conf)
set(OVERLAY_CONFIG "child_image/hci_ipc.conf")


# Setup SENSEI SDK
set(SENSEI_SDK_ROOT $ENV{SENSEI_SDK_ROOT})
if(NOT SENSEI_SDK_ROOT)
    message(FATAL_ERROR "SENSEI_SDK_ROOT is not defined")
endif()

list(APPEND EXTRA_ZEPHYR_MODULES
    ${SENSEI_SDK_ROOT}/NRF
)

# Configure the project
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(mmWave_stream)


target_sources(app PRIVATE
    # Entry point
    main.c

    # Core
    core/sync_streaming.c
    core/i2c_helpers.c
    core/board_sync.c

    # BSP
    bsp/pwr_bsp.c
    bsp/battery/battery.c
    bsp/system_status/system_status.c


)
#depending on config includes: (Benis Changes)

# AFE (Analog Front-End - ADS1298)
if(CONFIG_SENSOR_EEG OR CONFIG_SENSOR_EMG)
    target_sources(app PRIVATE
    bsp/power/power.c
    afe/ads_appl.c
    afe/ads_spi_hw.c
    afe/ads_spi_comm.c
    afe/ads_spi_config.c
    afe/ads_spi_data.c
    )
endif()

# Sensors - IMU
if(CONFIG_SENSOR_IMU)
    target_sources(app PRIVATE
    sensors/imu/imu_appl.c
    sensors/imu/lis2duxs12_sensor.c
    sensors/imu/driver/lis2duxs12_reg.c
    )
endif()

# Sensors - Microphone
if(CONFIG_SENSOR_MIC)
    target_sources(app PRIVATE
        sensors/mic/mic_appl.c
    )
endif()

# Sensors - EEG
if(CONFIG_SENSOR_EEG)
    target_sources(app PRIVATE
        sensors/eeg/eeg_appl.c
    )
endif()

# Sensors - EMG
if(CONFIG_SENSOR_EMG)
    target_sources(app PRIVATE
        sensors/emg/emg_appl.c
    )
endif()

# Sensors - PPG
if(CONFIG_SENSOR_PPG)
    target_sources(app PRIVATE
        sensors/ppg/ppg_appl.c
    )
endif()

# Sensors - mmWave
if(CONFIG_SENSOR_MMWAVE)
    target_sources(app PRIVATE
    sensors/mmWave/mmWave_appl.c
    sensors/mmWave/driver/xensiv_bgt60trxx.c
    )
endif()

target_sources(app PRIVATE
    
    # Always include, only weak functions (Benis Change)
    stubs/sensor_stubs.c

    # BLE
    ble/ble_appl.c
    ble/bluetooth.c
    )


target_include_directories(app PRIVATE
    .
)


