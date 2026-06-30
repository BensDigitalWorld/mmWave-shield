# -----------------------------------------------------------------------------
#
# File: power_analysis.py
#
# Last edited: 23.06.2025
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
import re
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


# ============================================================
# CONFIG
# ============================================================

POWER_LOG_DIR = os.path.join("data", "power_measurments", "powerLogs")

FOLDER_BASE = os.path.join(POWER_LOG_DIR, "Baseboard")
FOLDER_3V3  = os.path.join(POWER_LOG_DIR, "shield3_3")
FOLDER_1V8  = os.path.join(POWER_LOG_DIR, "shield1_8")

V_BASE = 4
V_3V3 = 3.3
V_1V8 = 1.8

SETTLING_TIME_S = 5.0
TOTAL_TIME_S = 35.0
EVAL_TIME_S = TOTAL_TIME_S - SETTLING_TIME_S

OUTPUT_FOLDER_NAME = "power_analysis_output"
OUTPUT_FOLDER = os.path.join("plots", OUTPUT_FOLDER_NAME)

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ============================================================
# FILENAME PARSING
# ============================================================

def parse_filename(filename):
    """
    Supports:
        31_100_1.csv  -> tx_power=31, fps=100, repetition=1
        off_1.csv
        on_1.csv
        conf_1.csv
    """
    name = os.path.basename(filename)

    m = re.match(r"^(\d+)_(\d+)_(\d+)\.csv$", name)
    if m:
        tx_power = int(m.group(1))
        fps = int(m.group(2))
        repetition = int(m.group(3))

        return {
            "state": "streaming",
            "tx_power": tx_power,
            "fps": fps,
            "repetition": repetition,
            "test_name": f"tx{tx_power}_fps{fps}",
        }

    m = re.match(r"^(off|on|conf)_(\d+)\.csv$", name)
    if m:
        state_raw = m.group(1)
        repetition = int(m.group(2))

        state_map = {
            "off": "mmwave_off",
            "on": "mmwave_on_not_configured",
            "conf": "mmwave_configured_not_streaming",
        }

        state = state_map[state_raw]

        return {
            "state": state,
            "tx_power": np.nan,
            "fps": np.nan,
            "repetition": repetition,
            "test_name": state,
        }

    return None


# ============================================================
# CSV HELPERS
# ============================================================

def get_header_info(path):
    """
    Reads:
        Timestamp(ms),Current(uA)

    Also reads the first two data rows to estimate dt.
    """
    with open(path, "r") as f:
        header = f.readline().strip()
        row1 = f.readline().strip()
        row2 = f.readline().strip()

    m_current = re.search(r"Current\((.*?)\)", header)
    if not m_current:
        raise ValueError(f"Could not detect current unit from header: {header}")

    current_unit = m_current.group(1).strip()

    scale_map = {
        "nA": 1e-9,
        "uA": 1e-6,
        "µA": 1e-6,
        "mA": 1e-3,
        "A": 1.0,
    }

    if current_unit not in scale_map:
        raise ValueError(f"Unknown current unit: {current_unit}")

    current_scale_to_A = scale_map[current_unit]

    t1_ms = float(row1.split(",")[0])
    t2_ms = float(row2.split(",")[0])
    dt_ms = t2_ms - t1_ms

    if dt_ms <= 0:
        raise ValueError(f"Invalid timestamp step in file: {path}")

    return current_unit, current_scale_to_A, dt_ms


def analyze_file_fast(path, voltage):
    current_unit, scale_to_A, dt_ms = get_header_info(path)

    settling_rows = int((SETTLING_TIME_S * 1000.0) / dt_ms)

    # skip header + settling rows
    skiprows = 1 + settling_rows

    # Read only current column
    current_raw = np.loadtxt(
        path,
        delimiter=",",
        skiprows=skiprows,
        usecols=1,
        dtype=np.float32,
    )

    current_A = current_raw * scale_to_A
    power_W = current_A * voltage

    return {
        "current_unit_original": current_unit,
        "dt_ms": dt_ms,
        "samples_used": len(current_A),
        "duration_s": len(current_A) * dt_ms / 1000.0,

        "mean_current_A": float(np.mean(current_A)),
        "std_current_A": float(np.std(current_A, ddof=1)),
        "min_current_A": float(np.min(current_A)),
        "max_current_A": float(np.max(current_A)),

        "mean_power_W": float(np.mean(power_W)),
        "std_power_W": float(np.std(power_W, ddof=1)),
        "min_power_W": float(np.min(power_W)),
        "max_power_W": float(np.max(power_W)),
    }


