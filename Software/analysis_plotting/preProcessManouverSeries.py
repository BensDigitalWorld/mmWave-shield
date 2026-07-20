# -----------------------------------------------------------------------------
#
# File: preProcessManouverSeries.py
#
# Last edited: 14.07.2026
#
# Copyright (C) 2026, ETH Zurich
#
# Authors:
# - Benjamin Löliger, ETH Zurich
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
import zipfile
import numpy as np
import xml.etree.ElementTree as ET

from scipy.signal import butter, filtfilt, find_peaks
from scipy.interpolate import interp1d


# ============================================================
# WRIST CONFIGS
# ============================================================

PREPROCESSED_CACHE_FOLDER = os.path.join("data","processed","wrist")
os.makedirs(PREPROCESSED_CACHE_FOLDER, exist_ok=True)

PREPROCESSED_CACHE_PATH = os.path.join(PREPROCESSED_CACHE_FOLDER,"preprocessed_maneuver_series.npz")
processed_mmwave_path = os.path.join(PREPROCESSED_CACHE_FOLDER, "mmwave_processed.npz")

nsc_path = os.path.join("data", "finaPress_measurments", "2026-05-22_19.24.20.nsc")

mmwave_raw_path =  os.path.join("data","biogap_measurments","manouverSeries","wrist_2026-05-22_18-36","fps_200_order_01_rep_1_data.npy")
mmwave_sync_path = os.path.join("data","biogap_measurments","manouverSeries","wrist_2026-05-22_18-36","fps_200_order_01_rep_1_sync_state.npy")

mmwave_duration_s = 20 * 60   
mmwave_time_shift_s = 0

# Finapres marker event times [s]
finapres_event_1_s = 242.5874
finapres_event_2_s = 1439.447

# Corresponding mmWave sync event times BEFORE correction [s]
mmwave_event_1_s = 0.49
mmwave_event_2_s = 1199.8
'''

# ============================================================
# TEMPLE CONFIGS
# ============================================================
PREPROCESSED_CACHE_FOLDER = os.path.join("data","processed","temple")
os.makedirs(PREPROCESSED_CACHE_FOLDER, exist_ok=True)

PREPROCESSED_CACHE_PATH = os.path.join(PREPROCESSED_CACHE_FOLDER,"preprocessed_maneuver_series.npz")
processed_mmwave_path = os.path.join(PREPROCESSED_CACHE_FOLDER, "mmwave_processed.npz")

nsc_path = os.path.join("data", "finaPress_measurments", "2026-05-22_18.46.42.nsc")

mmwave_raw_path =  os.path.join("data","biogap_measurments","manouverSeries","temple_2026-05-22_18-00","fps_200_order_01_rep_1_data.npy")
mmwave_sync_path = os.path.join("data","biogap_measurments","manouverSeries","temple_2026-05-22_18-00","fps_200_order_01_rep_1_sync_state.npy")

mmwave_duration_s = 20 * 60  
mmwave_time_shift_s = 0

# Finapres marker event times [s]
finapres_event_1_s = 301.6524
finapres_event_2_s = 1498.508

# Corresponding mmWave sync event times BEFORE correction [s]
mmwave_event_1_s = 0.49
mmwave_event_2_s = 1199.94
'''

# ============================================================
# GENERAL CONFIGS
# ============================================================

force_reprocess_mmwave = False
FORCE_REPROCESS_PREPROCESSED = True

# mmWave sync signal

POINTS_PER_BEAT = 200
mmwave_sync_fs = 500  # sampling rate of sync signal, adjust if needed

# Radar parameters
RADAR_FREQ_GHZ = 60.75
ANTENNA_INDEX = 0

# Search only reasonable close range bins
BIN_SEARCH_START = 1
BIN_SEARCH_END = 3

# Optional: use only a clean section for automatic bin selection
# Set to None to use full recording
BIN_SELECTION_START_S = 420
BIN_SELECTION_END_S = 500

# SNR bands
SIGNAL_BAND = (0.5, 8.0)
NOISE_BAND = (8.0, 12.0)

# Plot settings
MAX_POINTS_PER_SIGNAL = 3_000_000


