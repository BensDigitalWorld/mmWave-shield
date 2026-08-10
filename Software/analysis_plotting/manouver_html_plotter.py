# -----------------------------------------------------------------------------
#
# File: manouver_html_plotter.py
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

import plotly.graph_objects as go
from plotly.subplots import make_subplots

'''
# ============================================================
# CONFIG WRIST
# ============================================================

PREPROCESSED_CACHE_PATH = os.path.join(
    "data",
    "processed",
    "wrist",
    "preprocessed_maneuver_series.npz"
)

OUTPUT_FOLDER = os.path.join("plots", "html")
OUTPUT_HTML_PATH = os.path.join(
    OUTPUT_FOLDER,
    "finapres_mmwave_wrist_comparison.html"
)

MAX_POINTS_PER_SIGNAL = 3_000_000
'''

# ============================================================
# CONFIG TEMPLE
# ============================================================

PREPROCESSED_CACHE_PATH = os.path.join(
    "data",
    "processed",
    "temple",
    "preprocessed_maneuver_series.npz"
)

OUTPUT_FOLDER = os.path.join("plots", "html")
OUTPUT_HTML_PATH = os.path.join(
    OUTPUT_FOLDER,
    "finapres_mmwave_temple_comparison.html"
)

MAX_POINTS_PER_SIGNAL = 3_000_000


# ============================================================
# HELPERS
# ============================================================

def normalize_for_overlay(x):
    return (x - np.nanmean(x)) / (np.nanstd(x) + 1e-12)


def downsample_for_plot(t, y, max_points=150_000):
    if len(y) <= max_points:
        return t, y

    stride = int(np.ceil(len(y) / max_points))
    return t[::stride], y[::stride]


def _result_from_npz(prefix, data):
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
    print("Loading preprocessed cache:", cache_path)

    data = np.load(cache_path, allow_pickle=False)

    required_keys = [
        "t_marker",
        "marker",
        "t_mmwave_sync",
        "mmwave_sync",
    ]

    missing_keys = [key for key in required_keys if key not in data.files]

    if len(missing_keys) > 0:
        raise KeyError(
            "Cache is missing keys: "
            + ", ".join(missing_keys)
            + "\nRun the preprocessing script once with "
            + "FORCE_REPROCESS_PREPROCESSED = True."
        )

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

        "t_marker": data["t_marker"],
        "marker": data["marker"],
        "t_mmwave_sync": data["t_mmwave_sync"],
        "mmwave_sync": data["mmwave_sync"],
    }

    return results, protocol_intervals, extra


# ============================================================
# LOAD CACHED DATA
# ============================================================

results, protocol_intervals, extra = load_preprocessed_cache(
    PREPROCESSED_CACHE_PATH
)

finger_result = results["finger"]
mmwave_result = results["mmwave"]

time_scale = extra["time_scale"]
time_offset_s = extra["time_offset_s"]
best_bin = extra["best_bin"]
best_snr_db = extra["best_snr_db"]


# ============================================================
# PREPARE PLOT SIGNALS
# ============================================================

t_finger = finger_result["t"]
finger = finger_result["signal"]

t_mmwave = mmwave_result["t"]
mmwave_signal = mmwave_result["signal"]

t_marker = extra["t_marker"]
marker = extra["marker"]

t_mmwave_sync = extra["t_mmwave_sync"]
mmwave_sync = extra["mmwave_sync"]

finger_plot = normalize_for_overlay(finger)
mmwave_plot = normalize_for_overlay(mmwave_signal)
marker_plot = normalize_for_overlay(marker)
mmwave_sync_plot = normalize_for_overlay(mmwave_sync)

t_finger_p, finger_p = downsample_for_plot(
    t_finger,
    finger_plot,
    MAX_POINTS_PER_SIGNAL
)

t_mmwave_p, mmwave_p = downsample_for_plot(
    t_mmwave,
    mmwave_plot,
    MAX_POINTS_PER_SIGNAL
)

