# -----------------------------------------------------------------------------
#
# File: live_waveform_viewer.py
#
# Last edited: 30.06.2025
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



import sys
import time
import numpy as np
from threading import Thread, Event, Lock

from scipy.signal import butter, filtfilt, find_peaks


from PyQt5 import QtWidgets, QtCore
import pyqtgraph as pg

from acquisition.bgt_com_class import BGT60SensorThreaded


# =========================
# Radar / dev board configuration
# =========================
PORT = "COM4"

LIVE_SMOOTHING_SECONDS = 0.08
RAW_CHIRP_INDEX = 0

VALID_GAIN_STAGES = [18, 23, 28, 30, 33, 35, 38, 40, 43, 45, 48, 50, 55, 60]
TX_POWER_LEVEL = 31
VALID_FPS_STAGES = [25, 50, 100, 150, 200]


ADC_BITS = 12
ADC_MAX_VALUE = (1 << ADC_BITS) - 1  # 4095
ADC_CLIP_MARGIN = 20                 # values <=20 or >=4075 count as near clipping

SAMPLES_PER_CHIRP = 8
CHIRPS_PER_FRAME = 32
FRAME_RATE = 100
DEFAULT_FPS = 100

NUM_RX_ANTENNAS = 1
ANTENNA_INDEX = 0

IF_GAIN_DB = 23

RANGE_BIN = 1

LIVE_WINDOW_SECONDS = 5
SUMMARY_SECONDS = 10
SUMMARY_TAIL_SKIP_SECONDS = 2

PHASE_BANDPASS_LOW_HZ = 0.7
PHASE_BANDPASS_HIGH_HZ = 4.0
PHASE_BANDPASS_ORDER = 2


def smooth_for_display(signal, fs=FRAME_RATE, smoothing_seconds=LIVE_SMOOTHING_SECONDS):
    signal = np.asarray(signal, dtype=float)

    window_size = max(1, int(fs * smoothing_seconds))

    if window_size < 2:
        return signal

    if window_size % 2 == 0:
        window_size += 1

    kernel = np.ones(window_size) / window_size
    return np.convolve(signal, kernel, mode="same")


def bandpass_filter(data, lowcut=PHASE_BANDPASS_LOW_HZ, highcut=PHASE_BANDPASS_HIGH_HZ,
                    fs=FRAME_RATE, order=PHASE_BANDPASS_ORDER):
    data = np.asarray(data, dtype=float)

    if len(data) < 4:
        return data.copy()

    nyquist = 0.5 * fs

    if highcut >= nyquist:
        highcut = 0.9 * nyquist

    low = lowcut / nyquist
    high = highcut / nyquist

    if low <= 0 or high >= 1 or low >= high:
        return data.copy()

    b, a = butter(order, [low, high], btype="band")

    padlen = 3 * max(len(a), len(b))

    if len(data) <= padlen:
        return data.copy()

    return filtfilt(b, a, data)


def extract_average_pulse_waveform(signal, fs, num_points=100):
    signal = np.asarray(signal, dtype=float)
    filtered = bandpass_filter(signal, fs=fs)

    min_peak_distance = max(1, int(0.4 * fs))
    prominence = max(1e-9, 0.2 * np.std(filtered))

    peaks, _ = find_peaks(filtered, distance=min_peak_distance, prominence=prominence)

    if len(peaks) < 3:
        peaks, _ = find_peaks(filtered, distance=min_peak_distance)

    if len(peaks) < 3:
        return None

    beats = []

    for i in range(len(peaks) - 1):
        start = peaks[i]
        end = peaks[i + 1]

        segment = filtered[start:end]

        if len(segment) < 4:
            continue

        x_old = np.linspace(0, 1, len(segment))
        x_new = np.linspace(0, 1, num_points)
        segment_resampled = np.interp(x_new, x_old, segment)

        beats.append(segment_resampled)

    if len(beats) < 2:
        return None

    beats = np.vstack(beats)
    mean_waveform = np.mean(beats, axis=0)

    k = max(3, int(0.10 * num_points))
    x = np.arange(k)
    slope = np.polyfit(x, mean_waveform[:k], 1)[0]

    if slope < 0:
        beats = -beats
        mean_waveform = np.mean(beats, axis=0)

    std_waveform = np.std(beats, axis=0)
    x_axis = np.linspace(0, 100, num_points)

    return x_axis, mean_waveform, std_waveform, beats.shape[0]


