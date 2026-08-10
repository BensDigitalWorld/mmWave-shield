# -----------------------------------------------------------------------------
#
# File: snr_analysis.py
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
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from scipy.signal import butter, filtfilt


# ============================================================
# CONFIG
# ============================================================


OUTPUT_FOLDER_NAME = "snr_vs_fps_output"
OUTPUT_FOLDER = os.path.join("plots", OUTPUT_FOLDER_NAME)

INPUT_ROOT = os.path.join("data", "biogap_measurments", "radar_fps_sweep")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Each folder contains ONE measurement condition.
# Adjust these paths and labels.
EXPERIMENTS = [
    {
        "folder": os.path.join(INPUT_ROOT, "radar_invivo_fps_sweep_2026-05-22_18-28"),
        "site": "wrist",
        "gain": 18,
    },
    {
        "folder": os.path.join(INPUT_ROOT,"radar_invivo_fps_sweep_2026-05-22_17-14"),
        "site": "wrist",
        "gain": 33,
    },
        {
        "folder": os.path.join(INPUT_ROOT,"radar_invivo_fps_sweep_2026-05-22_17-51"),
        "site": "temple",
        "gain": 18,
    },
        {
        "folder": os.path.join(INPUT_ROOT,"radar_invivo_fps_sweep_2026-05-22_17-28"),
        "site": "temple",
        "gain": 33,
    },
    # Example:
    # {
    #     "folder": r"radar_invivo_fps_sweep_2026-05-22_18-45",
    #     "site": "temple",
    #     "gain": 33,
    # },
    # {
    #     "folder": r"radar_invivo_fps_sweep_2026-05-22_19-10",
    #     "site": "radial artery",
    #     "gain": 18,
    # },
    # {
    #     "folder": r"radar_invivo_fps_sweep_2026-05-22_19-30",
    #     "site": "radial artery",
    #     "gain": 33,
    # },
]

RADAR_FREQ_GHZ = 60.75

# Main processing filter
BANDPASS_LOW_HZ = 0.5
BANDPASS_HIGH_HZ = 8.0
FILTER_ORDER = 4

# SNR bands
SNR_SIGNAL_BAND = (0.5, 6.0)
SNR_NOISE_BAND = (6.0, 12.0)

# Range-bin search
BIN_SEARCH_START = 1
BIN_SEARCH_END = 3  # None = all bins

PLOT_DPI = 300


# ============================================================
# HELPERS
# ============================================================

def parse_filename(filename):
    """
    Expected:
        fps_025_order_03_rep_2_data.npy
        fps_200_order_05_rep_1_data.npy

    order is only acquisition order, not site/gain.
    """
    name = os.path.basename(filename)

    m = re.match(
        r"^fps_(\d+)_order_(\d+)_rep_(\d+)_data\.npy$",
        name
    )

    if not m:
        return None

    return {
        "fps": int(m.group(1)),
        "order": int(m.group(2)),
        "rep": int(m.group(3)),
    }


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

    return (wavelength_mm * unwrapped_phase) / (4 * np.pi)


def estimate_snr_db(x, fs):
    """
    SNR estimate:
    0.5–6 Hz = pulse-related signal band
    6–12 Hz  = higher-frequency noise estimate
    """
    signal = bandpass_filter(
        x,
        fs,
        SNR_SIGNAL_BAND[0],
        SNR_SIGNAL_BAND[1],
        order=FILTER_ORDER
    )

    noise = bandpass_filter(
        x,
        fs,
        SNR_NOISE_BAND[0],
        SNR_NOISE_BAND[1],
        order=FILTER_ORDER
    )

    p_signal = np.nanmean(signal ** 2)
    p_noise = np.nanmean(noise ** 2)

    return 10 * np.log10((p_signal + 1e-12) / (p_noise + 1e-12))