# ============================================================
# BASIC HELPERS
# ============================================================

def normalize_for_overlay(x):
    return (x - np.nanmean(x)) / (np.nanstd(x) + 1e-12)


def downsample_for_plot(t, y, max_points=150_000):
    
    return t, y

    stride = int(np.ceil(len(y) / max_points))
    return t[::stride], y[::stride]


def bandpass_filter(x, fs, lowcut, highcut, order=3, axis=0):
    nyquist = 0.5 * fs

    if highcut >= nyquist:
        highcut = 0.95 * nyquist

    low = lowcut / nyquist
    high = highcut / nyquist

    b, a = butter(order, [low, high], btype="band")
    return filtfilt(b, a, x, axis=axis)


def estimate_snr_db(x, fs, signal_band=(0.5, 6.0), noise_band=(6.0, 12.0)):
    signal = bandpass_filter(x, fs, signal_band[0], signal_band[1], order=3)
    noise = bandpass_filter(x, fs, noise_band[0], noise_band[1], order=3)

    p_signal = np.nanmean(signal ** 2)
    p_noise = np.nanmean(noise ** 2)

    return 10 * np.log10((p_signal + 1e-12) / (p_noise + 1e-12))


# ============================================================
# NOVASCOPE / NSC READER
# ============================================================

def find_file_in_zip(zip_file, filename):
    for name in zip_file.namelist():
        if name.endswith("/" + filename) or name.endswith(filename):
            return name
    raise FileNotFoundError(f"{filename} not found in archive")


def read_xml_from_zip(zip_file, filename):
    path = find_file_in_zip(zip_file, filename)
    xml_bytes = zip_file.read(path)
    xml_text = xml_bytes.decode("utf-8-sig")
    return ET.fromstring(xml_text)


def read_nsd_y_from_zip(zip_file, filename):
    path = find_file_in_zip(zip_file, filename)
    raw = zip_file.read(path)

    y = np.frombuffer(raw, dtype="<i2").astype(float)
    y[y == -32768] = np.nan

    return y


def read_nsd_x_from_zip(zip_file, filename):
    """
    Reads NovaScope X-axis data.
    The X files usually contain time ticks. We try uint32 ticks first.
    """
    path = find_file_in_zip(zip_file, filename)
    raw = zip_file.read(path)

    # Most likely: uint32 ticks
    x_ticks = np.frombuffer(raw, dtype="<u4").astype(float)

    # NovaScope often uses 0.1 ms ticks
    t = x_ticks * 1e-4

    # Make time start at zero
    t = t - t[0]

    return t


def parse_nsc_signals(nsc_path):
    signals = {}

    with zipfile.ZipFile(nsc_path, "r") as z:
        root = read_xml_from_zip(z, "Measurement.xml")

        for container in root.findall(".//SignalContainer"):

            # Get X-axis file for this signal container
            x_file = None
            x_axis = container.find("XAxis")

            if x_axis is not None:
                x_file_node = x_axis.find("DataFile")
                if x_file_node is not None:
                    x_file = x_file_node.text

            for sig in container.findall(".//Signal"):
                short_name = sig.findtext("ShortName")
                name = sig.findtext("Name")
                data_file = sig.findtext("DataFile")
                units = sig.findtext("Units")
                sample_rate = sig.findtext("SampleRate")

                if short_name and data_file:
                    signals[short_name] = {
                        "short_name": short_name,
                        "name": name,
                        "data_file": data_file,
                        "x_file": x_file,
                        "units": units,
                        "sample_rate": float(sample_rate) if sample_rate else None,
                    }

    return signals