class SummaryWindow(QtWidgets.QDialog):
    def __init__(self, x_axis, mean_waveform, std_waveform, num_beats):
        super().__init__()

        self.setWindowTitle("Summary of the Experiment - Average Pulse Waveform")
        self.resize(700, 500)

        layout = QtWidgets.QVBoxLayout(self)

        title = QtWidgets.QLabel(
            "<h2>Average Pulse Waveform - mmWave radar</h2>"
        )
        title.setAlignment(QtCore.Qt.AlignCenter)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.setLabels(left="Filtered Phase", bottom="Pulse Cycle (%)")
        self.plot_widget.showGrid(x=True, y=True)

        upper = mean_waveform + std_waveform
        lower = mean_waveform - std_waveform

        upper_curve = self.plot_widget.plot(
            x_axis, upper, pen=pg.mkPen((180, 180, 255), width=1)
        )
        lower_curve = self.plot_widget.plot(
            x_axis, lower, pen=pg.mkPen((180, 180, 255), width=1)
        )

        fill = pg.FillBetweenItem(
            upper_curve, lower_curve, brush=pg.mkBrush(100, 100, 255, 80)
        )
        self.plot_widget.addItem(fill)

        self.plot_widget.plot(
            x_axis,
            mean_waveform,
            pen=pg.mkPen(color="b", width=3)
        )

        info_label = QtWidgets.QLabel(
            f"Representative waveform from {num_beats} detected beats"
        )
        info_label.setAlignment(QtCore.Qt.AlignCenter)
        info_label.setStyleSheet("font-size: 18px; color: black; font-weight: bold;")

        layout.addWidget(title)
        layout.addWidget(self.plot_widget)
        layout.addWidget(info_label)


class RadarReader(Thread):
    def __init__(self, visualizer, if_gain_db=None, tx_power_level=None, fps=None):
        super().__init__()

        self.visualizer = visualizer
        self.stop_event = Event()

        self.if_gain_db = if_gain_db
        self.tx_power_level = tx_power_level
        self.fps = fps

        self.sensor = BGT60SensorThreaded(
            port=PORT,
            NUM_RX_ANTENNAS=NUM_RX_ANTENNAS,
            NUM_CHIRPS=CHIRPS_PER_FRAME,
            NUM_SAMPLES=SAMPLES_PER_CHIRP
        )

    def stop(self):
        self.stop_event.set()

    def run(self):
        try:
            self.sensor.start(
                gain_db=self.if_gain_db,
                tx_power=self.tx_power_level,
                fps=self.fps)

            while not self.stop_event.is_set():
                frame_id, sync_state, frame = self.sensor.get_latest_frame()

                if frame is None:
                    continue

                if ANTENNA_INDEX >= frame.shape[0]:
                    continue

                # frame shape from your class:
                # (num_antennas, num_chirps, num_samples)
                antenna_frame = frame[ANTENNA_INDEX]


                show_raw, process_pulse = self.visualizer.get_processing_options()
                # -------------------------------------------------
                # Optional: raw chirp / clipping view
                # -------------------------------------------------
                if show_raw:
                    if RAW_CHIRP_INDEX < antenna_frame.shape[0]:
                        raw_chirp = antenna_frame[RAW_CHIRP_INDEX].copy()
                        self.visualizer.add_raw_chirp(raw_chirp, frame_id)

                # -------------------------------------------------
                # Optional: pulse processing
                # -------------------------------------------------
                if not process_pulse:
                    continue

                # Remove DC per chirp
                antenna_frame = antenna_frame - np.mean(
                    antenna_frame,
                    axis=1,
                    keepdims=True
                )

                # Window over samples
                window = np.hanning(antenna_frame.shape[1])
                antenna_frame = antenna_frame * window

                # Range FFT over sample axis
                range_fft = np.fft.rfft(antenna_frame, axis=1)

                if RANGE_BIN >= range_fft.shape[1]:
                    continue

                # One complex value per chirp at the selected range bin
                bin_values = range_fft[:, RANGE_BIN]

                # Average chirps to get one complex value per frame
                complex_mean = np.mean(bin_values)

                phase_value = np.angle(complex_mean)

                self.visualizer.add_phase_point(phase_value)

        except Exception as e:
            print(f"RadarReader error: {e}")

        finally:
            self.sensor.stop()
            self.sensor.close()