def analyze_folder(folder, rail_name, voltage):
    rows = []

    for filename in sorted(os.listdir(folder)):
        if not filename.endswith(".csv"):
            continue

        parsed = parse_filename(filename)
        if parsed is None:
            print(f"Skipping unknown filename format: {filename}")
            continue

        path = os.path.join(folder, filename)
        print(f"Analyzing {rail_name}: {filename}")

        stats = analyze_file_fast(path, voltage)

        row = {
            "rail": rail_name,
            "filename": filename,
            **parsed,
            **stats,
        }

        rows.append(row)

    return pd.DataFrame(rows)


# ============================================================
# LOAD DATA
# ============================================================

df_base = analyze_folder(FOLDER_BASE, "base", V_BASE)
df_3v3 = analyze_folder(FOLDER_3V3, "3v3", V_3V3)
df_1v8 = analyze_folder(FOLDER_1V8, "1v8", V_1V8)

for df in [df_base, df_3v3, df_1v8]:
    df["mean_current_mA"] = df["mean_current_A"] * 1000.0
    df["std_current_mA"] = df["std_current_A"] * 1000.0
    df["mean_power_mW"] = df["mean_power_W"] * 1000.0
    df["std_power_mW"] = df["std_power_W"] * 1000.0

all_rails = pd.concat([df_base, df_3v3, df_1v8], ignore_index=True)

all_rails["mean_current_mA"] = all_rails["mean_current_A"] * 1000.0
all_rails["std_current_mA"] = all_rails["std_current_A"] * 1000.0
all_rails["mean_power_mW"] = all_rails["mean_power_W"] * 1000.0
all_rails["std_power_mW"] = all_rails["std_power_W"] * 1000.0

all_rails.to_csv(
    os.path.join(OUTPUT_FOLDER, "all_rail_file_statistics.csv"),
    index=False,
)


# ============================================================
# COMBINE 3V3 + 1V8 TO SHIELD TOTAL
# ============================================================

key_cols = ["state", "tx_power", "fps", "repetition", "test_name"]

df_3v3_small = df_3v3[key_cols + ["mean_power_W", "std_power_W"]].copy()
df_1v8_small = df_1v8[key_cols + ["mean_power_W", "std_power_W"]].copy()

shield = pd.merge(
    df_3v3_small,
    df_1v8_small,
    on=key_cols,
    suffixes=("_3v3", "_1v8"),
)

shield["mean_power_W_shield"] = (
    shield["mean_power_W_3v3"] + shield["mean_power_W_1v8"]
)

shield["std_power_W_shield_est"] = np.sqrt(
    shield["std_power_W_3v3"] ** 2 + shield["std_power_W_1v8"] ** 2
)

shield["mean_power_mW_shield"] = shield["mean_power_W_shield"] * 1000.0
shield["std_power_mW_shield_est"] = shield["std_power_W_shield_est"] * 1000.0

shield.to_csv(
    os.path.join(OUTPUT_FOLDER, "shield_file_statistics.csv"),
    index=False,
)


# ============================================================
# GROUP REPETITIONS
# ============================================================

shield_summary = shield.groupby(
    ["state", "tx_power", "fps", "test_name"],
    dropna=False,
).agg(
    shield_power_mW_mean=("mean_power_mW_shield", "mean"),
    shield_power_mW_std=("mean_power_mW_shield", "std"),
    shield_power_mW_min=("mean_power_mW_shield", "min"),
    shield_power_mW_max=("mean_power_mW_shield", "max"),
    repetitions=("mean_power_mW_shield", "count"),
).reset_index()

shield_summary.to_csv(
    os.path.join(OUTPUT_FOLDER, "shield_summary.csv"),
    index=False,
)


base_summary = df_base.groupby(
    ["state", "tx_power", "fps", "test_name"],
    dropna=False,
).agg(
    base_power_mW_mean=("mean_power_mW", "mean"),
    base_power_mW_std=("mean_power_mW", "std"),
    base_power_mW_min=("mean_power_mW", "min"),
    base_power_mW_max=("mean_power_mW", "max"),
    repetitions=("mean_power_mW", "count"),
).reset_index()

base_summary.to_csv(
    os.path.join(OUTPUT_FOLDER, "base_summary.csv"),
    index=False,
)


# ============================================================
# PLOTS
# ============================================================

PLOT_DPI = 300

