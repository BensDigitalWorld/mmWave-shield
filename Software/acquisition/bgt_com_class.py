# -----------------------------------------------------------------------------
#
# File: bgt_com_class.py
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

import argparse
import serial
import struct
import time
import numpy as np

import threading
import queue


# ===========================================================================
# DEFINES
# ===========================================================================

PACKET_SIZE = 244
MMWAVE_HEADER = 0xAA
MMWAVE_TRAILER = 0x55

# BLE Commands
START_CMD     = (39).to_bytes(1, "big")
STOP_CMD      = (40).to_bytes(1, "big")
CONFIGURE_CMD = (41).to_bytes(1, "big")
OFF_CMD       = (42).to_bytes(1, "big")
ON_CMD        = (43).to_bytes(1, "big")
SET_IF_GAIN   = (44).to_bytes(1, "big")
SET_TX_POWER  = (45).to_bytes(1, "big")
SET_FPS       = (46).to_bytes(1, "big")

VALID_GAIN_STAGES = [18, 23, 28, 30, 33, 35, 38, 40, 43, 45, 48, 50, 55, 60]

VALID_FPS_STAGES = [25, 50, 100, 150, 200]

# ===========================================================================
# HELPER
# ===========================================================================

def unpack_12bit_packed(packed_bytes, num_samples):
    raw = np.frombuffer(packed_bytes, dtype=np.uint8)

    num_pairs = (num_samples + 1) // 2
    required_bytes = num_pairs * 3

    if len(raw) < required_bytes:
        raise ValueError(
            f"Not enough packed data: got {len(raw)} bytes, need {required_bytes}"
        )

    raw = raw[:required_bytes]

    b0 = raw[0::3].astype(np.uint16)
    b1 = raw[1::3].astype(np.uint16)
    b2 = raw[2::3].astype(np.uint16)

    samples0 = (b0 << 4) | (b1 >> 4)
    samples1 = ((b1 & 0x0F) << 8) | b2

    out = np.empty(num_pairs * 2, dtype=np.uint16)
    out[0::2] = samples0
    out[1::2] = samples1

    return out[:num_samples]

# ===========================================================================
# Working Class
# ===========================================================================