def load_nsc_signal(nsc_path, short_name):
    signals = parse_nsc_signals(nsc_path)

    if short_name not in signals:
        available = "\n".join(sorted(signals.keys()))
        raise KeyError(f"Signal '{short_name}' not found. Available signals:\n{available}")

    info = signals[short_name]

    with zipfile.ZipFile(nsc_path, "r") as z:
        y = read_nsd_y_from_zip(z, info["data_file"])

        t = None

        # Prefer true X-axis from NovaScope
        if info["x_file"] is not None:
            try:
                t_candidate = read_nsd_x_from_zip(z, info["x_file"])

                if len(t_candidate) == len(y):
                    t = t_candidate
                else:
                    print(
                        f"Warning: X/Y length mismatch for {short_name}: "
                        f"len(x)={len(t_candidate)}, len(y)={len(y)}. "
                        f"Falling back to sample rate."
                    )
            except Exception as e:
                print(f"Could not read X-axis for {short_name}: {e}")

    # Fallback only if X-axis failed
    if t is None:
        fs = info["sample_rate"]

        if fs is None:
            raise ValueError(f"No valid X-axis or sample rate found for {short_name}")

        t = np.arange(len(y)) / fs

    fs_estimated = 1 / np.nanmedian(np.diff(t))

    print(
        f"{short_name}: duration={t[-1]:.2f}s, "
        f"samples={len(y)}, fs_estimated={fs_estimated:.2f} Hz, "
        f"file={info['data_file']}, x_file={info['x_file']}"
    )

    return t, y, fs_estimated, info



# ============================================================
# PEAK / FOOTPOINT DETECTION ON READY SIGNALS
# No filtering, no polarity correction
# ============================================================
def detect_peaks_and_footpoints(signal, fs):
    """
    Detect systolic peaks and one foot/diastolic valley before each peak.

    Important:
    The footpoint is NOT selected as the deepest point in the search window.
    Instead, the last local valley before the next systolic peak is selected.
    This avoids selecting an earlier, deeper reflection-related valley.
    """

    signal = np.asarray(signal, dtype=float)

    # Work on a copy for peak detection
    y = signal.copy()

    # If signal contains NaNs, interpolate them for peak detection
    nans = np.isnan(y)
    if np.any(nans):
        valid = ~nans

        if np.sum(valid) < 10:
            return np.array([], dtype=int), np.array([], dtype=int)

        y[nans] = np.interp(
            np.flatnonzero(nans),
            np.flatnonzero(valid),
            y[valid]
        )

    # ------------------------------------------------------------
    # 1. Detect systolic peaks
    # ------------------------------------------------------------
    min_peak_distance = max(1, int(0.45 * fs))
    peak_prominence = max(1e-12, 0.25 * np.nanstd(y))

    systolic_peaks, _ = find_peaks(
        y,
        distance=min_peak_distance,
        prominence=peak_prominence
    )

    if len(systolic_peaks) < 2:
        return systolic_peaks, np.array([], dtype=int)

    footpoints = []

    # ------------------------------------------------------------
    # 2. For each peak, find the LAST local valley before it
    # ------------------------------------------------------------
    for i in range(1, len(systolic_peaks)):
        prev_peak = systolic_peaks[i - 1]
        curr_peak = systolic_peaks[i]

        rr = curr_peak - prev_peak

        # Search before current systolic peak.
        # The end excludes the immediate peak region.
        search_start = curr_peak - int(0.65 * rr)
        search_end = curr_peak - int(0.05 * rr)

        search_start = max(0, search_start)
        search_end = max(search_start + 1, search_end)

        segment = y[search_start:search_end]

        if len(segment) < 3:
            continue

        if np.all(np.isnan(segment)):
            continue

        # Find local valleys inside the search window
        local_valleys, _ = find_peaks(
            -segment,
            distance=max(1, int(0.06 * fs)),
            prominence=max(1e-12, 0.03 * np.nanstd(segment))
        )

        if len(local_valleys) > 0:
            # Take the LAST valley before the systolic peak
            foot_idx = search_start + local_valleys[-1]
        else:
            # Fallback:
            # If no local valley is detected, take the minimum in the last
            # part of the search window instead of the full window.
            fallback_start = int(0.65 * len(segment))
            fallback_segment = segment[fallback_start:]

            if len(fallback_segment) == 0 or np.all(np.isnan(fallback_segment)):
                continue

            foot_idx = search_start + fallback_start + np.nanargmin(fallback_segment)

        footpoints.append(foot_idx)

    return systolic_peaks, np.array(footpoints, dtype=int)

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