STATE_LABELS = {
    "mmwave_off": "Off",
    "mmwave_on_not_configured": "On\nnot configured",
    "mmwave_configured_not_streaming": "Configured\nnot streaming",
}

baseline_order = [
    "mmwave_off",
    "mmwave_on_not_configured",
    "mmwave_configured_not_streaming",
]


def save_plot(filename):
    path = os.path.join(OUTPUT_FOLDER, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=PLOT_DPI)
    plt.show()


def format_mw(value):
    if abs(value) < 0.1:
        return f"{value:.3f}"
    elif abs(value) < 10:
        return f"{value:.2f}"
    else:
        return f"{value:.1f}"


def add_bar_value_labels(ax, bars, values=None, unit="mW", y_offset_frac=0.025):
    if values is None:
        values = [bar.get_height() for bar in bars]

    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    y_offset = y_range * y_offset_frac

    for bar, value in zip(bars, values):
        height = bar.get_height()
        x = bar.get_x() + bar.get_width() / 2.0

        label = f"{format_mw(value)} {unit}"

        if height > 0.18 * y_max:
            y = height * 0.5
            va = "center"
        else:
            y = height + y_offset
            va = "bottom"

        ax.text(
            x,
            y,
            label,
            ha="center",
            va=va,
            fontsize=9,
        )


def set_y_axis_from_zero(ax, values, errors=None, headroom=1.20):
    values = np.asarray(values, dtype=float)

    if errors is not None:
        errors = np.nan_to_num(np.asarray(errors, dtype=float), nan=0.0)
        y_max = np.nanmax(values + errors)
    else:
        y_max = np.nanmax(values)

    if y_max <= 0:
        y_max = 1.0

    ax.set_ylim(0, y_max * headroom)


def add_stacked_total_labels(ax, x_positions, totals, unit="mW", y_offset_frac=0.025):
    y_min, y_max = ax.get_ylim()
    y_range = y_max - y_min
    y_offset = y_range * y_offset_frac

    for x, total in zip(x_positions, totals):
        ax.text(
            x,
            total + y_offset,
            f"{format_mw(total)} {unit}",
            ha="center",
            va="bottom",
            fontsize=9,
        )


# ------------------------------------------------------------
# 1. Shield baseline states
# ------------------------------------------------------------

baseline = shield_summary[
    shield_summary["state"].isin(baseline_order)
].copy()

if len(baseline) > 0:
    baseline["state"] = pd.Categorical(
        baseline["state"],
        categories=baseline_order,
        ordered=True,
    )
    baseline = baseline.sort_values("state")

    labels = [STATE_LABELS[state] for state in baseline["state"].astype(str)]
    values = baseline["shield_power_mW_mean"].to_numpy()
    errors = baseline["shield_power_mW_std"].fillna(0).to_numpy()

    fig, ax = plt.subplots(figsize=(7, 4))

    bars = ax.bar(
        labels,
        values,
        yerr=errors,
        capsize=4,
    )

    set_y_axis_from_zero(ax, values, errors, headroom=1.25)
    add_bar_value_labels(ax, bars, values)

    ax.set_ylabel("Shield power [mW]")
    #ax.set_title("mmWave shield baseline power states")
    ax.grid(True, axis="y", linestyle=":")

    save_plot("shield_baseline_states.png")


# ------------------------------------------------------------
# 2. Whole/base reference states
# ------------------------------------------------------------

base_baseline = base_summary[
    base_summary["state"].isin(baseline_order)
].copy()

if len(base_baseline) > 0:
    base_baseline["state"] = pd.Categorical(
        base_baseline["state"],
        categories=baseline_order,
        ordered=True,
    )
    base_baseline = base_baseline.sort_values("state")

    labels = [STATE_LABELS[state] for state in base_baseline["state"].astype(str)]
    values = base_baseline["base_power_mW_mean"].to_numpy()
    errors = base_baseline["base_power_mW_std"].fillna(0).to_numpy()

    fig, ax = plt.subplots(figsize=(7, 4))

    bars = ax.bar(
        labels,
        values,
        yerr=errors,
        capsize=4,
    )

    set_y_axis_from_zero(ax, values, errors, headroom=1.25)
    add_bar_value_labels(ax, bars, values)

    ax.set_ylabel("Base / whole-system power [mW]")
    #ax.set_title("Base / whole-system reference power states")
    ax.grid(True, axis="y", linestyle=":")

    save_plot("base_reference_states.png")



