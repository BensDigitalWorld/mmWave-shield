import numpy as np
import os
import time
from datetime import datetime

from bgt_com_class import BGT60SensorThreaded


timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
output_folder = f"radar_session_{timestamp}"

if not os.path.exists(output_folder):
    os.makedirs(output_folder)
    print(f"📁 Ordner erstellt: {output_folder}")

# ===========================================================================
# TEST CONFIGS
# ===========================================================================

RECORD_TIME_S = 30
NUM_RX_ANTENNAS = 1
if_gain_dB = 33
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

    # 3. PRE-ALLOCATION for more speeeed
    num_frames = int(FPS * RECORD_TIME_S)

    data_buffer = np.zeros((num_frames, NUM_RX_ANTENNAS, CHIRPS, SAMPLES), dtype=np.float32)
    time_stamps = np.zeros(num_frames , dtype=np.uint32)
    sensor = BGT60SensorThreaded(
                port='COM4',
                NUM_RX_ANTENNAS=NUM_RX_ANTENNAS,
                NUM_CHIRPS=CHIRPS,
                NUM_SAMPLES=SAMPLES)
    
    valid_frames = 0
    timeouts = 0


    print(f"Aufnahme von {num_frames} Frames läuft...")

    sensor.start(gain_db=None)

    # 4. Data collection
    start_t = time.time()
    try:
        while valid_frames < num_frames:
            time_stamp, sync_state, frame_content = sensor.get_next_frame() 
            if frame_content is None:
                dropped_frames += 1
                print("Kein gültiger Frame erhalten.")
                continue
            # frame_contents[0] enthält die Daten aller RX-Antennen
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

        # 5. Saving
        filename = f"data.npy"
        # os.path.join verbindet Ordnername und Dateiname sicher (unabhängig von Windows/Linux)
    
        np.save(os.path.join(output_folder, "data.npy"), data_buffer)
        np.save(os.path.join(output_folder, "time_stamps.npy"), time_stamps)

        print(f"💾 Files Saved")
        print(f"Took time: {stop_t - start_t:.2f}s (Should be: {RECORD_TIME_S}s)")
