# -----------------------------------------------------------------------------
#
# File: record_fps_sweep_biogap.py
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
import random
from datetime import datetime

from acquisition.bgt_com_class import BGT60SensorThreaded


# ===========================================================================
# CONFIG
# ===========================================================================

PORT = "COM4"

NUM_RX_ANTENNAS = 1
CHIRPS = 32
SAMPLES = 8

IF_GAIN_DB = 18
TX_POWER = 31

FPS_LIST = [25, 50, 100, 150, 200]
RANDOMIZE_ORDER = True

RECORD_TIME_S = 10
REPETITIONS = 3

SETTLING_TIME_S = 2

# ===========================================================================
# Make Folder
# ===========================================================================


timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")

output_folder_name = f"radar_fps_sweep_{timestamp}"
output_folder = os.path.join("data", "biogap_measurments", output_folder_name)

os.makedirs(output_folder, exist_ok=True)

print(f"Ordner erstellt: {output_folder}")


# ===========================================================================
# HELPER
# ===========================================================================

def print_progress(current, total, width=30):
    progress = current / total
    filled = int(width * progress)
    bar = "#" * filled + "-" * (width - filled)
    percent = progress * 100

    print(
        f"\r[{bar}] {current}/{total} Frames ({percent:5.1f}%)",
        end="",
        flush=True,
    )


def record_config(fps, repetition, order_index):
    target_frames = int(fps * RECORD_TIME_S)


    print()
    print("=" * 60)
    print(f"FPS={fps}, repetition={repetition}, order={order_index}")
    print(f"Target frames: {target_frames}")
    print("=" * 60)

    data_buffer = np.zeros(
        (target_frames, NUM_RX_ANTENNAS, CHIRPS, SAMPLES),
        dtype=np.uint16,
    )

    sync_buffer = np.zeros(
        target_frames,
        dtype=np.uint8,
    )

    sensor = BGT60SensorThreaded(
        port=PORT,
        NUM_RX_ANTENNAS=NUM_RX_ANTENNAS,
        NUM_CHIRPS=CHIRPS,
        NUM_SAMPLES=SAMPLES,
    )

    valid_frames = 0

    try:
        sensor.start(
            gain_db=IF_GAIN_DB,
            tx_power=TX_POWER,
            fps=fps,
        )

        print(f"Settling {SETTLING_TIME_S}s...")
        time.sleep(SETTLING_TIME_S)

        sensor.clear_queue()

        print("Recording...")

        start_t = time.time()

        while valid_frames < target_frames:
            _, sync_state, frame_content = sensor.get_next_frame()

            if frame_content is None:
                continue

            data_buffer[valid_frames] = frame_content
            sync_buffer[valid_frames] = sync_state
            valid_frames += 1

            print_progress(valid_frames, target_frames)

        stop_t = time.time()
        print()

    except KeyboardInterrupt:
        print()
        print("Interrupted.")

    finally:
        sensor.stop()
        sensor.close()

    np.save(os.path.join(output_folder, f"fps_{fps:03d}_order_{order_index:02d}_rep_{repetition}_data.npy"), data_buffer)
    np.save(os.path.join(output_folder, f"fps_{fps:03d}_order_{order_index:02d}_rep_{repetition}_sync_state.npy"), sync_buffer)


    print(f"Saved: {output_folder}/data.npy")
    print(f"Shape: {data_buffer.shape}")
    print(f"Time: {stop_t - start_t:.2f}s")


# ===========================================================================
# MAIN
# ===========================================================================

if __name__ == "__main__":

    for rep in range(1, REPETITIONS + 1):

        fps_order = FPS_LIST.copy()

        if RANDOMIZE_ORDER:
            random.shuffle(fps_order)

        print()
        print(f"Repetition {rep} FPS order: {fps_order}")

        for order_index, fps in enumerate(fps_order, start=1):
            record_config(fps, rep, order_index)
            time.sleep(1.0)

    print()
    print("Done.")