# ------------------------------------------------------------
# 3. Combined baseline states: mmWave shield + whole system
# ------------------------------------------------------------

baseline_compare = pd.merge(
    shield_summary[
        shield_summary["state"].isin(baseline_order)
    ][["state", "shield_power_mW_mean", "shield_power_mW_std"]],
    base_summary[
        base_summary["state"].isin(baseline_order)
    ][["state", "base_power_mW_mean", "base_power_mW_std"]],
    on="state",
    how="inner",
)

if len(baseline_compare) > 0:
    baseline_compare["state"] = pd.Categorical(
        baseline_compare["state"],
        categories=baseline_order,
        ordered=True,
    )
    baseline_compare = baseline_compare.sort_values("state")

    labels = [STATE_LABELS[state] for state in baseline_compare["state"].astype(str)]
    x_pos = np.arange(len(baseline_compare))

    mmwave_y = baseline_compare["shield_power_mW_mean"].to_numpy(dtype=float)
    mmwave_err = baseline_compare["shield_power_mW_std"].fillna(0).to_numpy(dtype=float)

    whole_y = baseline_compare["base_power_mW_mean"].to_numpy(dtype=float)
    whole_err = baseline_compare["base_power_mW_std"].fillna(0).to_numpy(dtype=float)

    # --------------------------------------------------------
    # 3a. One column per state
    #     The orange part is the remaining whole-system power.
    #     This keeps the total bar height equal to the whole system.
    # --------------------------------------------------------

    rest_y = whole_y - mmwave_y

    if np.any(rest_y < 0):
        print(
            "Warning: Shield power is larger than whole-system power for at least one state. "
            "Clipping the stacked remainder to 0 for plotting."
        )
        rest_y = np.clip(rest_y, 0.0, None)

    fig, ax = plt.subplots(figsize=(7, 4))

    bars_mmwave = ax.bar(
        x_pos,
        mmwave_y,
        color="tab:blue",
        label="mmWave shield",
    )

    bars_rest = ax.bar(
        x_pos,
        rest_y,
        bottom=mmwave_y,
        color="tab:orange",
        label="Whole system remainder",
    )

    # Error bar shows the measured whole-system uncertainty on the total height
    ax.errorbar(
        x_pos,
        whole_y,
        yerr=whole_err,
        fmt="none",
        ecolor="black",
        capsize=4,
        linewidth=1,
    )

    set_y_axis_from_zero(ax, whole_y, whole_err, headroom=1.25)

    # Label mmWave part if it is large enough to read cleanly
    y_min, y_max = ax.get_ylim()
    for x_i, value_i in zip(x_pos, mmwave_y):
        if value_i > 0.08 * y_max:
            ax.text(
                x_i,
                value_i / 2.0,
                f"{format_mw(value_i)}",
                ha="center",
                va="center",
                fontsize=9,
            )

    add_stacked_total_labels(ax, x_pos, whole_y)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Power [mW]")
    ax.grid(True, axis="y", linestyle=":")
    ax.legend()

    save_plot("combined_baseline_states_stacked.png")

    # --------------------------------------------------------
    # 3b. Two columns per state
    # --------------------------------------------------------

    fig, ax = plt.subplots(figsize=(7, 4))

    width = 0.36

    bars_mmwave = ax.bar(
        x_pos - width / 2.0,
        mmwave_y,
        width=width,
        yerr=mmwave_err,
        capsize=4,
        color="tab:blue",
        label="mmWave shield",
    )

    bars_whole = ax.bar(
        x_pos + width / 2.0,
        whole_y,
        width=width,
        yerr=whole_err,
        capsize=4,
        color="tab:orange",
        label="Whole system",
    )

    set_y_axis_from_zero(
        ax,
        np.concatenate([mmwave_y, whole_y]),
        np.concatenate([mmwave_err, whole_err]),
        headroom=1.25,
    )

    add_bar_value_labels(ax, bars_mmwave, mmwave_y)
    add_bar_value_labels(ax, bars_whole, whole_y)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Power [mW]")
    ax.grid(True, axis="y", linestyle=":")
    ax.legend()

    save_plot("combined_baseline_states_grouped.png")


# ------------------------------------------------------------
# 3. Shield power vs FPS at TX=31 + linear fit
# ------------------------------------------------------------

fps_sweep = shield_summary[
    (shield_summary["state"] == "streaming") &
    (shield_summary["tx_power"] == 31)
].copy()

fps_sweep = fps_sweep.sort_values("fps")

