# -----------------------------------------------------------------------------
#
# File: manouver_plots.py
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
from scipy.interpolate import interp1d
from scipy.signal import find_peaks
# ============================================================
# CONFIG
# ============================================================

OUTPUT_ROOT = "plots"
LOCATION_KEY = "temple"   # "temple" or "wrist"

PREPROCESSED_CACHE_PATH = os.path.join(
    "data",
    "processed",
    LOCATION_KEY,
    "preprocessed_maneuver_series.npz"
)

SAVE_DPI = 500
SHOW_FIGURES = False      # True if you want every plot displayed

SEGMENT_SPACING_S = 60
SEGMENT_DURATION_S = 20
IBI_CONTEXT_S = 5.0 

POINTS_PER_BEAT = 200

segment_names = [
    "rest1",
    "hand1",
    "rest2",
    "hand2",
    "rest3",
    "hand3",
    "rest4",
    "cold1",
    "rest5",
    "cold2",
    "rest6",
    "valsal1",
    "rest7",
    "valsal2",
    "rest8",
    "stand1",
    "rest9",
    "stand2",
    "rest10",
]


SEGMENT_LABELS = {
    "rest1": "Rest Period 1",
    "rest2": "Rest Period 2",
    "rest3": "Rest Period 3",
    "rest4": "Rest Period 4",
    "rest5": "Rest Period 5",
    "rest6": "Rest Period 6",
    "rest7": "Rest Period 7",
    "rest8": "Rest Period 8",
    "rest9": "Rest Period 9",
    "rest10": "Rest Period 10",

    "hand1": "Hand Grip 1",
    "hand2": "Hand Grip 2",
    "hand3": "Hand Grip 3",

    "cold1": "Cold Pressor 1",
    "cold2": "Cold Pressor 2",

    "valsal1": "Valsalva 1",
    "valsal2": "Valsalva 2",

    "stand1": "Stand Up 1",
    "stand2": "Stand Up 2",
}


def segment_label(name):
    return SEGMENT_LABELS.get(name, name)


def location_label(location):
    return {
        "temple": "Temple",
        "wrist": "Wrist",
    }.get(location, location.capitalize())


def is_rest_segment(name):
    return name.startswith("rest")


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)


SAVE_DPI = 500

def save_fig(fig, folder, filename):
    os.makedirs(folder, exist_ok=True)

    pdf_path = os.path.join(folder, filename + ".pdf")

    fig.savefig(
        pdf_path,
        dpi=SAVE_DPI,
        bbox_inches="tight"
    )

    print("Saved:", pdf_path)

    if SHOW_FIGURES:
        plt.show()
    else:
        plt.close(fig)

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


def crop_result(result, start_s, end_s):
    """
    Crops one already processed result dict to an interval.
    Peaks/IBI/average waveform are recomputed inside the cropped interval.
    """

    t = result["t"]
    y = result["signal"]
    fs = result["fs"]

    mask = (t >= start_s) & (t <= end_s)

    t_crop = t[mask]
    y_crop = y[mask]

    if len(t_crop) < 10:
        return None

    peaks, valleys = detect_peaks_and_footpoints(y_crop, fs)

    ibi_time, ibi_ms = compute_ibi_from_indices(t_crop, valleys)

    beats = extract_normalized_beats(
        y_crop,
        valleys,
        points_per_beat=POINTS_PER_BEAT
    )

    if len(beats) > 0:
        avg = np.nanmean(beats, axis=0)
        std = np.nanstd(beats, axis=0)
    else:
        avg = None
        std = None

    return {
        "name": result["name"],
        "t": t_crop,
        "fs": fs,
        "signal": y_crop,
        "systolic_peaks": peaks,
        "diastolic_valleys": valleys,
        "ibi_time": ibi_time,
        "ibi_ms": ibi_ms,
        "beats": beats,
        "average_pulse": avg,
        "std_pulse": std,
    }

