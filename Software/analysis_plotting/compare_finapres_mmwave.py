# -----------------------------------------------------------------------------
#
# File: compare_finapres_mmwave.py
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

import os
import numpy as np
import matplotlib.pyplot as plt

from scipy.signal import butter, filtfilt, find_peaks
from scipy.interpolate import interp1d


# ============================================================
# CONFIG
# ============================================================
root = os.path.join("data", "biogap_measurments", "radar_fps_sweep")

path_temple = os.path.join(root, "radar_invivo_fps_sweep_2026-05-22_18-00","fps_200_order_01_rep_1_data.npy")
path_wrist = os.path.join(root, "radar_invivo_fps_sweep_2026-05-22_18-36","fps_200_order_01_rep_1_data.npy")

files = [path_temple, path_wrist]

RECORDING_TIME_S = 20*60

RADAR_FREQ_GHZ = 60.75

LOWCUT_HZ = 0.5
HIGHCUT_HZ = 8.0
FILTER_ORDER = 4

# Bin selection
BIN_SEARCH_START = 1      # skip DC / very near bin
BIN_SEARCH_END = 3     # None = all available bins

# Beat segmentation
POINTS_PER_BEAT = 200

# Peak detection
MIN_HEART_PERIOD_S = 0.35   # 0.35 s = ~171 bpm max
PROMINENCE_FACTOR = 0.20


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def bandpass_filter(x, fs, lowcut, highcut, order=4, axis=0):
    nyquist = 0.5 * fs

    if highcut >= nyquist:
        highcut = 0.95 * nyquist

    b, a = butter(
        order,
        [lowcut / nyquist, highcut / nyquist],
        btype="band"
    )

    return filtfilt(b, a, x, axis=axis)


def phase_to_displacement_mm(unwrapped_phase, radar_freq_ghz):
    c = 3e8
    wavelength_m = c / (radar_freq_ghz * 1e9)
    wavelength_mm = wavelength_m * 1000.0

    displacement_mm = (wavelength_mm * unwrapped_phase) / (4 * np.pi)

    return displacement_mm


def detect_systolic_and_diastolic(signal, fs):
    min_distance = max(1, int(MIN_HEART_PERIOD_S * fs))
    prominence = max(1e-12, PROMINENCE_FACTOR * np.nanstd(signal))

    systolic_peaks, _ = find_peaks(
        signal,
        distance=min_distance,
        prominence=prominence
    )

    diastolic_valleys, _ = find_peaks(
        -signal,
        distance=min_distance,
        prominence=prominence
    )

    return systolic_peaks, diastolic_valleys


def correct_polarity(signal, fs):
    """
    Ensures that the dominant pulsatile peaks are positive.
    This is a simple shape-based polarity correction.
    """

    min_distance = max(1, int(MIN_HEART_PERIOD_S * fs))
    prominence = max(1e-12, PROMINENCE_FACTOR * np.nanstd(signal))

    pos_peaks, _ = find_peaks(
        signal,
        distance=min_distance,
        prominence=prominence
    )

    neg_peaks, _ = find_peaks(
        -signal,
        distance=min_distance,
        prominence=prominence
    )

    if len(pos_peaks) == 0 or len(neg_peaks) == 0:
        # fallback to your previous skewness-like method
        if np.nanmean(signal ** 3) < 0:
            return -signal
        return signal

    pos_amp = np.nanmean(signal[pos_peaks])
    neg_amp = np.nanmean(-signal[neg_peaks])

    if neg_amp > pos_amp:
        signal = -signal

    return signal


def extract_normalized_beats(signal, valley_indices, points_per_beat=200):
    """
    Extract beat segments between consecutive diastolic valleys.
    Each beat is normalized in amplitude and time.
    """

    beats = []

    valley_indices = np.sort(valley_indices)

    for i in range(len(valley_indices) - 1):
        start = valley_indices[i]
        end = valley_indices[i + 1]

        beat = signal[start:end]

        if len(beat) < 10:
            continue

        # amplitude normalization: 0 ... 1
        beat = beat - np.nanmin(beat)
        beat = beat / (np.nanmax(beat) + 1e-12)

        # time normalization: 0 ... 1
        x_old = np.linspace(0, 1, len(beat))
        x_new = np.linspace(0, 1, points_per_beat)

        f = interp1d(x_old, beat, kind="linear")
        beat_interp = f(x_new)

        beats.append(beat_interp)

    return np.array(beats)

def detect_peaks_and_footpoints(signal, fs):
    """
    Detect systolic peaks and one foot/diastolic valley before each peak.
    Better for pulse waveform segmentation.
    """

    min_peak_distance = max(1, int(0.45 * fs))
    prominence = max(1e-12, 0.25 * np.nanstd(signal))

    systolic_peaks, _ = find_peaks(
        signal,
        distance=min_peak_distance,
        prominence=prominence
    )

    if len(systolic_peaks) < 2:
        return systolic_peaks, np.array([], dtype=int)

    footpoints = []

    for i in range(1, len(systolic_peaks)):
        prev_peak = systolic_peaks[i - 1]
        curr_peak = systolic_peaks[i]

        rr = curr_peak - prev_peak

        # Search before current systolic peak
        search_start = curr_peak - int(0.65 * rr)
        search_end = curr_peak - int(0.08 * rr)

        search_start = max(0, search_start)
        search_end = max(search_start + 1, search_end)

        segment = signal[search_start:search_end]

        if len(segment) == 0:
            continue

        foot_idx = search_start + np.nanargmin(segment)
        footpoints.append(foot_idx)

    return systolic_peaks, np.array(footpoints, dtype=int)