if len(fps_sweep) > 0:
    x = fps_sweep["fps"].to_numpy(dtype=float)
    y = fps_sweep["shield_power_mW_mean"].to_numpy(dtype=float)
    yerr = fps_sweep["shield_power_mW_std"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        y,
        yerr=yerr,
        marker="o",
        capsize=4,
        linestyle="none",
        label="Shield measured",
    )

    if len(x) >= 2:
        coef = np.polyfit(x, y, 1)
        fit = np.poly1d(coef)
        ax.plot(
            x,
            fit(x),
            "--",
            label=f"Linear fit: {coef[0]:.3f} mW/FPS",
        )

    set_y_axis_from_zero(ax, y, yerr, headroom=1.15)

    ax.set_xlabel("Frame rate [FPS]")
    ax.set_ylabel("Shield power [mW]")
    #ax.set_title("Shield power vs frame rate, TX power = 31")
    ax.grid(True, linestyle=":")
    ax.legend()

    save_plot("shield_power_vs_fps_tx31.png")


# ------------------------------------------------------------
# 4. Whole/base power vs FPS at TX=31
# ------------------------------------------------------------

base_fps_sweep = base_summary[
    (base_summary["state"] == "streaming") &
    (base_summary["tx_power"] == 31)
].copy()

base_fps_sweep = base_fps_sweep.sort_values("fps")

if len(base_fps_sweep) > 0:
    x = base_fps_sweep["fps"].to_numpy(dtype=float)
    y = base_fps_sweep["base_power_mW_mean"].to_numpy(dtype=float)
    yerr = base_fps_sweep["base_power_mW_std"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        y,
        yerr=yerr,
        marker="o",
        capsize=4,
        linestyle="none",
        label="Whole system measured",
    )

    if len(x) >= 2:
        coef = np.polyfit(x, y, 1)
        fit = np.poly1d(coef)
        ax.plot(
            x,
            fit(x),
            "--",
            label=f"Linear fit: {coef[0]:.3f} mW/FPS",
        )

    set_y_axis_from_zero(ax, y, yerr, headroom=1.15)

    ax.set_xlabel("Frame rate [FPS]")
    ax.set_ylabel("Whole-system power [mW]")
    #ax.set_title("Whole-system power vs frame rate, TX power = 31")
    ax.grid(True, linestyle=":")
    ax.legend()

    save_plot("base_power_vs_fps_tx31.png")


# ------------------------------------------------------------
# 5. Comparison: Shield vs Whole system, FPS sweep at TX=31
# ------------------------------------------------------------

fps_compare = pd.merge(
    fps_sweep[["fps", "shield_power_mW_mean", "shield_power_mW_std"]],
    base_fps_sweep[["fps", "base_power_mW_mean", "base_power_mW_std"]],
    on="fps",
    how="inner",
)

fps_compare = fps_compare.sort_values("fps")

if len(fps_compare) > 0:
    x = fps_compare["fps"].to_numpy(dtype=float)

    shield_y = fps_compare["shield_power_mW_mean"].to_numpy(dtype=float)
    shield_err = fps_compare["shield_power_mW_std"].fillna(0).to_numpy(dtype=float)

    base_y = fps_compare["base_power_mW_mean"].to_numpy(dtype=float)
    base_err = fps_compare["base_power_mW_std"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        shield_y,
        yerr=shield_err,
        marker="o",
        capsize=4,
        label="Shield",
    )

    ax.errorbar(
        x,
        base_y,
        yerr=base_err,
        marker="s",
        capsize=4,
        label="Whole system",
    )

    set_y_axis_from_zero(
        ax,
        np.concatenate([shield_y, base_y]),
        np.concatenate([shield_err, base_err]),
        headroom=1.15,
    )

    ax.set_xlabel("Frame rate [FPS]")
    ax.set_ylabel("Power [mW]")
    #ax.set_title("Shield vs whole-system power vs frame rate, TX power = 31")
    ax.grid(True, linestyle=":")
    ax.legend()

    save_plot("comparison_power_vs_fps_tx31.png")


# ------------------------------------------------------------
# 6. Shield power vs TX power at FPS=100, absolute scale
# ------------------------------------------------------------

tx_sweep = shield_summary[
    (shield_summary["state"] == "streaming") &
    (shield_summary["fps"] == 100)
].copy()

tx_sweep = tx_sweep.sort_values("tx_power")

