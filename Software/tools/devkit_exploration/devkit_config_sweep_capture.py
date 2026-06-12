import numpy as np
import os
import time
from datetime import datetime
try:
    from ifxradarsdk.fmcw import DeviceFmcw
    from ifxradarsdk.fmcw.types import FmcwSimpleSequenceConfig, FmcwSequenceChirp
except ImportError as exc:
    raise ImportError(
        "The Infineon Radar SDK Python package is required for this script. "
        "Install it from the Radar SDK wheel as described in the README."
    ) from exc


timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
output_folder = f"radar_session_{timestamp}"

if not os.path.exists(output_folder):
    os.makedirs(output_folder)
    print(f"📁 Ordner erstellt: {output_folder}")




# ===========================================================================
# TEST CONFIGS
# ===========================================================================
test_scenarios = [
    #{"name": "minsSettings", "fps": 25, "chirp_repetition_time_s": 12e-6, "chirps": 1, "samples": 8},
    #{"name": "maxDATA_maybe", "fps": 195, "chirp_repetition_time_s": 40e-6, "chirps": 128, "samples": 64},
    {"name": "200fps_35chrep_128ch_32sa", "fps": 200, "chirp_repetition_time_s": 35e-6, "chirps": 128, "samples": 32},
    {"name": "200fps_41chrep_64ch_64sa", "fps": 200, "chirp_repetition_time_s": 41e-6, "chirps": 64, "samples": 64},
    {"name": "200fps_73chrep_32ch_128sa", "fps": 200, "chirp_repetition_time_s": 73e-6, "chirps": 32, "samples": 128},
    {"name": "200fps_17chrep_256ch_8sa", "fps": 200, "chirp_repetition_time_s": 17e-6, "chirps": 256, "samples": 8},
    
    
    {"name": "100fps_25chrep_256ch_32sa", "fps": 100, "chirp_repetition_time_s": 25e-6, "chirps": 256, "samples": 32},
    {"name": "100fps_41chrep_128ch_64sa", "fps": 100, "chirp_repetition_time_s": 41e-6, "chirps": 128, "samples": 64},
    {"name": "100fps_137chrep_64ch_256sa", "fps": 100, "chirp_repetition_time_s": 137e-6, "chirps": 64, "samples": 256},
    {"name": "100fps_17chrep_512ch_8sa", "fps": 100, "chirp_repetition_time_s": 17e-6, "chirps": 512, "samples": 8},

    {"name": "200fps_35chrep_128ch_32sa", "fps": 200, "chirp_repetition_time_s": 35e-6, "chirps": 128, "samples": 32},

    {"name": "50fps_25chrep_512ch_32sa", "fps": 50, "chirp_repetition_time_s": 25e-6, "chirps": 512, "samples": 32},
    {"name": "50fps_17chrep_512ch_8sa", "fps": 50, "chirp_repetition_time_s": 17e-6, "chirps": 512, "samples": 8},
    {"name": "50fps_137chrep_128ch_256sa", "fps":50, "chirp_repetition_time_s": 137e-6, "chirps": 128, "samples": 256},
    {"name": "50fps_41chrep_128ch_64sa", "fps": 50, "chirp_repetition_time_s": 41e-6, "chirps": 128, "samples": 64},

    {"name": "25fps_17chrep_512ch_64sa", "fps": 25, "chirp_repetition_time_s": 17e-6, "chirps": 512, "samples": 8},
    {"name": "25fps_137chrep_512ch_64sa", "fps": 25, "chirp_repetition_time_s": 137e-6, "chirps": 256, "samples": 256},
    {"name": "25fps_25chrep_512ch_64sa", "fps": 25, "chirp_repetition_time_s": 25e-6, "chirps": 512, "samples": 32},
    {"name": "25fps_41chrep_512ch_64sa", "fps": 25, "chirp_repetition_time_s": 41e-6, "chirps": 512, "samples": 64},

    {"name": "200fps_35chrep_128ch_32sa", "fps": 200, "chirp_repetition_time_s": 35e-6, "chirps": 128, "samples": 32},
   
]

RECORD_TIME_S = 10
NUM_RX_ANTENNAS = 1
rx_ant_sel = 1# 1 = RX1, 2 = RX2, 4 = RX3 (BITMASK, 111 = 7 => ALL 3 ANTENNAS)
if_gain_dB = 23

# ===========================================================================
# TEST CONFIGS
# ===========================================================================


with DeviceFmcw() as device:
    print(f"Radar verbunden: {device.get_sensor_type()}")
    

    for idx, scenario in enumerate(test_scenarios, start=1):
        print(f"\n>>> Starte Szenario: {scenario['name']}")
        
        print("Degree in C = ", device.get_temperature())
        
        # 2. KONFIGURATION DYNAMISCH ERSTELLEN
        config = FmcwSimpleSequenceConfig(
            frame_repetition_time_s = 1.0 / scenario['fps'],
            chirp_repetition_time_s = scenario['chirp_repetition_time_s'],
            num_chirps = scenario['chirps'],
            tdm_mimo = False, # ONLY FOR OTHER SENSOR WITH 2 TX ANTENNAS
            chirp = FmcwSequenceChirp(
                start_frequency_Hz = 58e9,
                end_frequency_Hz = 63.5e9,
                sample_rate_Hz = 2e6, # 2 MHz
                num_samples = scenario['samples'],
                rx_mask = rx_ant_sel,          # Bitmask 7 = 111 (RX1, RX2, RX3)  (1 for only RX1)
                tx_mask = 1,          # TX1 activ
                tx_power_level = 23,
                lp_cutoff_Hz = 500000,
                hp_cutoff_Hz = 80000,
                if_gain_dB = if_gain_dB,
            )
        )

        # Configure for each scenario
        sequence = device.create_simple_sequence(config)
        device.set_acquisition_sequence(sequence)

        # 3. PRE-ALLOCATION for more speeeed
        num_frames = int(scenario['fps'] * RECORD_TIME_S)

        data_buffer = np.zeros((num_frames, NUM_RX_ANTENNAS, scenario['chirps'], scenario['samples']), dtype=np.float32)

        print(f"Aufnahme von {num_frames} Frames läuft...")

        # 4. Data collection
        start_t = time.time()
        for frame_idx in range(num_frames):
            frame_contents = device.get_next_frame() 
            # frame_contents[0] enthält die Daten aller RX-Antennen
            data_buffer[frame_idx] = frame_contents[0] 

        stop_t = time.time()
        
        # 5. Saving
        filename = f"{idx:02d}_{scenario['name']}.npy"
        # os.path.join verbindet Ordnername und Dateiname sicher (unabhängig von Windows/Linux)
        full_path = os.path.join(output_folder, filename)
        
        np.save(full_path, data_buffer)
        print(f"💾 File Saved: {full_path}")
        
        print(f"✓ Saved: {filename}")
        print(f"  Took time: {stop_t - start_t:.2f}s (Should be: {RECORD_TIME_S}s)")

        # Kurze Pause zum Abkühlen des Sensors / Vorbereitung
        time.sleep(1)

print("\nAll Measurments finished!")