class RadarVisualizer(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle(
            "Real-Time Arterial Pulse Wave - custom BGT60 dev board"
        )

        self.reader = None
        self.start_time = None
        self.lock = Lock()

        self.live_buffer = []
        self.full_buffer = []

        self.latest_raw_chirp = None
        self.latest_raw_frame_id = None
        self.clipping_info_text = "No raw chirp yet."

        self.show_raw_chirp = True
        self.process_pulse = True
        self.flip_waveform = False

        self.current_fps = DEFAULT_FPS

        self.prev_wrapped_phase = None
        self.phase_offset = 0.0

        self.setup_ui()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(40)

    def get_processing_options(self):
        with self.lock:
            return self.show_raw_chirp, self.process_pulse
        
    def setup_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)

        header = QtWidgets.QLabel(
            "Live Arterial Pulse Wave - custom BGT60 dev board"
        )
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        # -------------------------------------------------
        # View / processing options
        # -------------------------------------------------
        options_layout = QtWidgets.QHBoxLayout()

        self.raw_checkbox = QtWidgets.QCheckBox("Show raw chirp / clipping")
        self.raw_checkbox.setChecked(True)

        self.pulse_checkbox = QtWidgets.QCheckBox("Process pulse live")
        self.pulse_checkbox.setChecked(True)

        self.flip_button = QtWidgets.QPushButton("Flip waveform: OFF")
        self.flip_button.setCheckable(True)
        self.flip_button.setToolTip("Invert only the displayed live pulse waveform.")
        self.flip_button.clicked.connect(self.toggle_waveform_flip)

        self.raw_checkbox.stateChanged.connect(self.update_processing_options)
        self.pulse_checkbox.stateChanged.connect(self.update_processing_options)

        options_layout.addWidget(self.raw_checkbox)
        options_layout.addWidget(self.pulse_checkbox)
        options_layout.addWidget(self.flip_button)

        layout.addLayout(options_layout)


        # -------------------------------------------------
        # Runtime config controls
        # -------------------------------------------------
        config_layout = QtWidgets.QHBoxLayout()

        self.if_gain_box = QtWidgets.QComboBox()
        for gain in VALID_GAIN_STAGES:
            self.if_gain_box.addItem(f"{gain} dB", gain)

        default_gain_index = self.if_gain_box.findData(IF_GAIN_DB)
        if default_gain_index >= 0:
            self.if_gain_box.setCurrentIndex(default_gain_index)

        self.tx_power_spin = QtWidgets.QSpinBox()
        self.tx_power_spin.setRange(0, 31)
        self.tx_power_spin.setValue(TX_POWER_LEVEL)

        self.apply_config_button = QtWidgets.QPushButton("Apply Config")
        self.apply_config_button.clicked.connect(self.apply_config)

        self.fps_box = QtWidgets.QComboBox()
        for fps in VALID_FPS_STAGES:
            self.fps_box.addItem(f"{fps} FPS", fps)

        default_fps_index = self.fps_box.findData(DEFAULT_FPS)
        if default_fps_index >= 0:
            self.fps_box.setCurrentIndex(default_fps_index)



        config_layout.addWidget(QtWidgets.QLabel("IF Gain:"))
        config_layout.addWidget(self.if_gain_box)

        config_layout.addWidget(QtWidgets.QLabel("TX Power:"))
        config_layout.addWidget(self.tx_power_spin)

        config_layout.addWidget(QtWidgets.QLabel("FPS:"))
        config_layout.addWidget(self.fps_box)

        config_layout.addWidget(self.apply_config_button)

        layout.addLayout(config_layout)


        self.status_label = QtWidgets.QLabel("Status: idle")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        layout.addWidget(self.status_label)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.setLabels(
            left="Bandpassed Unwrapped Phase",
            bottom="Time (s)"
        )
        self.plot_widget.showGrid(x=True, y=True)

        layout.addWidget(self.plot_widget)

        self.plot_curve = self.plot_widget.plot(
            pen=pg.mkPen(color="r", width=3)
        )

        # Raw chirp plot for clipping / ADC range inspection
        self.raw_chirp_plot = pg.PlotWidget()
        self.raw_chirp_plot.setBackground("w")
        self.raw_chirp_plot.setLabels(
            left="Raw ADC Value",
            bottom="Sample Index"
        )
        self.raw_chirp_plot.showGrid(x=True, y=True)
        self.raw_chirp_plot.setYRange(0, ADC_MAX_VALUE)

        self.raw_chirp_curve = self.raw_chirp_plot.plot(
            pen=pg.mkPen(color="b", width=2),
            symbol="o",
            symbolSize=6,
            symbolBrush="b"
        )

        layout.addWidget(self.raw_chirp_plot)

        self.clipping_label = QtWidgets.QLabel("Raw chirp clipping status: waiting...")
        self.clipping_label.setStyleSheet("font-size: 14px; font-weight: bold; color: black;")
        layout.addWidget(self.clipping_label)

        footer = QtWidgets.QLabel(
            f"Port: {PORT}"
            f"Chirps/Frame: {CHIRPS_PER_FRAME} | Samples/Chirp: {SAMPLES_PER_CHIRP} | "
            f"Range Bin: {RANGE_BIN} | Antenna: {ANTENNA_INDEX} | IF Gain: {IF_GAIN_DB} dB"
        )
        layout.addWidget(footer)

        button_layout = QtWidgets.QHBoxLayout()

        self.start_button = QtWidgets.QPushButton("Start")
        self.stop_button = QtWidgets.QPushButton("Stop")

        self.start_button.setFixedSize(100, 40)
        self.stop_button.setFixedSize(100, 40)

        self.start_button.clicked.connect(self.start_acquisition)
        self.stop_button.clicked.connect(lambda: self.stop_acquisition(show_summary=True))

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)

        layout.addLayout(button_layout)

    def toggle_waveform_flip(self, checked):
        with self.lock:
            self.flip_waveform = checked

        if checked:
            self.flip_button.setText("Flip waveform: ON")
            self.status_label.setText("Waveform display flipped.")
        else:
            self.flip_button.setText("Flip waveform: OFF")
            self.status_label.setText("Waveform display normal.")

        # Force an immediate redraw so the current waveform flips right away.
        self.update_plot()

    def unwrap_phase_sample(self, phase_value):
        if self.prev_wrapped_phase is None:
            self.prev_wrapped_phase = phase_value
            return phase_value

        delta = phase_value - self.prev_wrapped_phase

        if delta > np.pi:
            self.phase_offset -= 2 * np.pi
        elif delta < -np.pi:
            self.phase_offset += 2 * np.pi

        unwrapped = phase_value + self.phase_offset
        self.prev_wrapped_phase = phase_value

        return unwrapped
    
    def add_raw_chirp(self, raw_chirp, frame_id=None):
        raw_chirp = np.asarray(raw_chirp, dtype=float)

        low_clip_count = np.sum(raw_chirp <= ADC_CLIP_MARGIN)
        high_clip_count = np.sum(raw_chirp >= (ADC_MAX_VALUE - ADC_CLIP_MARGIN))
        total_count = len(raw_chirp)

        low_clip_percent = 100.0 * low_clip_count / total_count
        high_clip_percent = 100.0 * high_clip_count / total_count

        min_val = np.min(raw_chirp)
        max_val = np.max(raw_chirp)
        peak_to_peak = max_val - min_val

        if high_clip_count > 0:
            status = (
                f"WARNING: upper clipping risk | "
                f"min={min_val:.0f}, max={max_val:.0f}, p2p={peak_to_peak:.0f}, "
                f"high_clip={high_clip_percent:.1f}%"
            )
        elif low_clip_count > 0:
            status = (
                f"WARNING: lower clipping risk | "
                f"min={min_val:.0f}, max={max_val:.0f}, p2p={peak_to_peak:.0f}, "
                f"low_clip={low_clip_percent:.1f}%"
            )
        elif max_val > 0.90 * ADC_MAX_VALUE:
            status = (
                f"Close to upper limit | "
                f"min={min_val:.0f}, max={max_val:.0f}, p2p={peak_to_peak:.0f}"
            )
        elif peak_to_peak < 100:
            status = (
                f"Signal maybe too small | "
                f"min={min_val:.0f}, max={max_val:.0f}, p2p={peak_to_peak:.0f}"
            )
        else:
            status = (
                f"OK | "
                f"min={min_val:.0f}, max={max_val:.0f}, p2p={peak_to_peak:.0f}"
            )

        if frame_id is not None:
            status = f"Frame {frame_id} | " + status

        with self.lock:
            self.latest_raw_chirp = raw_chirp
            self.latest_raw_frame_id = frame_id
            self.clipping_info_text = status

    def add_phase_point(self, phase_value):
        if self.start_time is None:
            return

        current_time = time.time() - self.start_time
        unwrapped_phase = self.unwrap_phase_sample(phase_value)

        with self.lock:
            self.full_buffer.append((current_time, unwrapped_phase))

            fps = self.current_fps
            # Only filter recent data for live display.
            # This avoids filtering the full measurement on every frame.
            max_live_points = int(fps  * LIVE_WINDOW_SECONDS)

            recent_buffer = self.full_buffer[-max_live_points:]
            raw_phase_recent = [x[1] for x in recent_buffer]

            filtered_recent = bandpass_filter(raw_phase_recent, fs=fps)
            filtered_value = filtered_recent[-1]

            self.live_buffer.append((current_time, unwrapped_phase, filtered_value))

            while len(self.live_buffer) > max_live_points:
                self.live_buffer.pop(0)

    def update_plot(self):
        with self.lock:
            times = None
            filtered_phase = None
            flip_waveform = self.flip_waveform

            if self.live_buffer:
                times = np.array([x[0] for x in self.live_buffer])
                filtered_phase = np.array([x[2] for x in self.live_buffer])

            raw_chirp = None
            clipping_info_text = self.clipping_info_text

            if self.latest_raw_chirp is not None:
                raw_chirp = self.latest_raw_chirp.copy()

        # Update pulse plot
        if times is not None and filtered_phase is not None:
            # Optional display smoothing
            # filtered_phase = smooth_for_display(filtered_phase, fs=FRAME_RATE)

            if flip_waveform:
                filtered_phase = -filtered_phase

            self.plot_curve.setData(times, filtered_phase)

        # Update raw chirp plot
        if raw_chirp is not None:
            x = np.arange(len(raw_chirp))
            self.raw_chirp_curve.setData(x, raw_chirp)

            self.raw_chirp_plot.setXRange(0, max(1, len(raw_chirp) - 1))
            self.raw_chirp_plot.setYRange(0, ADC_MAX_VALUE)

        # Update clipping label
        self.clipping_label.setText(f"Raw chirp clipping status: {clipping_info_text}")

        if "WARNING" in clipping_info_text:
            self.clipping_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: red;"
            )
        elif "Close" in clipping_info_text:
            self.clipping_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: orange;"
            )
        elif "too small" in clipping_info_text:
            self.clipping_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: orange;"
            )
        else:
            self.clipping_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: green;"
            )

    def update_processing_options(self):
        with self.lock:
            self.show_raw_chirp = self.raw_checkbox.isChecked()
            self.process_pulse = self.pulse_checkbox.isChecked()

        self.raw_chirp_plot.setVisible(self.raw_checkbox.isChecked())
        self.clipping_label.setVisible(self.raw_checkbox.isChecked())
        self.plot_widget.setVisible(self.pulse_checkbox.isChecked())

        if not self.raw_checkbox.isChecked() and not self.pulse_checkbox.isChecked():
            self.status_label.setText("Warning: both views disabled.")
        else:
            self.status_label.setText(
                f"Raw chirp: {'on' if self.raw_checkbox.isChecked() else 'off'} | "
                f"Pulse: {'on' if self.pulse_checkbox.isChecked() else 'off'}"
            )


    def apply_config(self):
        if_gain_db = self.if_gain_box.currentData()
        tx_power_level = self.tx_power_spin.value()
        fps = self.fps_box.currentData()

        if self.reader is None:
            self.status_label.setText(
                f"Config selected: IF Gain={if_gain_db} dB, TX Power={tx_power_level}, FPS={fps}. " 
                f"Press Start to apply."
            )
            return

        self.status_label.setText("Applying config: restarting sensor...")
        QtWidgets.QApplication.processEvents()

        self.stop_acquisition(show_summary=False)
        self.start_acquisition()

        self.status_label.setText(
            f"Applied config and restarted: IF Gain={if_gain_db} dB, "
            f"TX Power={tx_power_level}, FPS={fps}"
        )

    def start_acquisition(self):
        self.stop_acquisition(show_summary=False)

        with self.lock:
            self.live_buffer.clear()
            self.full_buffer.clear()
            self.latest_raw_chirp = None
            self.latest_raw_frame_id = None
            self.clipping_info_text = "No raw chirp yet."

        self.prev_wrapped_phase = None
        self.phase_offset = 0.0

        self.start_time = time.time()

        if_gain_db = self.if_gain_box.currentData()
        tx_power_level = self.tx_power_spin.value()
        fps = self.fps_box.currentData()

        self.current_fps = fps

        self.reader = RadarReader(
            self,
            if_gain_db=if_gain_db,
            tx_power_level=tx_power_level,
            fps=fps
        )

        self.reader.start()

        self.status_label.setText(
            f"Started: IF Gain={if_gain_db} dB, TX Power={tx_power_level}, FPS={fps}"
        )

    def stop_acquisition(self, show_summary=True):
        if self.reader is None:
            return

        self.reader.stop()
        self.reader.join(timeout=2.0)

        self.reader = None

        self.status_label.setText("Stopped.")

        if show_summary:
            self.show_summary()

    def show_summary(self):
        with self.lock:
            fps = self.current_fps
            if len(self.full_buffer) < fps * SUMMARY_SECONDS:
                print("Not enough data for summary.")
                return

            times, raw_phase = zip(*self.full_buffer)

        end_time = times[-1] - SUMMARY_TAIL_SKIP_SECONDS
        start_time = end_time - SUMMARY_SECONDS

        summary_phase = [
            phase for t, phase in zip(times, raw_phase)
            if start_time <= t <= end_time
        ]

        if len(summary_phase) < fps:
            print("Not enough data in summary window.")
            return
        
        return
        result = extract_average_pulse_waveform(summary_phase, fs=fps)

        if result is None:
            print("Could not detect enough beats for average waveform.")
            return

        x_axis, mean_waveform, std_waveform, num_beats = result

        SummaryWindow(
            x_axis,
            mean_waveform,
            std_waveform,
            num_beats
        ).exec_()


if __name__ == "__main__":

    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_DisableHighDpiScaling, True)
    QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_Use96Dpi, True)    
    app = QtWidgets.QApplication(sys.argv)

    window = RadarVisualizer()
    window.show()

    sys.exit(app.exec_())