def add_maneuver_shading(ax, total_duration_s=20, rest_s=4, transition_s=2):
    rest_start = 0
    rest_end = rest_s

    transition_start = rest_end
    transition_end = rest_end + transition_s

    maneuver_start = transition_end
    maneuver_end = total_duration_s

    # Rest
    ax.axvspan(
        rest_start,
        rest_end,
        facecolor="0.96",
        edgecolor="0.75",
        hatch=".",
        alpha=0.35,
        linewidth=0,
        zorder=0,
    )

    # Transition
    ax.axvspan(
        transition_start,
        transition_end,
        facecolor="0.90",
        edgecolor="0.65",
        hatch="..",
        alpha=0.40,
        linewidth=0,
        zorder=0,
    )

    # Maneuver
    ax.axvspan(
        maneuver_start,
        maneuver_end,
        facecolor="0.96",
        edgecolor="0.75",
        hatch=".",
        alpha=0.35,
        linewidth=0,
        zorder=0,
    )
def plot_ibi(segment_results, segment_name, location, output_dir, segment_start_s, segment_end_s):
    label = segment_label(segment_name)
    loc = location_label(location)
    maneuver = not is_rest_segment(segment_name)

    segment_duration = segment_end_s - segment_start_s

    fig, ax = plt.subplots(figsize=(8, 3.5))

    styles = {
        "mmwave": {
            "label": "mmWave",
            "linestyle": "-",
            "linewidth": 2.0,
            "color": "#1f77b4",
        },
        "finger": {
            "label": "Finger Pressure",
            "linestyle": "--",
            "linewidth": 2.0,
            "color": "#ff7f0e",
        },
    }

    for key in ["mmwave", "finger"]:
        res = segment_results[key]

        if res is None or len(res["ibi_ms"]) == 0:
            continue

        # IBI times are absolute/global; convert to relative segment time
        x = res["ibi_time"] - segment_start_s
        y = res["ibi_ms"]

        # Show only IBIs that fall inside the visible 20 s segment
        mask = (x >= 0) & (x <= segment_duration)

        ax.plot(
            x[mask],
            y[mask],
            linestyle=styles[key]["linestyle"],
            linewidth=styles[key]["linewidth"],
            color=styles[key]["color"],
            label=styles[key]["label"],
        )

    if maneuver:
        add_maneuver_shading(ax, total_duration_s=segment_duration)

    ax.set_xlim(0, segment_duration)
    ax.set_xticks(np.arange(0, segment_duration + 0.1, 5))

    ax.set_title(f"Inter-Beat Intervals – {label} ({loc})", fontweight="bold")
    ax.set_xlabel("Time in segment [s]")
    ax.set_ylabel("IBI [ms]")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(fontsize=8)

    fig.tight_layout()
    save_fig(fig, output_dir, "ibi")
def plot_waveform(segment_results, segment_name, location, output_dir):
    label = segment_label(segment_name)
    loc = location_label(location)
    maneuver = not is_rest_segment(segment_name)

    fig, axs = plt.subplots(2, 1, figsize=(8, 4.8), sharex=True)

    plot_order = [
        ("mmwave", "mmWave", "Displacement [mm]", "#1f77b4"),
        ("finger", "Finger Pressure", "Pressure [mmHg]", "#ff7f0e"),
    ]

    for ax, (key, title, ylabel, color) in zip(axs, plot_order):
        res = segment_results[key]

        if res is None:
            continue

        t = res["t"]
        y = res["signal"]
        valleys = res["diastolic_valleys"]

        x = t - t[0]

        ax.plot(
            x,
            y,
            linewidth=1.5,
            color=color,
        )

        valley_times = t[valleys] - t[0]

        for vt in valley_times:
            ax.axvline(
                vt,
                linestyle="--",
                linewidth=0.8,
                alpha=0.5,
                color="#6baed6",
            )

        if maneuver:
            add_maneuver_shading(ax, total_duration_s=SEGMENT_DURATION_S)

        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_ylabel(ylabel)
        ax.grid(True, linestyle=":", alpha=0.6)

    fig.suptitle(f"Waveform Comparison – {label} ({loc})", fontweight="bold")
    axs[-1].set_xlabel("Time [s]")

    for ax in axs:
        ax.set_xlim(0, SEGMENT_DURATION_S)
        ax.set_xticks(np.arange(0, SEGMENT_DURATION_S + 0.1, 5))

    fig.tight_layout()
    save_fig(fig, output_dir, "waveform")
