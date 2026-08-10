/*
 * -----------------------------------------------------------------------------
 *
 * File: sensor_stubs.c
 *
 * Copyright (C) 2026 Benjamin Löliger
 *
 * Authors:
 * - Benjamin Löliger (bloeliger@ethz.ch)
 *
 * -----------------------------------------------------------------------------
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the License); you may
 * not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an AS IS BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * -----------------------------------------------------------------------------
 */

/**
 * @file sensor_stubs.c
 * @brief Weak stub implementations for unused sensor modules.
 *
 * This file provides weak fallback definitions for sensor-related functions that
 * may be referenced by the existing BioGAP firmware structure but are not used
 * in the mmWave firmware variant.
 *
 * The stubs avoid linker errors when unused sensor modules are disabled in the
 * build configuration. If the corresponding real sensor implementation is
 * compiled, it overrides the weak definition provided here.
 */

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