def process_phase_only(file_path, fps, fixed_ant=None, fixed_bin=None):
    """
    Phase-only mmWave processing.

    Expected raw shape:
        frames x antennas x chirps x samples
    """

    data = np.load(file_path)

    num_frames, num_antennas, num_chirps, num_samples = data.shape
    time_axis = np.arange(num_frames) / fps

    # ------------------------------------------------------------
    # 1. DC removal across samples per chirp
    # ------------------------------------------------------------
    mean_removed = data - np.mean(data, axis=-1, keepdims=True)

    # ------------------------------------------------------------
    # 2. Windowing
    # ------------------------------------------------------------
    window = np.hanning(num_samples)
    windowed_data = mean_removed * window

    # ------------------------------------------------------------
    # 3. Range FFT
    # Shape: frames x antennas x chirps x range_bins
    # ------------------------------------------------------------
    range_fft = np.fft.rfft(windowed_data, axis=-1)

    # ------------------------------------------------------------
    # 4. Complex averaging over chirps, then phase extraction
    # Shape: frames x antennas x range_bins
    # ------------------------------------------------------------
    complex_mean = np.mean(range_fft, axis=2)

    phase = np.angle(complex_mean)
    unwrapped_phase = np.unwrap(phase, axis=0)

    displacement_mm = phase_to_displacement_mm(
        unwrapped_phase,
        RADAR_FREQ_GHZ
    )

    # ------------------------------------------------------------
    # 5. Filter for bin selection and waveform extraction
    # ------------------------------------------------------------
    filtered_phase = bandpass_filter(
        displacement_mm,
        fps,
        BANDPASS_LOW_HZ,
        BANDPASS_HIGH_HZ,
        order=FILTER_ORDER,
        axis=0
    )

    # ------------------------------------------------------------
    # 6. Antenna / range-bin selection
    # ------------------------------------------------------------

    if fixed_ant is not None and fixed_bin is not None:
        best_ant = int(fixed_ant)
        best_bin = int(fixed_bin)
    else:
        num_bins = filtered_phase.shape[2]

        if BIN_SEARCH_END is None:
            bin_search_end = num_bins
        else:
            bin_search_end = min(BIN_SEARCH_END, num_bins)

        bin_indices = np.arange(BIN_SEARCH_START, bin_search_end)

        if len(bin_indices) == 0:
            raise ValueError(f"No bins available in {file_path}")

        search_data = filtered_phase[:, :, bin_indices]

        peak_to_peak = (
            np.nanmax(search_data, axis=0)
            - np.nanmin(search_data, axis=0)
        )

        best_ant_rel, best_bin_rel = np.unravel_index(
            np.nanargmax(peak_to_peak),
            peak_to_peak.shape
        )

        best_ant = int(best_ant_rel)
        best_bin = int(bin_indices[best_bin_rel])
    selected_filtered_signal = filtered_phase[:, best_ant, best_bin]

    # Polarity correction for nicer waveform comparison
    if np.nanmean(selected_filtered_signal ** 3) < 0:
        selected_filtered_signal *= -1

    # ------------------------------------------------------------
    # 7. SNR estimate on unfiltered displacement of selected bin
    # ------------------------------------------------------------
    selected_unfiltered_signal = displacement_mm[:, best_ant, best_bin]
    snr_db = estimate_snr_db(selected_unfiltered_signal, fps)

    return {
        "time_axis": time_axis,
        "signal": selected_filtered_signal,
        "snr_db": snr_db,
        "best_ant": best_ant,
        "best_bin": best_bin,
        "num_frames": num_frames,
        "num_antennas": num_antennas,
        "num_chirps": num_chirps,
        "num_samples": num_samples,
        "duration_s": num_frames / fps,
    }