def process_mmwave_file(
    file_path,
    recording_time_s,
    radar_freq_ghz=60.75,
    bin_search_start=1,
    bin_search_end=None,
):
    """
    mmWave processing pipeline adapted from Nimas Work

    Expected raw data shape:
    frames x antennas x chirps x samples
    """

    data = np.load(file_path)

    num_frames, num_antennas, num_chirps, num_samples = data.shape
    fps = num_frames / recording_time_s
    time_axis = np.arange(num_frames) / fps

    print("\nProcessing:", file_path)
    print("Raw shape:", data.shape)
    print("Estimated fps:", fps)

    # ------------------------------------------------------------
    # 1. DC removal across samples per chirp
    # ------------------------------------------------------------
    mean_removed = data - np.mean(data, axis=-1, keepdims=True)

    # ------------------------------------------------------------
    # 2. Windowing across ADC samples
    # ------------------------------------------------------------
    window = np.hanning(num_samples)
    windowed_data = mean_removed * window

    # ------------------------------------------------------------
    # 3. Range FFT along sample dimension
    # Shape: frames x antennas x chirps x range_bins
    # ------------------------------------------------------------
    range_fft = np.fft.rfft(windowed_data, axis=-1)

    # ------------------------------------------------------------
    # 4. Complex averaging over chirps
    # Shape: frames x antennas x range_bins
    # ------------------------------------------------------------
    complex_mean = np.mean(range_fft, axis=2)

    # ------------------------------------------------------------
    # 5. Phase extraction and temporal unwrapping
    # ------------------------------------------------------------
    phase = np.angle(complex_mean)
    unwrapped_phase = np.unwrap(phase, axis=0)

    # ------------------------------------------------------------
    # 6. Convert phase to displacement
    # Shape: frames x antennas x range_bins
    # ------------------------------------------------------------
    displacement_mm = phase_to_displacement_mm(
        unwrapped_phase,
        radar_freq_ghz
    )

    # ------------------------------------------------------------
    # 7. Bandpass filtering, 4th-order Butterworth 0.5–8 Hz
    # ------------------------------------------------------------
    filtered_phase = bandpass_filter(
        displacement_mm,
        fps,
        LOWCUT_HZ,
        HIGHCUT_HZ,
        order=FILTER_ORDER,
        axis=0
    )

    # ------------------------------------------------------------
    # 8. Automatic antenna/range-bin selection
    # highest peak-to-peak amplitude of pulsatile signal
    # ------------------------------------------------------------
    num_bins = filtered_phase.shape[2]

    if bin_search_end is None:
        bin_search_end = num_bins

    bin_search_end = min(bin_search_end, num_bins)

    search_data = filtered_phase[:, :, bin_search_start:bin_search_end]

    peak_to_peak = np.nanmax(search_data, axis=0) - np.nanmin(search_data, axis=0)

    best_ant_rel, best_bin_rel = np.unravel_index(
        np.nanargmax(peak_to_peak),
        peak_to_peak.shape
    )

    best_ant = best_ant_rel
    best_bin = best_bin_rel + bin_search_start

    vital_signal = filtered_phase[:, best_ant, best_bin]

    print("Selected antenna:", best_ant)
    print("Selected range bin:", best_bin)
    print("Peak-to-peak amplitude:", peak_to_peak[best_ant_rel, best_bin_rel], "mm")

    # ------------------------------------------------------------
    # 9. Polarity correction
    # ------------------------------------------------------------
    vital_signal = correct_polarity(vital_signal, fps)

    # ------------------------------------------------------------
    # 10. Peak detection
    # ------------------------------------------------------------
    systolic_peaks, diastolic_valleys = detect_peaks_and_footpoints(
        vital_signal,
        fps
    )

    print("Detected systolic peaks:", len(systolic_peaks))
    print("Detected diastolic valleys:", len(diastolic_valleys))

    # ------------------------------------------------------------
    # 11. IBI from diastolic valleys
    # ------------------------------------------------------------
    if len(diastolic_valleys) > 1:
        ibi_s = np.diff(time_axis[diastolic_valleys])
        hr_bpm = 60.0 / ibi_s
    else:
        ibi_s = np.array([])
        hr_bpm = np.array([])

    # ------------------------------------------------------------
    # 12. Beat morphology extraction
    # ------------------------------------------------------------
    beats = extract_normalized_beats(
        vital_signal,
        diastolic_valleys,
        points_per_beat=POINTS_PER_BEAT
    )

    if len(beats) > 0:
        average_pulse = np.nanmean(beats, axis=0)
        std_pulse = np.nanstd(beats, axis=0)
    else:
        average_pulse = None
        std_pulse = None

    return {
        "file_path": file_path,
        "data_shape": data.shape,
        "fps": fps,
        "time_axis": time_axis,
        "filtered_all_bins": filtered_phase,
        "vital_signal": vital_signal,
        "best_ant": best_ant,
        "best_bin": best_bin,
        "systolic_peaks": systolic_peaks,
        "diastolic_valleys": diastolic_valleys,
        "ibi_s": ibi_s,
        "hr_bpm": hr_bpm,
        "beats": beats,
        "average_pulse": average_pulse,
        "std_pulse": std_pulse,
    }