if len(tx_sweep) > 0:
    x = tx_sweep["tx_power"].to_numpy(dtype=float)
    y = tx_sweep["shield_power_mW_mean"].to_numpy(dtype=float)
    yerr = tx_sweep["shield_power_mW_std"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        y,
        yerr=yerr,
        marker="o",
        capsize=4,
        label="Shield",
    )

    set_y_axis_from_zero(ax, y, yerr, headroom=1.15)

    ax.set_xlabel("TX power level")
    ax.set_ylabel("Shield power [mW]")
    #ax.set_title("Shield power vs TX power, FPS = 100")
    ax.grid(True, linestyle=":")
    ax.legend()

    save_plot("shield_power_vs_tx_fps100_absolute.png")


# ------------------------------------------------------------
# 7. Whole/base power vs TX power at FPS=100
# ------------------------------------------------------------

base_tx_sweep = base_summary[
    (base_summary["state"] == "streaming") &
    (base_summary["fps"] == 100)
].copy()

base_tx_sweep = base_tx_sweep.sort_values("tx_power")

if len(base_tx_sweep) > 0:
    x = base_tx_sweep["tx_power"].to_numpy(dtype=float)
    y = base_tx_sweep["base_power_mW_mean"].to_numpy(dtype=float)
    yerr = base_tx_sweep["base_power_mW_std"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        y,
        yerr=yerr,
        marker="o",
        capsize=4,
        label="Whole system",
    )

    set_y_axis_from_zero(ax, y, yerr, headroom=1.15)

    ax.set_xlabel("TX power level")
    ax.set_ylabel("Whole-system power [mW]")
    #ax.set_title("Whole-system power vs TX power, FPS = 100")
    ax.grid(True, linestyle=":")
    ax.legend()

    save_plot("base_power_vs_tx_fps100.png")


# ------------------------------------------------------------
# 8. Comparison: Shield vs Whole system, TX sweep at FPS=100
# ------------------------------------------------------------

tx_compare = pd.merge(
    tx_sweep[["tx_power", "shield_power_mW_mean", "shield_power_mW_std"]],
    base_tx_sweep[["tx_power", "base_power_mW_mean", "base_power_mW_std"]],
    on="tx_power",
    how="inner",
)

tx_compare = tx_compare.sort_values("tx_power")

if len(tx_compare) > 0:
    x = tx_compare["tx_power"].to_numpy(dtype=float)

    shield_y = tx_compare["shield_power_mW_mean"].to_numpy(dtype=float)
    shield_err = tx_compare["shield_power_mW_std"].fillna(0).to_numpy(dtype=float)

    base_y = tx_compare["base_power_mW_mean"].to_numpy(dtype=float)
    base_err = tx_compare["base_power_mW_std"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        shield_y,
        yerr=shield_err,
        marker="o",
        capsize=4,
        label="Shield",
    )

    ax.errorbar(
        x,
        base_y,
        yerr=base_err,
        marker="s",
        capsize=4,
        label="Whole system",
    )

    set_y_axis_from_zero(
        ax,
        np.concatenate([shield_y, base_y]),
        np.concatenate([shield_err, base_err]),
        headroom=1.15,
    )

    ax.set_xlabel("TX power level")
    ax.set_ylabel("Power [mW]")
    #ax.set_title("Shield vs whole-system power vs TX power, FPS = 100")
    ax.grid(True, linestyle=":")
    ax.legend()

    save_plot("comparison_power_vs_tx_fps100.png")


# ------------------------------------------------------------
# 9. Incremental shield power vs TX power at FPS=100
# ------------------------------------------------------------

if len(tx_sweep) > 0 and (tx_sweep["tx_power"] == 0).any():
    tx0_row = tx_sweep[tx_sweep["tx_power"] == 0].iloc[0]

    tx0_power = float(tx0_row["shield_power_mW_mean"])
    tx0_std = float(tx0_row["shield_power_mW_std"]) if not pd.isna(tx0_row["shield_power_mW_std"]) else 0.0

    tx_sweep_delta = tx_sweep.copy()
    tx_sweep_delta["delta_power_mW"] = (
        tx_sweep_delta["shield_power_mW_mean"] - tx0_power
    )

    tx_sweep_delta["delta_power_mW_std"] = np.sqrt(
        tx_sweep_delta["shield_power_mW_std"].fillna(0).to_numpy(dtype=float) ** 2
        + tx0_std ** 2
    )

    x = tx_sweep_delta["tx_power"].to_numpy(dtype=float)
    y = tx_sweep_delta["delta_power_mW"].to_numpy(dtype=float)
    yerr = tx_sweep_delta["delta_power_mW_std"].to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        y,
        yerr=yerr,
        marker="o",
        capsize=4,
    )

    y_max = max(np.nanmax(y + yerr), 0.1)
    y_min = min(np.nanmin(y - yerr), 0.0)

    ax.set_ylim(y_min - 0.05 * y_max, y_max * 1.25)

    ax.set_xlabel("TX power level")
    ax.set_ylabel("Additional shield power vs TX=0 [mW]")
    #ax.set_title("Incremental shield power vs TX power, FPS = 100")
    ax.grid(True, linestyle=":")

    save_plot("shield_delta_power_vs_tx_fps100.png")