def find_fixed_bin_for_folder(folder):
    """
    Determines one fixed antenna/bin combination for all recordings in a folder.
    Uses the mean peak-to-peak amplitude across all recordings.
    """

    data_files = sorted([
        f for f in os.listdir(folder)
        if f.endswith("_data.npy")
    ])

    metrics = []

    for filename in data_files:
        parsed = parse_filename(filename)

        if parsed is None:
            continue

        fps = parsed["fps"]
        file_path = os.path.join(folder, filename)

        data = np.load(file_path)

        num_frames, num_antennas, num_chirps, num_samples = data.shape

        mean_removed = data - np.mean(data, axis=-1, keepdims=True)
        window = np.hanning(num_samples)
        windowed_data = mean_removed * window

        range_fft = np.fft.rfft(windowed_data, axis=-1)

        complex_mean = np.mean(range_fft, axis=2)
        phase = np.angle(complex_mean)
        unwrapped_phase = np.unwrap(phase, axis=0)

        displacement_mm = phase_to_displacement_mm(
            unwrapped_phase,
            RADAR_FREQ_GHZ
        )

        filtered_phase = bandpass_filter(
            displacement_mm,
            fps,
            BANDPASS_LOW_HZ,
            BANDPASS_HIGH_HZ,
            order=FILTER_ORDER,
            axis=0
        )

        num_bins = filtered_phase.shape[2]

        if BIN_SEARCH_END is None:
            bin_search_end = num_bins
        else:
            bin_search_end = min(BIN_SEARCH_END, num_bins)

        bin_indices = np.arange(BIN_SEARCH_START, bin_search_end)

        search_data = filtered_phase[:, :, bin_indices]

        peak_to_peak = (
            np.nanmax(search_data, axis=0)
            - np.nanmin(search_data, axis=0)
        )

        metrics.append(peak_to_peak)

    if len(metrics) == 0:
        raise ValueError(f"No valid data files found in {folder}")

    mean_metric = np.nanmean(np.stack(metrics, axis=0), axis=0)

    best_ant_rel, best_bin_rel = np.unravel_index(
        np.nanargmax(mean_metric),
        mean_metric.shape
    )

    best_ant = int(best_ant_rel)
    best_bin = int(best_bin_rel + BIN_SEARCH_START)

    print(f"Fixed selection for {folder}: antenna {best_ant}, bin {best_bin}")

    return best_ant, best_bin

def normalize_for_plot(x):
    return (x - np.nanmean(x)) / (np.nanstd(x) + 1e-12)


# ============================================================
# PROCESS ALL FOLDERS
# ============================================================

rows = []
waveforms = {}

for exp in EXPERIMENTS:
    folder = exp["folder"]
    site = exp["site"]
    gain = exp["gain"]

    fixed_ant, fixed_bin = find_fixed_bin_for_folder(folder)

    data_files = sorted([
        f for f in os.listdir(folder)
        if f.endswith("_data.npy")
    ])

    print(f"\nFolder: {folder}")
    print(f"Site: {site}, gain: {gain}")
    print(f"Found {len(data_files)} data files.")

    for filename in data_files:
        parsed = parse_filename(filename)

        if parsed is None:
            print(f"Skipping unknown filename format: {filename}")
            continue

        file_path = os.path.join(folder, filename)

        fps = parsed["fps"]
        order = parsed["order"]
        rep = parsed["rep"]

        print(
            f"Processing {filename} | "
            f"fps={fps}, order={order}, rep={rep}, "
            f"site={site}, gain={gain}"
        )

        result = process_phase_only(
            file_path,
            fps=fps,
            fixed_ant=fixed_ant,
            fixed_bin=fixed_bin
        )
        row = {
            "folder": folder,
            "filename": filename,
            "site": site,
            "gain": gain,
            "fps": fps,
            "order": order,
            "rep": rep,
            "fixed_selection": True,
            "snr_db": result["snr_db"],
            "best_ant": result["best_ant"],
            "best_bin": result["best_bin"],
            "num_frames": result["num_frames"],
            "num_chirps": result["num_chirps"],
            "num_samples": result["num_samples"],
            "duration_s": result["duration_s"],
        }

        rows.append(row)

        key = f"{site}_gain{gain}_{filename}"

        waveforms[key] = {
            "time_axis": result["time_axis"],
            "signal": result["signal"],
            **row,
        }


df = pd.DataFrame(rows)

df.to_csv(
    os.path.join(OUTPUT_FOLDER, "snr_per_recording.csv"),
    index=False
)

print("\nPer-recording results:")
print(df)


# ============================================================
# SUMMARY: mean ± std over repetitions
# ============================================================

summary = df.groupby(
    ["site", "gain", "fps"],
    dropna=False
).agg(
    snr_mean_db=("snr_db", "mean"),
    snr_std_db=("snr_db", "std"),
    snr_min_db=("snr_db", "min"),
    snr_max_db=("snr_db", "max"),
    repetitions=("snr_db", "count"),
).reset_index()

summary.to_csv(
    os.path.join(OUTPUT_FOLDER, "snr_summary_vs_fps.csv"),
    index=False
)