def compute_ibi_from_indices(t, indices):
    """
    Compute IBI from event indices.
    Works for peaks or footpoints.
    """
    event_times = t[indices]

    if len(event_times) < 2:
        return np.array([]), np.array([])

    ibi_s = np.diff(event_times)
    ibi_ms = ibi_s * 1000.0
    ibi_time = event_times[1:]

    return ibi_time, ibi_ms


def process_ready_signal(
    t,
    signal,
    fs,
    name,
):
    """
    Apply peak and footpoint detection to an already processed signal.

    Important:
    - No additional filtering is applied.
    - No polarity correction is applied.
    - The sampling rate is provided explicitly.
    """

    y = np.asarray(signal, dtype=float).copy()

    systolic_peaks, diastolic_valleys = detect_peaks_and_footpoints(
        y,
        fs
    )

    ibi_time, ibi_ms = compute_ibi_from_indices(
        t,
        diastolic_valleys
    )

    if len(ibi_ms) > 0:
        hr_bpm = 60000.0 / ibi_ms
    else:
        hr_bpm = np.array([])

    beats = extract_normalized_beats(
        y,
        diastolic_valleys,
        points_per_beat=POINTS_PER_BEAT
    )

    if len(beats) > 0:
        average_pulse = np.nanmean(beats, axis=0)
        std_pulse = np.nanstd(beats, axis=0)
    else:
        average_pulse = None
        std_pulse = None

    print(f"\n{name}")
    print(f"Used fs: {fs:.2f} Hz")
    print(f"Detected systolic peaks: {len(systolic_peaks)}")
    print(f"Detected diastolic valleys: {len(diastolic_valleys)}")
    print(f"Detected IBI values: {len(ibi_ms)}")

    return {
        "name": name,
        "t": t,
        "fs": fs,
        "signal": y,
        "systolic_peaks": systolic_peaks,
        "diastolic_valleys": diastolic_valleys,
        "ibi_time": ibi_time,
        "ibi_ms": ibi_ms,
        "hr_bpm": hr_bpm,
        "beats": beats,
        "average_pulse": average_pulse,
        "std_pulse": std_pulse,
    }

# ============================================================
# MMWAVE PROCESSING
# ============================================================

def process_mmwave_raw(
    npy_path,
    duration_s,
    radar_freq_ghz=60.75,
    antenna_index=0,
    bin_search_start=1,
    bin_search_end=8,
    bin_selection_start_s=None,
    bin_selection_end_s=None,
    signal_band=(0.5, 8.0),
    noise_band=(8.0, 12.0),
):
    """
    Expected raw data shape:
    (frames, antennas, chirps, samples)
    """

    data = np.load(npy_path)

    num_frames, num_ant, num_chirps, num_samples = data.shape
    fps = num_frames / duration_s

    print("mmWave raw shape:", data.shape)
    print("Estimated mmWave fps:", fps)

    # Remove DC over ADC samples
    mean_removed = data - np.mean(data, axis=-1, keepdims=True)

    # Window over ADC samples
    window = np.hanning(num_samples)
    windowed_data = mean_removed * window

    # Range FFT
    range_fft = np.fft.rfft(windowed_data, axis=-1)

    # Complex averaging over chirps, then phase extraction
    complex_mean = np.mean(range_fft[:, antenna_index, :, :], axis=1)

    phase = np.angle(complex_mean)
    unwrapped_phase = np.unwrap(phase, axis=0)

    # Phase to displacement
    c = 3e8
    wavelength_m = c / (radar_freq_ghz * 1e9)
    wavelength_mm = wavelength_m * 1000

    displacement_mm = (wavelength_mm * unwrapped_phase) / (4 * np.pi)

    t = np.arange(num_frames) / fps

    num_bins = displacement_mm.shape[1]

    if bin_search_end is None:
        bin_search_end = num_bins

    bin_search_end = min(bin_search_end, num_bins)
    bin_indices = np.arange(bin_search_start, bin_search_end)

    if len(bin_indices) == 0:
        raise ValueError("No range bins available for bin selection.")

    # Use only selected clean time range for automatic bin selection
    if bin_selection_start_s is not None and bin_selection_end_s is not None:
        selection_mask = (t >= bin_selection_start_s) & (t <= bin_selection_end_s)
    else:
        selection_mask = np.ones_like(t, dtype=bool)

    snr_per_bin = []

    for bin_idx in bin_indices:
        x = displacement_mm[selection_mask, bin_idx]

        try:
            snr = estimate_snr_db(
                x,
                fps,
                signal_band=signal_band,
                noise_band=noise_band
            )
        except Exception:
            snr = -np.inf

        snr_per_bin.append(snr)

    snr_per_bin = np.array(snr_per_bin)

    best_bin = int(bin_indices[np.nanargmax(snr_per_bin)])
    best_snr_db = float(np.nanmax(snr_per_bin))

    print("Best range bin:", best_bin)
    print("Best bin SNR:", best_snr_db, "dB")

    # Extract final full-length radar signal from selected bin
    radar_signal = bandpass_filter(
        displacement_mm[:, best_bin],
        fps,
        signal_band[0],
        signal_band[1],
        order=3
    )

    # Optional polarity correction
    #if np.nanmean(radar_signal ** 3) < 0:
    radar_signal *= -1

    return {
        "t": t,
        "signal": radar_signal,
        "fps": fps,
        "best_bin": best_bin,
        "best_snr_db": best_snr_db,
        "snr_per_bin": snr_per_bin,
        "bin_indices": bin_indices,
        "raw_shape": data.shape,
    }