# ------------------------------------------------------------
# 10. Rail breakdown vs FPS at TX=31
# ------------------------------------------------------------

rail_group = all_rails.groupby(
    ["rail", "state", "tx_power", "fps"],
    dropna=False,
).agg(
    mean_power_mW=("mean_power_mW", "mean"),
    std_power_mW=("mean_power_mW", "std"),
).reset_index()

rail_fps = rail_group[
    (rail_group["state"] == "streaming") &
    (rail_group["tx_power"] == 31) &
    (rail_group["rail"].isin(["3v3", "1v8"]))
].copy()

if len(rail_fps) > 0:
    pivot = rail_fps.pivot(
        index="fps",
        columns="rail",
        values="mean_power_mW",
    ).sort_index()

    fps_labels = [
        str(int(fps)) if float(fps).is_integer() else f"{fps:g}"
        for fps in pivot.index
    ]

    x_pos = np.arange(len(pivot))
    bottom = np.zeros(len(pivot))

    fig, ax = plt.subplots(figsize=(7, 4))

    for rail in ["1v8", "3v3"]:
        if rail in pivot.columns:
            values = pivot[rail].to_numpy(dtype=float)

            ax.bar(
                x_pos,
                values,
                bottom=bottom,
                label=rail,
            )

            for x_i, value_i, bottom_i in zip(x_pos, values, bottom):
                if value_i >= 0.8:
                    ax.text(
                        x_i,
                        bottom_i + value_i / 2.0,
                        f"{format_mw(value_i)}",
                        ha="center",
                        va="center",
                        fontsize=9,
                    )

            bottom += values

    totals = bottom.copy()

    ax.set_xticks(x_pos)
    ax.set_xticklabels(fps_labels)

    set_y_axis_from_zero(ax, totals, None, headroom=1.20)
    add_stacked_total_labels(ax, x_pos, totals)

    ax.set_xlabel("Frame rate [FPS]")
    ax.set_ylabel("Power [mW]")
    #ax.set_title("Shield rail power breakdown vs FPS, TX power = 31")
    ax.legend()
    ax.grid(True, axis="y", linestyle=":")

    save_plot("shield_rail_breakdown_vs_fps.png")


# ------------------------------------------------------------
# 11. 3.3 V rail alone vs FPS at TX=31
# ------------------------------------------------------------

rail_3v3_fps = rail_fps[rail_fps["rail"] == "3v3"].copy()
rail_3v3_fps = rail_3v3_fps.sort_values("fps")