def plot_average_waveform(segment_results, segment_name, location, output_dir):
    label = segment_label(segment_name)
    loc = location_label(location)

    fig, ax = plt.subplots(figsize=(6.5, 4))

    x_norm = np.linspace(0, 1, POINTS_PER_BEAT)

    styles = {
        "mmwave": {
            "label": "mmWave",
            "linestyle": "-",
            "linewidth": 2.0,
        },
        "finger": {
            "label": "Finger Pressure",
            "linestyle": "--",
            "linewidth": 2.0,
        },
    }

    for key in ["mmwave", "finger"]:
        res = segment_results[key]

        if res is None or res["average_pulse"] is None:
            continue

        mean = res["average_pulse"]
        std = res["std_pulse"]

        ax.plot(
            x_norm,
            mean,
            linestyle=styles[key]["linestyle"],
            linewidth=styles[key]["linewidth"],
            label=styles[key]["label"],
        )

        ax.fill_between(
            x_norm,
            mean - std,
            mean + std,
            alpha=0.15,
        )

    ax.set_title(
        f"Average Normalized Pulse Waveform – {label} ({loc})",
        fontweight="bold",
    )
    ax.set_xlabel("Normalized Time")
    ax.set_ylabel("Normalized Amplitude")
    ax.grid(True, linestyle=":", alpha=0.6)
    ax.legend(fontsize=8)

    fig.tight_layout()
    save_fig(fig, output_dir, "average_waveform")

def make_all_plots(results, location):
    base_time = results["mmwave"]["t"][0] + 25 +25

    for n, segment_name in enumerate(segment_names):
        start_s = base_time + SEGMENT_SPACING_S * n
        end_s = start_s + SEGMENT_DURATION_S

        output_dir = os.path.join(OUTPUT_ROOT, location, segment_name)
        ensure_dir(output_dir)

        print("\n==============================")
        print(f"{location}/{segment_name}")
        print(segment_label(segment_name))
        print(f"{start_s:.2f} s to {end_s:.2f} s")
        print("==============================")

        segment_results = {
            "finger": crop_result(results["finger"], start_s, end_s),
            "mmwave": crop_result(results["mmwave"], start_s, end_s),
        }

        # For IBI only: use a slightly larger window.
        # This avoids missing edge beats, but the plot still displays only 0...20 s.
        segment_results_ibi = {
            "finger": crop_result(results["finger"], start_s - IBI_CONTEXT_S, end_s + IBI_CONTEXT_S),
            "mmwave": crop_result(results["mmwave"], start_s - IBI_CONTEXT_S, end_s + IBI_CONTEXT_S),
        }

        plot_ibi(
            segment_results_ibi,
            segment_name,
            location,
            output_dir,
            segment_start_s=start_s,
            segment_end_s=end_s,
        )

        plot_waveform(
            segment_results,
            segment_name,
            location,
            output_dir,
        )

        if is_rest_segment(segment_name):
            plot_average_waveform(
                segment_results,
                segment_name,
                location,
                output_dir,
            )


def _result_from_npz(prefix, data):
    """Reconstruct one processed signal result from an npz cache file."""

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


def load_preprocessed_cache(cache_path):
    """Load cached finger and mmWave preprocessing results."""

    if not os.path.exists(cache_path):
        raise FileNotFoundError(
            f"Preprocessed cache not found:\n{cache_path}\n\n"
            "Run the preprocessing script first."
        )

    print("Loading preprocessed cache:", cache_path)

    data = np.load(cache_path, allow_pickle=False)

    results = {
        "finger": _result_from_npz("finger", data),
        "mmwave": _result_from_npz("mmwave", data),
    }

    extra = {
        "time_scale": float(data["time_scale"]),
        "time_offset_s": float(data["time_offset_s"]),
        "best_bin": int(data["best_bin"]),
        "best_snr_db": float(data["best_snr_db"]),
    }

    return results, extra



results, extra = load_preprocessed_cache(PREPROCESSED_CACHE_PATH)

print("Loaded cache:")
print("  best_bin:", extra["best_bin"])
print("  best_snr_db:", extra["best_snr_db"])

make_all_plots(
    results=results,
    location=LOCATION_KEY,
)