print("\nSummary:")
print(summary)


# ============================================================
# BAR PLOT: SNR per configuration
# One figure per measurement site
# Two bars per FPS/configuration: Gain 18 dB and Gain 33 dB
# ============================================================

for site in summary["site"].dropna().unique():
    site_data = summary[summary["site"] == site].copy()

    if len(site_data) == 0:
        continue

    # Sort configurations by FPS
    fps_values = sorted(site_data["fps"].dropna().unique())
    gains = sorted(site_data["gain"].dropna().unique())

    x = np.arange(len(fps_values))
    bar_width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))

    # Fixed color mapping
    gain_colors = {
        18: "tab:blue",
        33: "tab:orange",
    }

    # Draw one bar group per gain
    for i, gain in enumerate(gains):
        gain_data = site_data[site_data["gain"] == gain].copy()
        gain_data = gain_data.set_index("fps").reindex(fps_values).reset_index()

        y = gain_data["snr_mean_db"].to_numpy(dtype=float)
        yerr = gain_data["snr_std_db"].fillna(0).to_numpy(dtype=float)

        # shift bars left/right
        offset = (i - (len(gains) - 1) / 2) * bar_width

        bars = ax.bar(
            x + offset,
            y,
            width=bar_width,
            yerr=yerr,
            capsize=4,
            label=f"Gain {int(gain)} dB",
            color=gain_colors.get(gain, None),
            edgecolor="black",
            linewidth=0.8,
        )

        # Optional: write mean value above bar
        for xi, yi in zip(x + offset, y):
            if np.isfinite(yi):
                ax.text(
                    xi,
                    yi + 0.05,
                    f"{yi:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=8
                )

    ax.set_xticks(x)
    ax.set_xticklabels([f"{fps} FPS" for fps in fps_values])
    ax.set_xlabel("Configuration")
    ax.set_ylabel("SNR [dB]")
    ax.grid(True, axis="y", linestyle=":")
    ax.legend()

    plt.tight_layout()

    out_path = os.path.join(
        OUTPUT_FOLDER,
        f"snr_barplot_{site.replace(' ', '_')}.png"
    )
    plt.savefig(out_path, dpi=PLOT_DPI)
    plt.show()


# ============================================================
# OPTIONAL: Combined plot over all sites/gains
# ============================================================

if len(summary) > 0:
    fig, ax = plt.subplots(figsize=(7, 4))

    for (site, gain), group in summary.groupby(["site", "gain"]):
        group = group.sort_values("fps")

        x = group["fps"].to_numpy(dtype=float)
        y = group["snr_mean_db"].to_numpy(dtype=float)
        yerr = group["snr_std_db"].fillna(0).to_numpy(dtype=float)

        ax.errorbar(
            x,
            y,
            yerr=yerr,
            marker="o",
            capsize=4,
            linewidth=1.5,
            label=f"{site}, gain {int(gain)} dB"
        )

    ax.set_xlabel("Frame rate [FPS]")
    ax.set_ylabel("SNR [dB]")
    ax.grid(True, linestyle=":")
    ax.legend(fontsize=8)

    plt.tight_layout()

    plt.savefig(
        os.path.join(OUTPUT_FOLDER, "snr_vs_fps_all_sites_gains.png"),
        dpi=PLOT_DPI
    )

    plt.show()


# ============================================================
# PLOT D: Representative extracted waveforms
# Select files automatically: lowest and highest FPS per site/gain
# ============================================================

representatives = []

for (site, gain), group in df.groupby(["site", "gain"]):
    group = group.sort_values("fps")

    if len(group) == 0:
        continue

    lowest = group.iloc[0]
    highest = group.iloc[-1]

    representatives.append(lowest)
    if highest["filename"] != lowest["filename"]:
        representatives.append(highest)

if len(representatives) > 0:
    fig, ax = plt.subplots(figsize=(9, 4))

    for row in representatives:
        key = f"{row['site']}_gain{row['gain']}_{row['filename']}"

        if key not in waveforms:
            continue

        w = waveforms[key]

        t = w["time_axis"]
        y = normalize_for_plot(w["signal"])

        ax.plot(
            t,
            y,
            linewidth=1.2,
            label=(
                f"{w['site']}, gain {int(w['gain'])} dB, "
                f"{int(w['fps'])} FPS"
            )
        )

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Normalized displacement")
    ax.grid(True, linestyle=":")
    ax.legend(fontsize=8)

    plt.tight_layout()

    plt.savefig(
        os.path.join(OUTPUT_FOLDER, "representative_waveforms_low_high_fps.png"),
        dpi=PLOT_DPI
    )

    plt.show()