def load_or_process_mmwave():
    if os.path.exists(processed_mmwave_path) and not force_reprocess_mmwave:
        print("Loading processed mmWave:", processed_mmwave_path)
        processed = np.load(processed_mmwave_path)

        return {
            "t": processed["t"],
            "signal": processed["signal"],
            "fps": float(processed["fps"]),
            "best_bin": int(processed["best_bin"]),
            "best_snr_db": float(processed["best_snr_db"]),
            "snr_per_bin": processed["snr_per_bin"],
            "bin_indices": processed["bin_indices"],
        }

    print("Processing raw mmWave data...")

    result = process_mmwave_raw(
        npy_path=mmwave_raw_path,
        duration_s=mmwave_duration_s,
        radar_freq_ghz=RADAR_FREQ_GHZ,
        antenna_index=ANTENNA_INDEX,
        bin_search_start=BIN_SEARCH_START,
        bin_search_end=BIN_SEARCH_END,
        bin_selection_start_s=BIN_SELECTION_START_S,
        bin_selection_end_s=BIN_SELECTION_END_S,
        signal_band=SIGNAL_BAND,
        noise_band=NOISE_BAND,
    )

    np.savez(
        processed_mmwave_path,
        t=result["t"],
        signal=result["signal"],
        fps=result["fps"],
        best_bin=result["best_bin"],
        best_snr_db=result["best_snr_db"],
        snr_per_bin=result["snr_per_bin"],
        bin_indices=result["bin_indices"],
    )

    print("Saved processed mmWave:", processed_mmwave_path)

    return result


def build_protocol_intervals(protocol):
    intervals = []
    t_start = 0.0

    for label, duration in protocol:
        t_end = t_start + duration
        intervals.append({
            "label": label,
            "start_mmwave": t_start,
            "end_mmwave": t_end,
            "duration": duration,
        })
        t_start = t_end

    return intervals


def _result_to_npz(prefix, result, out):
    """Flatten one processed signal result into an npz-compatible dict."""

    keys = [
        "t",
        "signal",
        "systolic_peaks",
        "diastolic_valleys",
        "ibi_time",
        "ibi_ms",
        "hr_bpm",
        "beats",
    ]

    for key in keys:
        out[f"{prefix}_{key}"] = np.asarray(result[key])

    out[f"{prefix}_fs"] = np.asarray(result["fs"])
    out[f"{prefix}_name"] = np.asarray(result["name"])

    out[f"{prefix}_average_pulse"] = (
        np.asarray(result["average_pulse"])
        if result["average_pulse"] is not None
        else np.asarray([])
    )

    out[f"{prefix}_std_pulse"] = (
        np.asarray(result["std_pulse"])
        if result["std_pulse"] is not None
        else np.asarray([])
    )


