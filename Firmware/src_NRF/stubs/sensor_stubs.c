#include "sensors/eeg/eeg_appl.h"
#include "sensors/imu/imu_appl.h"
#include "sensors/mic/mic_appl.h"
#include "sensors/emg/emg_appl.h"
#include "afe/ads_appl.h"
#include "afe/ads_spi.h"
#include <zephyr/toolchain.h>
#include <errno.h>
#include "bsp/power/power.h"
//Benis Changes

int __weak power_init(void) {return 0;}


void __weak ads_set_function(ads_function_t f) {}
ads_function_t ads_get_function(void) { return ADS_STILL; }
int __weak ads_dr_init() {return -1; }
void __weak init_spi() {}

int __weak eeg_start_streaming(void) {return -EINVAL;}
int __weak eeg_stop_streaming(void)  {return -EINVAL;}

int __weak emg_start_streaming(void) {return -EINVAL;}
int __weak emg_stop_streaming(void)  {return -EINVAL;}

int  __weak imu_init(void) {return -1;}
int __weak imu_start_streaming(void) {return -EINVAL;}
int __weak imu_stop_streaming(void)  {return -EINVAL;}

int  __weak mic_init(void) {return -1;}
int __weak mic_start_streaming(void) {return -EINVAL;}
int __weak mic_stop_streaming(void)  {return -EINVAL;}