# Firmware Code-Level Changes

This document contains a code-level diff of the modified existing firmware files.

Newly added files are excluded from this comparison because they are documented separately in the firmware README.

```diff
diff --git a/Firmware/src_NRF/CMakeLists.txt b/Firmware/src_NRF/CMakeLists.txt
index b46a8d4..6f33bbf 100644
--- a/Firmware/src_NRF/CMakeLists.txt
+++ b/Firmware/src_NRF/CMakeLists.txt
@@ -4,7 +4,7 @@
 cmake_minimum_required(VERSION 3.20.0)
 
 # Enable shields
-set(SHIELD "SENSEI_ExGShield SENSEI_PPGShield")
+set(SHIELD "mmWaveShield")
 
 set(CONF_FILE prj.conf)
 set(OVERLAY_CONFIG "child_image/hci_ipc.conf")
@@ -22,7 +22,7 @@ list(APPEND EXTRA_ZEPHYR_MODULES
 
 # Configure the project
 find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
-project(exg_stream)
+project(mmWave_stream)
 
 
 target_sources(app PRIVATE
@@ -37,37 +37,82 @@ target_sources(app PRIVATE
     # BSP
     bsp/pwr_bsp.c
     bsp/battery/battery.c
-    bsp/power/power.c
     bsp/system_status/system_status.c
 
-    # AFE (Analog Front-End - ADS1298)
+
+)
+#depending on config includes: (Benis Changes)
+
+# AFE (Analog Front-End - ADS1298)
+if(CONFIG_SENSOR_EEG OR CONFIG_SENSOR_EMG)
+    target_sources(app PRIVATE
+    bsp/power/power.c
     afe/ads_appl.c
     afe/ads_spi_hw.c
     afe/ads_spi_comm.c
     afe/ads_spi_config.c
     afe/ads_spi_data.c
+    )
+endif()
 
-    # Sensors - IMU
+# Sensors - IMU
+if(CONFIG_SENSOR_IMU)
+    target_sources(app PRIVATE
     sensors/imu/imu_appl.c
     sensors/imu/lis2duxs12_sensor.c
     sensors/imu/driver/lis2duxs12_reg.c
+    )
+endif()
+
+# Sensors - Microphone
+if(CONFIG_SENSOR_MIC)
+    target_sources(app PRIVATE
+        sensors/mic/mic_appl.c
+    )
+endif()
+
+# Sensors - EEG
+if(CONFIG_SENSOR_EEG)
+    target_sources(app PRIVATE
+        sensors/eeg/eeg_appl.c
+    )
+endif()
 
-    # Sensors - Microphone
-    sensors/mic/mic_appl.c
+# Sensors - EMG
+if(CONFIG_SENSOR_EMG)
+    target_sources(app PRIVATE
+        sensors/emg/emg_appl.c
+    )
+endif()
 
-    # Sensors - PPG
-    sensors/ppg/ppg_appl.c
+# Sensors - PPG
+if(CONFIG_SENSOR_PPG)
+    target_sources(app PRIVATE
+        sensors/ppg/ppg_appl.c
+    )
+endif()
 
-    # Sensors - EEG
-    sensors/eeg/eeg_appl.c
+# Sensors - mmWave
+if(CONFIG_SENSOR_MMWAVE)
+    target_sources(app PRIVATE
+    sensors/mmWave/mmWave_appl.c
+    sensors/mmWave/driver/xensiv_bgt60trxx.c
+    )
+endif()
 
-    # Sensors - EMG
-    sensors/emg/emg_appl.c
+target_sources(app PRIVATE
+    
+    # Always include, only weak functions (Benis Change)
+    stubs/sensor_stubs.c
 
     # BLE
     ble/ble_appl.c
     ble/bluetooth.c
-)
+    )
+
+
 target_include_directories(app PRIVATE
     .
 )
+
+
diff --git a/Firmware/src_NRF/Kconfig b/Firmware/src_NRF/Kconfig
index e8dfcaa..e2f79b2 100644
--- a/Firmware/src_NRF/Kconfig
+++ b/Firmware/src_NRF/Kconfig
@@ -60,6 +60,35 @@ config SENSOR_EEG
 	  Enable support for EEG sensor. This will include the necessary drivers,
 	  state machine states, and data processing for EEG data acquisition.
 
+#my changes below, gotta adjust comments (Benis Changes)
+config SENSOR_PPG
+	bool "PPG sensor"
+	default n
+	help
+	  Enable support for EEG sensor. This will include the necessary drivers,
+	  state machine states, and data processing for EEG data acquisition.
+
+config SENSOR_IMU
+	bool "IMU sensor"
+	default n
+	help
+	  Enable support for EEG sensor. This will include the necessary drivers,
+	  state machine states, and data processing for EEG data acquisition.
+
+config SENSOR_MIC
+	bool "MIC sensor"
+	default n
+	help
+	  Enable support for EEG sensor. This will include the necessary drivers,
+	  state machine states, and data processing for EEG data acquisition.
+
+config SENSOR_MMWAVE
+	bool "mmWave sensor"
+	default n
+	help
+	  Enable support for EEG sensor. This will include the necessary drivers,
+	  state machine states, and data processing for EEG data acquisition.
+
 menu "State Machine Configuration"
 
 config STATE_MACHINE_USE_CPU_IDLE
diff --git a/Firmware/src_NRF/ble/ble_appl.c b/Firmware/src_NRF/ble/ble_appl.c
index f2ef477..aa17add 100644
--- a/Firmware/src_NRF/ble/ble_appl.c
+++ b/Firmware/src_NRF/ble/ble_appl.c
@@ -33,9 +33,11 @@
 #include "core/common.h"
 #include "core/sync_streaming.h"
 #include "sensors/eeg/eeg_appl.h"
+#include "sensors/emg/emg_appl.h"
 #include "sensors/imu/imu_appl.h"
 #include "sensors/imu/lis2duxs12_sensor.h"
 #include "sensors/mic/mic_appl.h"
+#include "sensors/mmWave/mmWave_appl.h"
 
 #include <zephyr/logging/log.h>
 #include <zephyr/logging/log_ctrl.h>
@@ -228,6 +230,7 @@ static void handle_ble_command(uint8_t cmd) {
     emg_stop_streaming();
     ble_print_packet_stats(); /* Print BLE packet stats */
     break;
+
   case START_MIC_STREAMING:
     LOG_INF("Ping START_MIC_STREAMING");
     mic_start_streaming();
@@ -245,6 +248,7 @@ static void handle_ble_command(uint8_t cmd) {
     mic_start_streaming();
     eeg_start_streaming();
     break;
+
   case STOP_EEG_MIC_STREAMING:
     LOG_DBG("Ping STOP_EEG_MIC_STREAMING");
     mic_stop_streaming();
@@ -252,6 +256,7 @@ static void handle_ble_command(uint8_t cmd) {
     ble_print_packet_stats(); /* Print BLE packet stats */
     sync_reset();             /* Clean up sync state */
     break;
+
   case START_STREAMING_ALL:
     LOG_DBG("Ping START_STREAMING_ALL");
     ble_reset_packet_counters(); /* Reset packet counters for new session */
@@ -260,6 +265,7 @@ static void handle_ble_command(uint8_t cmd) {
     eeg_start_streaming();
     imu_start_streaming();
     break;
+
   case STOP_STREAMING_ALL:
     LOG_DBG("Ping STOP_STREAMING_ALL");
     mic_stop_streaming();
@@ -268,14 +274,56 @@ static void handle_ble_command(uint8_t cmd) {
     ble_print_packet_stats(); /* Print BLE packet stats */
     sync_reset();             /* Clean up sync state */
     break;
+
   case START_IMU_STREAMING:
     LOG_DBG("Ping START_IMU_STREAMING");
     imu_start_streaming();
     break;
+    
   case STOP_IMU_STREAMING:
     LOG_DBG("Ping STOP_IMU_STREAMING");
     imu_stop_streaming();
     break;
+  
+  case START_MMWAVE_STREAMING:
+    LOG_DBG("Ping START_MMWAVE_STREAMING");
+    mmWave_start_streaming();
+    break;
+    
+  case STOP_MMWAVE_STREAMING:
+    LOG_DBG("Ping STOP_MMWAVE_STREAMING");
+    mmWave_stop_streaming();
+    break;
+
+  case CONFIGURE_MMWAVE:
+    LOG_DBG("Ping CONFIGURE_MMWAVE");
+    mmWave_configure();
+    break;
+
+  case TURN_OFF_MMWAVE:
+    LOG_DBG("Ping TURN_OFF_MMWAVE");
+    mmWave_power_off();
+    break;  
+    
+  case TURN_ON_MMWAVE:
+    LOG_DBG("Ping TURN_ON_MMWAVE");
+    mmWave_power_on();
+    break;
+  
+  case CHANGE_IFGAIN_MMWAVE:
+    LOG_DBG("Ping CONFIG_IFGAIN_MMWAVE");
+    mmWave_set_ifGain(ble_data_available.data[1]);
+    break;
+
+  case CHANGE_TXPOWER_MMWAVE:
+    LOG_DBG("Ping CONFIG_TXPOWER_MMWAVE");
+    mmWave_set_txPower(ble_data_available.data[1]);
+    break;
+
+  case CHANGE_FPS_MMWAVE:
+    LOG_DBG("Ping CONFIG_FPS_MMWAVE");
+    mmWave_set_fps(ble_data_available.data[1]);
+    break;
   }
 }
 
diff --git a/Firmware/src_NRF/ble/ble_commands.h b/Firmware/src_NRF/ble/ble_commands.h
index ee34519..27d7904 100644
--- a/Firmware/src_NRF/ble/ble_commands.h
+++ b/Firmware/src_NRF/ble/ble_commands.h
@@ -67,5 +67,13 @@
 #define SET_DEVICE_SETTINGS 12
 #define START_EMG_STREAMING 37
 #define STOP_EMG_STREAMING 38
+#define START_MMWAVE_STREAMING 39
+#define STOP_MMWAVE_STREAMING 40
+#define CONFIGURE_MMWAVE 41
+#define TURN_OFF_MMWAVE 42
+#define TURN_ON_MMWAVE 43
+#define CHANGE_IFGAIN_MMWAVE 44
+#define CHANGE_TXPOWER_MMWAVE 45
+#define CHANGE_FPS_MMWAVE 46
 
 #endif // BLE_COMMANDS_H
diff --git a/Firmware/src_NRF/bsp/battery/battery.c b/Firmware/src_NRF/bsp/battery/battery.c
index 9458a9b..78d5c78 100644
--- a/Firmware/src_NRF/bsp/battery/battery.c
+++ b/Firmware/src_NRF/bsp/battery/battery.c
@@ -41,7 +41,7 @@ static void battery_update_thread(void *arg1, void *arg2, void *arg3)
         k_sleep(K_MSEC(5000));
         // Only update if not currently reading ADS data to avoid I2C/SPI interference if shared
         if (ads_get_function() != ADS_READ) {
-            battery_update_status();
+            //battery_update_status();
         }
     }
 }
diff --git a/Firmware/src_NRF/bsp/power/power.c b/Firmware/src_NRF/bsp/power/power.c
index 05a8794..96d3aab 100644
--- a/Firmware/src_NRF/bsp/power/power.c
+++ b/Firmware/src_NRF/bsp/power/power.c
@@ -22,10 +22,14 @@
 
 LOG_MODULE_REGISTER(power_bsp, LOG_LEVEL_INF);
 
+#if defined(CONFIG_SENSOR_EEG) || defined(CONFIG_SENSOR_EMG)
 #define GPIO_NODE_ads1298_pwr DT_NODELABEL(gpio_ads1298_pwr)
 static const struct gpio_dt_spec gpio_p0_31_ads1298_pwr = GPIO_DT_SPEC_GET(GPIO_NODE_ads1298_pwr, gpios);
+#endif
 
 int power_init(void) {
+    #if defined(CONFIG_SENSOR_EEG) || defined(CONFIG_SENSOR_EMG)
+
     // Enable ADS1298 power GPIO
     if (!device_is_ready(gpio_p0_31_ads1298_pwr.port)) {
         LOG_ERR("ADS1298 power GPIO port not ready");
@@ -36,11 +40,13 @@ int power_init(void) {
         LOG_ERR("ADS pwr GPIO init error");
         return -1;
     }
-    
+    #endif
     LOG_INF("Power BSP initialized");
     return 0;
 }
 
+#if defined(CONFIG_SENSOR_EEG) || defined(CONFIG_SENSOR_EMG)
+
 int power_ads_off(void) {
     struct max77654_conf *pmic_conf = &pmic_h.conf;
 
@@ -120,6 +126,7 @@ int power_ads_on_bipolar(void) {
 
     return 0;
 }
+#endif
 
 int power_exg_on(void) {
 #if defined(CONFIG_SENSOR_EEG) && !defined(CONFIG_SENSOR_EMG)
diff --git a/Firmware/src_NRF/bsp/pwr_bsp.c b/Firmware/src_NRF/bsp/pwr_bsp.c
index 7118e0c..b1fca36 100644
--- a/Firmware/src_NRF/bsp/pwr_bsp.c
+++ b/Firmware/src_NRF/bsp/pwr_bsp.c
@@ -142,7 +142,7 @@ int pwr_bsp_start() {
   pmic_conf->sbb_conf[2].peak_current = MAX77654_SBB_PEAK_CURRENT_1A;
   pmic_conf->sbb_conf[2].active_discharge = false;
   pmic_conf->sbb_conf[2].en = MAX77654_REG_ON;
-  pmic_conf->sbb_conf[2].output_voltage_mV = 1200;
+  pmic_conf->sbb_conf[2].output_voltage_mV = 3300;
 
   pmic_conf->ldo_conf[0].mode = MAX77654_LDO_MODE_LDO;
   pmic_conf->ldo_conf[0].active_discharge = false;
diff --git a/Firmware/src_NRF/main.c b/Firmware/src_NRF/main.c
index 3d0f0d1..52b4403 100644
--- a/Firmware/src_NRF/main.c
+++ b/Firmware/src_NRF/main.c
@@ -53,6 +53,7 @@
 #include "sensors/imu/imu_appl.h"
 #include "sensors/mic/mic_appl.h"
 #include "sensors/eeg/eeg_appl.h"
+#include "sensors/mmWave/mmWave_appl.h"
 
 // Inter-board hardware synchronization
 #include "core/board_sync.h"
@@ -71,6 +72,7 @@ struct uart_data_t {
 };
 
 void z_fatal_error(unsigned int reason, const z_arch_esf_t *esf) {
+  volatile unsigned int r = reason;
   LOG_INF("Fatal error occurred: %d", reason);
   while (1) {
     // Halt here for debugging
@@ -105,6 +107,7 @@ int main(void) {
 
   LOG_INF("Enabling charge...");
   pwr_charge_enable();
+
   LOG_INF("Initializing ADS...");
   ret = ads_dr_init();
 
@@ -155,6 +158,17 @@ int main(void) {
   }
 #endif
 
+
+  // Initialize mmWave subsystem
+  LOG_INF("Initializing mmWave subsystem...");
+  if (mmWave_HW_init() != 0) {
+    LOG_WRN("mmWave initialization failed - mmWave streaming disabled");
+  } else {
+    LOG_INF("mmWave subsystem initialized");
+  }
+
+
+
   // Initialize inter-board synchronization
   LOG_INF("Initializing board sync...");
   if (board_sync_init() != 0) {
diff --git a/Firmware/src_NRF/nrf5340_senseiv1_cpuapp.overlay b/Firmware/src_NRF/nrf5340_senseiv1_cpuapp.overlay
index dfc5e6d..c8d1e1c 100644
--- a/Firmware/src_NRF/nrf5340_senseiv1_cpuapp.overlay
+++ b/Firmware/src_NRF/nrf5340_senseiv1_cpuapp.overlay
@@ -16,7 +16,7 @@
 &clock {
     hfclkaudio-frequency = <12288000>;
 };
-
+/*
 &pinctrl {
     pdm_default: pdm_default {
         group1 {
@@ -32,7 +32,7 @@ dmic_dev: &pdm0 {
     pinctrl-names = "default";
     clock-source = "ACLK";
 };
-
+*/
 // /*
 //  * Inter-board synchronization GPIO
 //  *
diff --git a/Firmware/src_NRF/prj.conf b/Firmware/src_NRF/prj.conf
index 34923b4..ed9d4c1 100755
--- a/Firmware/src_NRF/prj.conf
+++ b/Firmware/src_NRF/prj.conf
@@ -39,10 +39,12 @@ CONFIG_NFCT_PINS_AS_GPIOS=y
 
 # SPI Configuration
 CONFIG_NRFX_SPIM2=y
-# CONFIG_SPI=y
+CONFIG_SPI=y
 
 # Sensor Support
 CONFIG_SENSOR=y
+CONFIG_SENSOR_MMWAVE=y
+CONFIG_SENSOR_IMU=y
 
 #===============================================================================
 # Debug and Logging
```