def _result_from_npz(prefix, data):
    """Reconstruct one processed signal result from an npz file."""

    average_pulse = data[f"{prefix}_average_pulse"]
    std_pulse = data[f"{prefix}_std_pulse"]

    return {
        "name": str(data[f"{prefix}_name"].item()),
        "t": data[f"{prefix}_t"],
        "fs": float(data[f"{prefix}_fs"]),
        "signal": data[f"{prefix}_signal"],
        "systolic_peaks": data[f"{prefix}_systolic_peaks"],
        "diastolic_valleys": data[f"{prefix}_diastolic_valleys"],
        "ibi_time": data[f"{prefix}_ibi_time"],
        "ibi_ms": data[f"{prefix}_ibi_ms"],
        "hr_bpm": data[f"{prefix}_hr_bpm"],
        "beats": data[f"{prefix}_beats"],
        "average_pulse": average_pulse if average_pulse.size > 0 else None,
        "std_pulse": std_pulse if std_pulse.size > 0 else None,
    }


def save_preprocessed_cache(cache_path, results, protocol_intervals, extra):
    """Save processed Finapres/mmWave signals, IBI results, and protocol metadata."""

    cache_folder = os.path.dirname(cache_path)

    if cache_folder != "":
        os.makedirs(cache_folder, exist_ok=True)

    out = {}

    for key, result in results.items():
        _result_to_npz(key, result, out)

    out["protocol_labels"] = np.asarray([p["label"] for p in protocol_intervals])
    out["protocol_start_mmwave"] = np.asarray([p["start_mmwave"] for p in protocol_intervals])
    out["protocol_end_mmwave"] = np.asarray([p["end_mmwave"] for p in protocol_intervals])
    out["protocol_duration"] = np.asarray([p["duration"] for p in protocol_intervals])

    for key, value in extra.items():
        out[key] = np.asarray(value)

    np.savez_compressed(cache_path, **out)

    print("Saved preprocessed cache:", cache_path)


def load_preprocessed_cache(cache_path):
    """Load processed signals and protocol metadata from cache."""

    print("Loading preprocessed cache:", cache_path)

    data = np.load(cache_path, allow_pickle=False)

    results = {
        "finger": _result_from_npz("finger", data),
        "mmwave": _result_from_npz("mmwave", data),
    }

    protocol_intervals = []

    for label, start, end, duration in zip(
        data["protocol_labels"],
        data["protocol_start_mmwave"],
        data["protocol_end_mmwave"],
        data["protocol_duration"],
    ):
        protocol_intervals.append({
            "label": str(label),
            "start_mmwave": float(start),
            "end_mmwave": float(end),
            "duration": float(duration),
        })

    extra = {
        "time_scale": float(data["time_scale"]),
        "time_offset_s": float(data["time_offset_s"]),
        "best_bin": int(data["best_bin"]),
        "best_snr_db": float(data["best_snr_db"]),
    }

    return results, protocol_intervals, extra

# ============================================================
# LOAD SIGNALS
# ============================================================

if os.path.exists(PREPROCESSED_CACHE_PATH) and not FORCE_REPROCESS_PREPROCESSED:
    results, protocol_intervals, extra = load_preprocessed_cache(
        PREPROCESSED_CACHE_PATH
    )

