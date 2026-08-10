# -----------------------------------------------------------------------------
#
# File: measure_biogap_single_session.py
#
# Last edited: 14.07.2026
#
# Copyright (C) 2026 Benjamin Löliger
#
# Authors:
# - Benjamin Löliger (bloeliger@ethz.ch)
#
# -----------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# -----------------------------------------------------------------------------

import numpy as np
import os
import time
from datetime import datetime

from acquisition.bgt_com_class import BGT60SensorThreaded


# ===========================================================================
# Make Folder
# ===========================================================================

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
output_folder_name = f"radar_and_finapress_session_{timestamp}"

output_folder = os.path.join("data", "biogap_measurments", output_folder_name)

if not os.path.exists(output_folder):
    os.makedirs(output_folder)
    print(f"📁 Ordner erstellt: {output_folder}")

# ===========================================================================
# TEST CONFIGS
# ===========================================================================

SERIAL_PORT = 'COM4'
RECORD_TIME_S = 30
NUM_RX_ANTENNAS = 1
if_gain_dB = 33
TX_POWER = 31
FPS = 100
CHIRPS = 32
SAMPLES = 8

# ===========================================================================
# HELPER
# ===========================================================================

def print_progress(current, total, width=30):
    progress = current / total
    filled = int(width * progress)

    bar = "#" * filled + "-" * (width - filled)
    percent = progress * 100

    print(f"\r[{bar}] {current}/{total} Frames ({percent:5.1f}%)", end="", flush=True)

# ===========================================================================
# MAIN
# ===========================================================================


if __name__ == '__main__':

    # PRE-ALLOCATION for more speeeed
    num_frames = int(FPS * RECORD_TIME_S)

    data_buffer = np.zeros((num_frames, NUM_RX_ANTENNAS, CHIRPS, SAMPLES), dtype=np.float32)
    time_stamps = np.zeros(num_frames , dtype=np.uint32)
    sensor = BGT60SensorThreaded(
                port= SERIAL_PORT,
                NUM_RX_ANTENNAS=NUM_RX_ANTENNAS,
                NUM_CHIRPS=CHIRPS,
                NUM_SAMPLES=SAMPLES)
    
    valid_frames = 0
    timeouts = 0


    print(f"Recording of {num_frames} frames started...")

    sensor.start(gain_db=if_gain_dB,tx_power=TX_POWER, fps=FPS)

    # Data collection
    start_t = time.time()
    try:
        while valid_frames < num_frames:
            time_stamp, sync_state, frame_content = sensor.get_next_frame() 
            if frame_content is None:
                dropped_frames += 1
                print("Kein gültiger Frame erhalten.")
                continue
            # frame_contents[0] the data of all RX-Antennas
            data_buffer[valid_frames] = frame_content
            time_stamps[valid_frames] = time_stamp
            valid_frames += 1
            print_progress(valid_frames,num_frames)

        print()

    except KeyboardInterrupt:
        pass
    
    finally:
        stop_t = time.time()

        sensor.stop()
        sensor.close()

        # Saving
        np.save(os.path.join(output_folder, "data.npy"), data_buffer)
        np.save(os.path.join(output_folder, "time_stamps.npy"), time_stamps)

        print(f"💾 Files Saved")
        print(f"Took time: {stop_t - start_t:.2f}s (Should be: {RECORD_TIME_S}s)")