# ============================================================
# PLOT: Representative waveforms for temple and wrist
# Shows 25 FPS vs 200 FPS
# ============================================================

SHOW_GAIN = 18
# set to 18 or 33 if you want to keep gain fixed
# set to None to automatically choose the best SNR recording

TARGET_SITES = ["temple", "wrist"]   # or ["temple", "wrist"] if that is your label
TARGET_FPS = [25, 200]

SHOW_DURATION_S = 5.0    # how many seconds to display
START_TIME_S = 0.0        # can be changed if the beginning is noisy


def normalize_for_plot(x):
    return (x - np.nanmean(x)) / (np.nanstd(x) + 1e-12)


def get_best_recording(df, site, fps, gain=None):
    subset = df[(df["site"] == site) & (df["fps"] == fps)].copy()

    if gain is not None:
        subset = subset[subset["gain"] == gain].copy()

    if len(subset) == 0:
        return None

    # choose the recording with the highest SNR
    subset = subset.sort_values("snr_db", ascending=False)
    return subset.iloc[0]


fig, axs = plt.subplots(1, len(TARGET_SITES), figsize=(12, 4), sharey=True)

if len(TARGET_SITES) == 1:
    axs = [axs]

for ax, site in zip(axs, TARGET_SITES):
    for fps in TARGET_FPS:
        row = get_best_recording(df, site=site, fps=fps, gain=SHOW_GAIN)
        
        if row is None:
            print(f"No recording found for site={site}, fps={fps}, gain={SHOW_GAIN}")
            continue

        key = f"{row['site']}_gain{row['gain']}_{row['filename']}"

        if key not in waveforms:
            print(f"Waveform not found in cache: {key}")
            continue

        w = waveforms[key]

        t = w["time_axis"]
        y = normalize_for_plot(w["signal"])

        if site == 'temple':
            if fps == 200:
                y *= -1
                START_TIME_S = 1

        # crop to a short representative window
        mask = (t >= START_TIME_S) & (t <= START_TIME_S + SHOW_DURATION_S)

        ax.plot(
            t[mask] - START_TIME_S,
            y[mask],
            linewidth=1.5,
            label=f"{int(row['fps'])} FPS, gain {int(row['gain'])} dB"
        )

    ax.set_title(site)
    ax.set_xlabel("Time [s]")
    ax.grid(True, linestyle=":")
    ax.legend(fontsize=8)

axs[0].set_ylabel("Normalized displacement")

plt.tight_layout()
plt.savefig(
    os.path.join(OUTPUT_FOLDER, "representative_waveforms_temple_wrist_25_vs_200fps.png"),
    dpi=PLOT_DPI
)
plt.show()


# ============================================================
# PLOT: one representative waveform per condition
# temple/wrist and 25/200 FPS
# ============================================================

SHOW_GAIN = 18
# set to 18 or 33 if you want a fixed gain
# if you want automatic best recording independent of gain, set to None

TARGET_SITES = ["temple", "wrist"]   # or "radial artery" if that is your label
TARGET_FPS = [25, 200]

SHOW_DURATION_S = 3.0   # shorter window usually looks cleaner than 5 s
START_TIME_S = 0.0


def normalize_for_plot(x):
    return (x - np.nanmean(x)) / (np.nanstd(x) + 1e-12)


def get_best_recording(df, site, fps, gain=None):
    subset = df[(df["site"] == site) & (df["fps"] == fps)].copy()

    if gain is not None:
        subset = subset[subset["gain"] == gain].copy()

    if len(subset) == 0:
        return None

    # choose recording with highest SNR
    subset = subset.sort_values("snr_db", ascending=False)
    return subset.iloc[0]


fig, axs = plt.subplots(2, 2, figsize=(10, 6), sharex=True, sharey=True)