class BGT60Sensor:
    def __init__(self, port, NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES):
        self.ser = serial.Serial(port, 115200, timeout=0.2) 
        self.frame_chunks = []
        self.NUM_SAMPLES = NUM_SAMPLES
        self.NUM_CHIRPS = NUM_CHIRPS
        self.NUM_RX_ANTENNAS = NUM_RX_ANTENNAS
        self.SAMPLES_EXPECTED = NUM_SAMPLES * NUM_CHIRPS * NUM_RX_ANTENNAS
        self.current_time = None
        self.expected_chunk = 0

    def start(self, gain_db = None, tx_power=None, fps=None):
        print("Sending Start-Command...")

        self.ser.reset_input_buffer()
        self.ser.write(ON_CMD)
        time.sleep(0.01)

         # Optional set IF-Gain, TX-Power and FPS
        if gain_db is not None:
            self.set_if_gain(gain_db)

        if tx_power is not None:
            self.set_tx_power(tx_power)

        if fps is not None:
            self.set_fps(fps)

        self.ser.write(CONFIGURE_CMD)
        time.sleep(0.02)
        self.ser.write(START_CMD)

    def stop(self):
        print("Sending Stop-Command...")
        self.ser.write(STOP_CMD)
        time.sleep(0.01)
        self.ser.write(OFF_CMD)

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def set_if_gain(self, gain_db):
        if gain_db not in VALID_GAIN_STAGES:
            print(f"Error: {gain_db} dB is not a valid Gain-Stage!")
            print(f"Valid Stages are: {VALID_GAIN_STAGES}")
            print("Using Standard Gain")
            return False
        
        print(f"Sending IF-Gain Command: {gain_db} dB")
        
        # Build Packet:: Command Byte (0x2C) + Value-Byte (eg. 0x17 for 23)
        payload = SET_IF_GAIN + gain_db.to_bytes(1, "big")
        self.ser.write(payload)
        time.sleep(0.01)
        return True
    
    def set_tx_power(self, tx_power):
        if tx_power < 0 or tx_power > 31:
            print(f"Invalid TX power: {tx_power}. Allowed: 0...31")
            return False

        payload = SET_TX_POWER + tx_power.to_bytes(1, "big")
        self.ser.write(payload)
        time.sleep(0.01)
        print(f"TX power set to {tx_power}")
        return True
    
    def set_fps(self, fps):
        if fps not in VALID_FPS_STAGES:
            print(f"Error: {fps} is not a valid FPS-Setting!")
            print(f"Allowd are: {VALID_FPS_STAGES}")
            print("Using Standard FPS")
            return False
        
        print(f"Sending FPS Command: {fps}")
        
        payload = SET_FPS + fps.to_bytes(1, "big")
        self.ser.write(payload)
        time.sleep(0.01)
        return True

    def get_next_frame_2(self, stop_event=None):           
        while True:
            if stop_event is not None and stop_event.is_set():
                return None, None, None
            
            # 1. search Sync
            char = self.ser.read(1)
            if not char or ord(char) != MMWAVE_HEADER:
                continue

            # 2. Read rest of the packte (243 Bytes)
            data = self.ser.read(PACKET_SIZE - 1)
            if len(data) < PACKET_SIZE - 1:
                continue

            # 3. Validated Trailer (last Byte in the read Packet)
            if data[242] != MMWAVE_TRAILER:
                print("Sync Lost - Trailer Wrong!")
                self.frame_chunks = [] # Empty Buffer for safety
                continue

            # 4. Metadata (Bytes 0-5 in 'data' Block)
            time_packed, chunk, total_chunks = struct.unpack(">IBB", data[0:6])
            time = time_packed & ~0x01
            sync_state = time_packed & 0x01

            if chunk == 0:
                self.frame_chunks = []
                self.current_time = time
                self.expected_chunk = 0

            if self.current_time is None:
                continue

            if time != self.current_time:
                print(f"TimeStamp Jump, Discarding Frame.")
                self.frame_chunks = []
                self.current_time = None
                self.expected_chunk = 0
                continue
            
            if chunk != self.expected_chunk:
                print(f"Chunk Lost: excpected {self.expected_chunk}, got {chunk}. Frame Discareded.")
                self.frame_chunks = []
                self.current_time = None
                self.expected_chunk = 0
                continue

            # 5. Gather Chunck data (Bytes 6-241)
            self.frame_chunks.append(data[6:242])
            self.expected_chunk += 1

            # 6. If frame complete
            if chunk + 1 == total_chunks:
                full_bytes = b"".join(self.frame_chunks)
                self.frame_chunks = [] # Empty Buffer
                self.current_time = None
                self.expected_chunk = 0

                packed_bytes_expected = ((self.SAMPLES_EXPECTED + 1) // 2) * 3

                # Only take expected Data sonce last chunck might be zero padded
                if len(full_bytes) >= packed_bytes_expected:
                    packed_data = full_bytes[:packed_bytes_expected]
                    frame_data = unpack_12bit_packed(packed_data, self.SAMPLES_EXPECTED)
                    # Reshape in (Chirps, Samples, Antennen)
                    # When NUM_RX_ANTENNAS = 1, last Dimension is 1
                    matrix = frame_data.reshape((self.NUM_CHIRPS, self.NUM_SAMPLES, self.NUM_RX_ANTENNAS))
                    # Transpose to (Antennen, Chirps, Samples), format like it is in the Radar SDK
                    matrix = np.transpose(matrix, (2, 0, 1))
                    return time, sync_state, matrix
                else:
                    print(f"Frame Not full: Got {packed_bytes_expected} instead of {self.SAMPLES_EXPECTED} Samples")
                    return None, None, None


# ===========================================================================
# Wrapper Class to enalble Threading
# ===========================================================================


class BGT60SensorThreaded(BGT60Sensor):
    """Threaded interface for receiving BGT60 radar frames in the background.

    This class extends `BGT60Sensor` by running frame reception in a separate
    thread. Received frames are stored in a queue and can be accessed either
    in FIFO order using `get_next_frame()` or as the most recent frame using
    `get_latest_frame()`.

    Each returned frame has the format:
        (timestamp, sync_state, frame_contents)

    where `frame_contents` has shape:
        (NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES)
    """

    def __init__(self, port, NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES):
        """Initialize the threaded radar sensor interface.

        Args:
            port: Serial port connected to the BioGAP BLE/serial interface.
            NUM_RX_ANTENNAS: Number of active receive antennas.
            NUM_CHIRPS: Number of chirps per radar frame.
            NUM_SAMPLES: Number of samples per chirp.
        """
        super().__init__(port, NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES)
        self.frame_queue = queue.Queue(maxsize=100)
        self.stop_event = threading.Event()
        self.thread = None


    def start(self, gain_db=None, tx_power=None, fps=None):
        """Start radar streaming and launch the background receiver thread.

        Args:
            gain_db: Optional IF gain setting in dB, defaults to 33dB.
            tx_power: Optional radar TX power level, defaults to 31.
            fps: Optional frame rate setting, defaults to defaults to 100fps.

        If the receiver thread is already running, the function returns
        without starting a second thread.
        """
        if self.thread is not None and self.thread.is_alive():
            print("Thread already running.")
            return
        
        self.stop_event.clear()

        super().start(gain_db=gain_db, tx_power=tx_power, fps=fps)

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        """Stop radar streaming and terminate the background receiver thread."""
        self.stop_event.set()

        super().stop()
 
        if self.thread is not None:
            self.thread.join(timeout=1.0)

    def _run(self):
        """Continuously receive radar frames in the background thread.

        This private method repeatedly calls `get_next_frame_2()` and stores
        valid frames in `frame_queue`. If the queue is full, the oldest behavior
        is not changed; the newly received frame is discarded.
        """
        while not self.stop_event.is_set():
            try:

                time, sync_state, frame_contents = self.get_next_frame_2(self.stop_event)
                
                if frame_contents is not None:
                    try:
                        self.frame_queue.put(
                            (time, sync_state, frame_contents),
                            timeout=0.1
                        )
                    except queue.Full:
                        print("Warning: Frame Queue full, Frame discarded.")


            except Exception as e:
                if not self.stop_event.is_set():
                    print(f"Error in Receiving-Thread: {e}")
                break


    def get_next_frame(self):
        """Return the next available radar frame from the queue.

        Returns:
            tuple: `(timestamp, sync_state, frame_contents)` if a frame is
            available, otherwise `(None, None, None)` after a timeout.

        This function preserves frame order and is therefore suited for
        recording scripts.
        """
        try:
            return self.frame_queue.get(timeout=1.0)
        except queue.Empty:
            return None, None, None
    

    def get_latest_frame(self):
        """Return the newest available radar frame and discard older frames.

        Returns:
            tuple: `(timestamp, sync_state, frame_contents)` if a frame is
            available, otherwise `(None, None, None)` after a timeout.

        This function is useful for live visualization, where low latency is
        more important than processing every single frame.
        """
        latest = None

        try:
            latest = self.frame_queue.get(timeout=1.0)
        except queue.Empty:
            return None, None, None

        while True:
            try:
                latest = self.frame_queue.get_nowait()
            except queue.Empty:
                break

        return latest
    
    def clear_queue(self):
        """Remove all currently buffered frames from the queue.

        This is useful before starting a new recording segment, so that old
        frames from the previous configuration are discarded.
        """
        while True:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break