t_marker_p, marker_p = downsample_for_plot(
    t_marker,
    marker_plot,
    MAX_POINTS_PER_SIGNAL
)

t_mmwave_sync_p, mmwave_sync_p = downsample_for_plot(
    t_mmwave_sync,
    mmwave_sync_plot,
    MAX_POINTS_PER_SIGNAL
)


# ============================================================
# INTERACTIVE PLOTLY VIEWER
# ============================================================

fig = make_subplots(
    rows=3,
    cols=1,
    shared_xaxes=True,
    vertical_spacing=0.06,
    row_heights=[0.55, 0.20, 0.25],
    subplot_titles=[
        "Pulse waveform comparison",
        "Finapres marker",
        "mmWave sync",
    ],
)

# Row 1: Pulse signals
fig.add_trace(
    go.Scattergl(
        x=t_finger_p,
        y=finger_p,
        mode="lines",
        name="Finapres finger pressure",
        line=dict(width=1),
    ),
    row=1,
    col=1,
)

fig.add_trace(
    go.Scattergl(
        x=t_mmwave_p,
        y=mmwave_p,
        mode="lines",
        name=f"mmWave radar, bin {best_bin}",
        line=dict(width=1),
    ),
    row=1,
    col=1,
)

# Row 2: Finapres marker
fig.add_trace(
    go.Scattergl(
        x=t_marker_p,
        y=marker_p,
        mode="lines",
        name="Finapres marker",
        line=dict(width=1),
    ),
    row=2,
    col=1,
)

# Row 3: mmWave sync
fig.add_trace(
    go.Scattergl(
        x=t_mmwave_sync_p,
        y=mmwave_sync_p,
        mode="lines",
        name="mmWave sync",
        line=dict(width=1),
    ),
    row=3,
    col=1,
)

fig.update_yaxes(title_text="Normalized", row=1, col=1)
fig.update_yaxes(title_text="Normalized", row=2, col=1)
fig.update_yaxes(title_text="Normalized", row=3, col=1)

fig.update_xaxes(
    title_text="Time [s]",
    row=3,
    col=1,
    rangeslider=dict(visible=True),
)

fig.update_layout(
    title=(
        "Finapres / NovaScope vs mmWave comparison "
        f"| selected bin = {best_bin} "
        f"| bin SNR = {best_snr_db:.1f} dB"
    ),
    height=700,
    width=1400,
    hovermode="x unified",
    legend=dict(
        orientation="h",
        yanchor="bottom",
        y=-0.18,
        xanchor="left",
        x=0,
    ),
)


# ============================================================
# ADD PROTOCOL MARKERS TO PLOT
# ============================================================

event_colors = {
    "Rest": "rgba(180, 180, 180, 0.12)",
    "Hand Grip": "rgba(255, 165, 0, 0.18)",
    "Cold Pressor": "rgba(0, 120, 255, 0.16)",
    "Valsalva": "rgba(180, 0, 180, 0.16)",
    "Stand Up": "rgba(0, 180, 80, 0.16)",
}

for interval in protocol_intervals:
    label = interval["label"]

    # Protocol times are stored relative to the mmWave recording.
    # Convert them to the global Finapres/NovaScope time axis.
    x0 = interval["start_mmwave"] * time_scale + time_offset_s
    x1 = interval["end_mmwave"] * time_scale + time_offset_s

    fig.add_vrect(
        x0=x0,
        x1=x1,
        fillcolor=event_colors.get(label, "rgba(150, 150, 150, 0.12)"),
        opacity=1.0,
        layer="below",
        line_width=0,
        annotation_text=label if label != "Rest" else "",
        annotation_position="top left",
    )

    fig.add_vline(
        x=x0,
        line_width=0.8,
        line_dash="dot",
        line_color="rgba(80, 80, 80, 0.5)",
    )


# ============================================================
# SAVE
# ============================================================

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

fig.write_html(
    OUTPUT_HTML_PATH,
    auto_open=True,
)

print("Saved HTML viewer:", OUTPUT_HTML_PATH)