for i, site in enumerate(TARGET_SITES):
    for j, fps in enumerate(TARGET_FPS):
        ax = axs[i, j]

        row = get_best_recording(df, site=site, fps=fps, gain=SHOW_GAIN)

        if row is None:
            ax.set_title(f"{site}, {fps} FPS\nnot available")
            ax.grid(True, linestyle=":")
            continue

        key = f"{row['site']}_gain{row['gain']}_{row['filename']}"

        if key not in waveforms:
            ax.set_title(f"{site}, {fps} FPS\nwaveform missing")
            ax.grid(True, linestyle=":")
            continue

        w = waveforms[key]

        t = w["time_axis"]
        y = w["signal"]
        
        if site == 'temple':
            if fps == 200:
                y *= -1
                START_TIME_S = 1

        mask = (t >= START_TIME_S) & (t <= START_TIME_S + SHOW_DURATION_S)

        ax.plot(
            t[mask] - START_TIME_S,
            y[mask],
            linewidth=1.5
        )

        ax.set_title(
            f"{site}, {fps} FPS"
        )
        ax.grid(True, linestyle=":")

for ax in axs[-1, :]:
    ax.set_xlabel("Time [s]")

for ax in axs[:, 0]:
    ax.set_ylabel("Displacement [mm]")

plt.tight_layout()
plt.savefig(
    os.path.join(OUTPUT_FOLDER, "representative_waveforms_2x2_single.png"),
    dpi=PLOT_DPI
)
plt.show()

# ============================================================
# PLOT: one representative waveform per condition
# temple/wrist and 25/200 FPS
# fixed gain and fixed repetition
# WITHOUT amplitude normalization
# ============================================================

SHOW_GAIN = 18
SHOW_REP = 1

TARGET_SITES = ["temple", "wrist"]   # or "radial artery" if that is your label
TARGET_FPS = [25, 200]

SHOW_DURATION_S = 3.0
START_TIME_S = 0.0


def get_recording_fixed_rep(df, site, fps, gain, rep):
    subset = df[
        (df["site"] == site) &
        (df["fps"] == fps) &
        (df["gain"] == gain) &
        (df["rep"] == rep)
    ].copy()

    if len(subset) == 0:
        return None

    # Usually there should be only one match.
    # If multiple exist, choose the one with highest SNR.
    subset = subset.sort_values("snr_db", ascending=False)
    return subset.iloc[0]


fig, axs = plt.subplots(2, 2, figsize=(10, 6), sharex=True, sharey=True)

for i, site in enumerate(TARGET_SITES):
    for j, fps in enumerate(TARGET_FPS):
        ax = axs[i, j]

        row = get_recording_fixed_rep(
            df,
            site=site,
            fps=fps,
            gain=SHOW_GAIN,
            rep=SHOW_REP
        )

        if row is None:
            ax.set_title(f"{site}, {fps} FPS\nrep {SHOW_REP} not available")
            ax.grid(True, linestyle=":")
            continue

        key = f"{row['site']}_gain{row['gain']}_{row['filename']}"

        if key not in waveforms:
            ax.set_title(f"{site}, {fps} FPS\nwaveform missing")
            ax.grid(True, linestyle=":")
            continue

        w = waveforms[key]

        t = w["time_axis"]
        y = w["signal"]   # no normalization

        if fps == 200:
            START_TIME_S = 0.45
        else:
            START_TIME_S = 0.1

        mask = (t >= START_TIME_S) & (t <= START_TIME_S + SHOW_DURATION_S)

        ax.plot(
            t[mask] - START_TIME_S,
            y[mask],
            linewidth=1.5
        )

        ax.set_title(
            f"{site}, {fps} FPS"
        )
        ax.grid(True, linestyle=":")

for ax in axs[-1, :]:
    ax.set_xlabel("Time [s]")

for ax in axs[:, 0]:
    ax.set_ylabel("Displacement [mm]")

plt.tight_layout()
plt.savefig(
    os.path.join(
        OUTPUT_FOLDER,
        f"representative_waveforms_rep{SHOW_REP}_gain{SHOW_GAIN}_raw.png"
    ),
    dpi=PLOT_DPI
)
plt.show()

print("Done.")
print(f"Results saved to: {OUTPUT_FOLDER}")