# ============================================================
# MANEUVER / PROTOCOL MARKERS
# ============================================================

maneuvers = [
    ("Hand Grip 1", 90, 120),
    ("Hand Grip 2", 210, 240),
    ("Hand Grip 3", 330, 360),

    ("Cold Pressor 1", 450, 480),
    ("Cold Pressor 2", 570, 600),

    ("Valsalva 1", 690, 720),
    ("Valsalva 2", 810, 840),

    ("Stand Up 1", 930, 960),
    ("Stand Up 2", 1050, 1080),
]


def add_maneuver_regions(ax, maneuvers, label_y_frac=0.95):
    """
    Add shaded maneuver intervals to a matplotlib axis.
    Times are in seconds relative to the recording start.
    """

    y_min, y_max = ax.get_ylim()
    y_text = y_min + label_y_frac * (y_max - y_min)

    for label, start_s, end_s in maneuvers:
        ax.axvspan(
            start_s,
            end_s,
            alpha=0.14,
            linewidth=0,
        )

        ax.text(
            (start_s + end_s) / 2,
            y_text,
            label,
            ha="center",
            va="top",
            fontsize=8,
            rotation=0,
        )

# ============================================================
# MAIN LOOP
# ============================================================

results = []

for file_path in files:
    result = process_mmwave_file(
        file_path=file_path,
        recording_time_s=RECORDING_TIME_S,
        radar_freq_ghz=RADAR_FREQ_GHZ,
        bin_search_start=BIN_SEARCH_START,
        bin_search_end=BIN_SEARCH_END,
    )

    results.append(result)

    t = result["time_axis"]
    signal = result["vital_signal"]
    systolic_peaks = result["systolic_peaks"]
    diastolic_valleys = result["diastolic_valleys"]

    # ------------------------------------------------------------
    # Plot processed pulse signal with detected peaks
    # ------------------------------------------------------------
    plt.figure(figsize=(12, 4))

    plt.plot(
        t,
        signal,
        linewidth=1.5,
        label=f"mmWave phase signal, ant {result['best_ant']}, bin {result['best_bin']}"
    )

    plt.plot(
        t[systolic_peaks],
        signal[systolic_peaks],
        "x",
        label="Systolic peaks"
    )

    plt.plot(
        t[diastolic_valleys],
        signal[diastolic_valleys],
        "o",
        markersize=4,
        label="Diastolic valleys"
    )

    plt.title("Processed mmWave pulse signal")
    plt.xlabel("Time [s]")
    #plt.xlim((30,40))
    plt.ylabel("Displacement [mm]")
    plt.grid(True, linestyle=":", alpha=0.6)
    add_maneuver_regions(plt.gca(), maneuvers)
    plt.legend()
    plt.tight_layout()
    plt.show()

    # ------------------------------------------------------------
    # Plot average pulse morphology
    # ------------------------------------------------------------
    if result["average_pulse"] is not None:
        x_norm = np.linspace(0, 1, POINTS_PER_BEAT)

        plt.figure(figsize=(7, 4))

        plt.plot(
            x_norm,
            result["average_pulse"],
            linewidth=2,
            label="Average normalized pulse"
        )

        plt.fill_between(
            x_norm,
            result["average_pulse"] - result["std_pulse"],
            result["average_pulse"] + result["std_pulse"],
            alpha=0.25,
            label="±1 std"
        )

        plt.title("Average normalized pulse waveform")
        plt.xlabel("Normalized beat time")
        plt.ylabel("Normalized amplitude")
        plt.grid(True, linestyle=":", alpha=0.6)
        plt.legend()
        plt.tight_layout()
        plt.show()

    # ------------------------------------------------------------
    # Optional HR / IBI plot
    # ------------------------------------------------------------
    if len(result["hr_bpm"]) > 0:
        ibi_time = t[diastolic_valleys[1:]]

        plt.figure(figsize=(10, 3))

        plt.plot(
            ibi_time,
            result["hr_bpm"],
            marker="o",
            linewidth=1.2
        )

        plt.title("Heart rate estimated from diastolic valleys")
        plt.xlabel("Time [s]")
        plt.ylabel("Heart rate [bpm]")
        plt.grid(True, linestyle=":", alpha=0.6)
        add_maneuver_regions(plt.gca(), maneuvers)
        plt.tight_layout()
        plt.show()