if len(rail_3v3_fps) > 0:
    x = rail_3v3_fps["fps"].to_numpy(dtype=float)
    y = rail_3v3_fps["mean_power_mW"].to_numpy(dtype=float)
    yerr = rail_3v3_fps["std_power_mW"].fillna(0).to_numpy(dtype=float)

    fig, ax = plt.subplots(figsize=(7, 4))

    ax.errorbar(
        x,
        y,
        yerr=yerr,
        marker="o",
        capsize=4,
    )

    set_y_axis_from_zero(ax, y, yerr, headroom=1.25)

    ax.set_xlabel("Frame rate [FPS]")
    ax.set_ylabel("3.3 V rail power [mW]")
    #ax.set_title("3.3 V rail power vs FPS, TX power = 31")
    ax.grid(True, linestyle=":")

    save_plot("shield_3v3_power_vs_fps_tx31.png")


    # ------------------------------------------------------------
    # 12. 3.3 V and 1.8 V rails vs FPS at TX=31
    # ------------------------------------------------------------

    rail_fps_lines = rail_fps[
        rail_fps["rail"].isin(["3v3", "1v8"])
    ].copy()

    rail_fps_lines = rail_fps_lines.sort_values(["rail", "fps"])

    if len(rail_fps_lines) > 0:
        fig, ax = plt.subplots(figsize=(7, 4))

        for rail, marker, label in [
            ("3v3", "o", "3.3 V rail"),
            ("1v8", "s", "1.8 V rail"),
        ]:
            rail_data = rail_fps_lines[rail_fps_lines["rail"] == rail].copy()
            rail_data = rail_data.sort_values("fps")

            if len(rail_data) == 0:
                continue

            x = rail_data["fps"].to_numpy(dtype=float)
            y = rail_data["mean_power_mW"].to_numpy(dtype=float)
            yerr = rail_data["std_power_mW"].fillna(0).to_numpy(dtype=float)

            ax.errorbar(
                x,
                y,
                yerr=yerr,
                marker=marker,
                capsize=4,
                linewidth=1.5,
                label=label,
            )

        all_y = rail_fps_lines["mean_power_mW"].to_numpy(dtype=float)
        all_yerr = rail_fps_lines["std_power_mW"].fillna(0).to_numpy(dtype=float)

        set_y_axis_from_zero(
            ax,
            all_y,
            all_yerr,
            headroom=1.20,
        )

        ax.set_xlabel("Frame rate [FPS]")
        ax.set_ylabel("Rail power [mW]")
        #ax.set_title("3.3 V and 1.8 V rail power vs FPS, TX power = 31")
        ax.grid(True, linestyle=":")
        ax.legend()

        save_plot("shield_3v3_1v8_power_vs_fps_tx31.png")

    # ------------------------------------------------------------
    # 12. 1.8 V and 3.3 V rails vs FPS with separate y-axes
    # ------------------------------------------------------------

    rail_fps_dual = rail_fps[
        rail_fps["rail"].isin(["1v8", "3v3"])
    ].copy()

    if len(rail_fps_dual) > 0:
        rail_1v8 = rail_fps_dual[rail_fps_dual["rail"] == "1v8"].sort_values("fps")
        rail_3v3 = rail_fps_dual[rail_fps_dual["rail"] == "3v3"].sort_values("fps")

        fig, ax1 = plt.subplots(figsize=(7, 4))

        # 1.8 V rail on left axis (blue)
        if len(rail_1v8) > 0:
            x_1v8 = rail_1v8["fps"].to_numpy(dtype=float)
            y_1v8 = rail_1v8["mean_power_mW"].to_numpy(dtype=float)
            yerr_1v8 = rail_1v8["std_power_mW"].fillna(0).to_numpy(dtype=float)

            ax1.errorbar(
                x_1v8,
                y_1v8,
                yerr=yerr_1v8,
                marker="o",
                capsize=4,
                linewidth=1.5,
                color="tab:blue",
                label="1.8 V rail",
            )

            ax1.set_ylabel("1.8 V rail power [mW]", color="tab:blue")
            ax1.tick_params(axis="y", labelcolor="tab:blue")
            set_y_axis_from_zero(ax1, y_1v8, yerr_1v8, headroom=1.20)

        ax1.set_xlabel("Frame rate [FPS]")
        ax1.grid(True, linestyle=":")

        # 3.3 V rail on right axis (orange)
        ax2 = ax1.twinx()

        if len(rail_3v3) > 0:
            x_3v3 = rail_3v3["fps"].to_numpy(dtype=float)
            y_3v3 = rail_3v3["mean_power_mW"].to_numpy(dtype=float)
            yerr_3v3 = rail_3v3["std_power_mW"].fillna(0).to_numpy(dtype=float)

            ax2.errorbar(
                x_3v3,
                y_3v3,
                yerr=yerr_3v3,
                marker="s",
                capsize=4,
                linewidth=1.5,
                linestyle="--",
                color="tab:orange",
                label="3.3 V rail",
            )

            ax2.set_ylabel("3.3 V rail power [mW]", color="tab:orange")
            ax2.tick_params(axis="y", labelcolor="tab:orange")
            set_y_axis_from_zero(ax2, y_3v3, yerr_3v3, headroom=1.40)

        # Combined legend
        lines_1, labels_1 = ax1.get_legend_handles_labels()
        lines_2, labels_2 = ax2.get_legend_handles_labels()
        ax1.legend(lines_1 + lines_2, labels_1 + labels_2, loc="upper left")

        save_plot("shield_1v8_3v3_power_vs_fps_dual_axis.png")

print("Done.")
print(f"Results saved to: {OUTPUT_FOLDER}")