else:
    # NovaScope / Finapres
    t_finger, finger, fs_finger, info_finger = load_nsc_signal(nsc_path, "fiAP")
    t_marker, marker, fs_marker, info_marker = load_nsc_signal(nsc_path, "Marker")

    print("Finger:", fs_finger, "Hz", info_finger["units"])
    print("Marker:", fs_marker, "Hz", info_marker["units"])

    # ============================================================
    # LOAD MMWAVE SIGNAL + SYNC
    # ============================================================

    mmwave = load_or_process_mmwave()

    mmwave_signal = mmwave["signal"]
    t_mmwave_raw = mmwave["t"]          # raw radar time axis, e.g. 0 ... 1200 s

    mmwave_sync = np.load(mmwave_sync_path)

    # Build raw sync time axis so that sync spans the same recording duration
    # as the mmWave radar data
    t_mmwave_sync_raw = np.linspace(
        0,
        t_mmwave_raw[-1],
        len(mmwave_sync),
        endpoint=True
    )

    print("mmWave radar duration:", t_mmwave_raw[-1] - t_mmwave_raw[0], "s")
    print("mmWave sync duration:", t_mmwave_sync_raw[-1] - t_mmwave_sync_raw[0], "s")
    # ============================================================
    # TIME ALIGNMENT: OFFSET + STRETCH
    # ============================================================



    time_scale = (finapres_event_2_s - finapres_event_1_s) / (
        mmwave_event_2_s - mmwave_event_1_s
    )

    time_offset_s = finapres_event_1_s - time_scale * mmwave_event_1_s

    print("time_scale:", time_scale)
    print("time_offset_s:", time_offset_s)

    # Apply the SAME correction to radar data and sync signal
    t_mmwave = t_mmwave_raw * time_scale + time_offset_s
    t_mmwave_sync = t_mmwave_sync_raw * time_scale + time_offset_s


    # ============================================================
    # NORMALIZE FOR VISUAL OVERLAY
    # ============================================================
    finger = (finger - 16384) / 50


    finger_plot = normalize_for_overlay(finger)
    marker_plot = normalize_for_overlay(marker)
    mmwave_plot = normalize_for_overlay(mmwave_signal)
    mmwave_sync_plot = normalize_for_overlay(mmwave_sync)


    # ============================================================
    # RUN DETECTION ON READY / SYNCHRONIZED SIGNALS
    # ============================================================

    finger_result = process_ready_signal(
        t=t_finger,
        signal=finger,
        fs=fs_finger,
        name="Finapres finger pressure",
    )

    mmwave_result = process_ready_signal(
        t=t_mmwave,
        signal=mmwave_signal,
        fs=200,
        name="mmWave wrist",
    )

    results = {
        "finger": finger_result,
        "mmwave": mmwave_result,
    }


    # ============================================================
    # DOWNSAMPLE ONLY FOR PLOTTING
    # ============================================================

    t_finger_p, finger_p = downsample_for_plot(t_finger, finger_plot, MAX_POINTS_PER_SIGNAL)
    t_marker_p, marker_p = downsample_for_plot(t_marker, marker_plot, MAX_POINTS_PER_SIGNAL)
    t_mmwave_p, mmwave_p = downsample_for_plot(t_mmwave, mmwave_plot, MAX_POINTS_PER_SIGNAL)
    t_mmwave_sync_p, mmwave_sync_p = downsample_for_plot(
        t_mmwave_sync,
        mmwave_sync_plot,
        MAX_POINTS_PER_SIGNAL
    )

    # ============================================================
    # EXPERIMENT PROTOCOL MARKERS
    # ============================================================
    # Protocol times are relative to the start of the mmWave recording.
    # They are then transformed to the global Finapres/NovaScope time axis
    # using the same time_scale and time_offset_s as the mmWave signal.


    protocol = [
        ("Rest", 90),
        ("Hand Grip", 30),
        ("Rest", 90),
        ("Hand Grip", 30),
        ("Rest", 90),
        ("Hand Grip", 30),

        ("Rest", 90),
        ("Cold Pressor", 30),
        ("Rest", 90),
        ("Cold Pressor", 30),

        ("Rest", 90),
        ("Valsalva", 30),
        ("Rest", 90),
        ("Valsalva", 30),

        ("Rest", 90),
        ("Stand Up", 30),
        ("Rest", 90),
        ("Stand Up", 30),
        ("Rest", 120),
    ]


    protocol_intervals = build_protocol_intervals(protocol)

    print("Total protocol duration:", protocol_intervals[-1]["end_mmwave"], "s")


    save_preprocessed_cache(
        PREPROCESSED_CACHE_PATH,
        results=results,
        protocol_intervals=protocol_intervals,
        extra={
            "time_scale": time_scale,
            "time_offset_s": time_offset_s,
            "best_bin": mmwave["best_bin"],
            "best_snr_db": mmwave["best_snr_db"],

                # Extra signals for HTML viewer
            "t_marker": t_marker,
            "marker": marker,
            "t_mmwave_sync": t_mmwave_sync,
            "mmwave_sync": mmwave_sync,
        },
    )

