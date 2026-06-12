#bgt_communaication class definition

import argparse
import serial
import struct
import time
import numpy as np

import threading
import queue



PACKET_SIZE = 244
MMWAVE_HEADER = 0xAA
MMWAVE_TRAILER = 0x55




# BLE Commands
#define START_MMWAVE_STREAMING 39
#define STOP_MMWAVE_STREAMING 40
#define CONFIGURE_MMWAVE 41
#define TURN_OFF_MMWAVE 42
#define TURN_ON_MMWAVE 43
#define CHANGE_IFGAIN_MMWAVE 44

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


class BGT60Sensor:
    def __init__(self, port, NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES):
        self.ser = serial.Serial(port, 115200, timeout=0.2) # Baudrate bei USB CDC egal
        self.frame_chunks = []
        self.NUM_SAMPLES = NUM_SAMPLES
        self.NUM_CHIRPS = NUM_CHIRPS
        self.NUM_RX_ANTENNAS = NUM_RX_ANTENNAS
        self.SAMPLES_EXPECTED = NUM_SAMPLES * NUM_CHIRPS * NUM_RX_ANTENNAS
        self.current_time = None
        self.expected_chunk = 0

    def start(self, gain_db = None, tx_power=None, fps=None):
        print("Sende Start-Kommando...")

        self.ser.reset_input_buffer()
        self.ser.write(ON_CMD)
        time.sleep(0.01)

         # Optional IF-Gain setzen
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
        print("Sende Stop-Kommando...")
        self.ser.write(STOP_CMD)
        time.sleep(0.01)
        self.ser.write(OFF_CMD)

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    def set_if_gain(self, gain_db):
        if gain_db not in VALID_GAIN_STAGES:
            print(f"Fehler: {gain_db} dB ist keine gültige Gain-Stufe!")
            print(f"Erlaubt sind: {VALID_GAIN_STAGES}")
            print("Nutze Standard Gain")
            return False
        
        print(f"Sende IF-Gain Kommando: {gain_db} dB")
        # Paket bauen: Command Byte (0x2C) + Wert-Byte (z.B. 0x17 für 23)
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
            print(f"Fehler: {fps} ist keine gültige FPS-Stufe!")
            print(f"Erlaubt sind: {VALID_FPS_STAGES}")
            print("Nutze Standard FPS")
            return False
        
        print(f"Sende FPS Kommando: {fps}")
        # Paket bauen: Command Byte (0x2C) + Wert-Byte (z.B. 0x17 für 23)
        payload = SET_FPS + fps.to_bytes(1, "big")
        self.ser.write(payload)
        time.sleep(0.01)
        return True

    def get_next_frame_2(self, stop_event=None):           
        while True:
            if stop_event is not None and stop_event.is_set():
                return None, None, None
            
            # 1. Sync suchen
            char = self.ser.read(1)
            if not char or ord(char) != MMWAVE_HEADER:
                continue

            # 2. Rest des Pakets lesen (243 Bytes)
            data = self.ser.read(PACKET_SIZE - 1)
            if len(data) < PACKET_SIZE - 1:
                continue

            # 3. Trailer prüfen (letztes Byte im gelesenen Block)
            if data[242] != MMWAVE_TRAILER:
                print("Sync verloren - Trailer falsch!")
                self.frame_chunks = [] # Puffer sicherheitshalber leeren
                continue

            # 4. Metadaten (Bytes 0-5 im 'data' Block)
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
                print(f"Frame-ID Sprung, Frame verworfen.")
                self.frame_chunks = []
                self.current_time = None
                self.expected_chunk = 0
                continue
            
            if chunk != self.expected_chunk:
                print(f"Chunk verloren: erwartet {self.expected_chunk}, bekommen {chunk}. Frame verworfen.")
                self.frame_chunks = []
                self.current_time = None
                self.expected_chunk = 0
                continue

            # 5. Nutzdaten sammeln (Bytes 6-241)
            self.frame_chunks.append(data[6:242])
            self.expected_chunk += 1

            # 6. Wenn Frame komplett
            if chunk + 1 == total_chunks:
                full_bytes = b"".join(self.frame_chunks)
                self.frame_chunks = [] # Puffer leeren
                self.current_time = None
                self.expected_chunk = 0

                # Umwandeln in uint16 (Anpassung: Little Endian '<u2' oder Big Endian '>u2')
                # Wenn dein C-Code einfach uint16_t sendet, ist es meist Little Endian
                #raw_data = np.frombuffer(full_bytes, dtype='<u2')
                
                #MY CHANGES NOW
                packed_bytes_expected = ((self.SAMPLES_EXPECTED + 1) // 2) * 3

                # Nur die echten Samples nehmen (Padding abschneiden)
                if len(full_bytes) >= packed_bytes_expected:
                    packed_data = full_bytes[:packed_bytes_expected]
                    frame_data = unpack_12bit_packed(packed_data, self.SAMPLES_EXPECTED)
                    # Reshape in (Chirps, Samples, Antennen)
                    # Da NUM_RX_ANTENNAS = 1, ist die letzte Dimension 1
                    matrix = frame_data.reshape((self.NUM_CHIRPS, self.NUM_SAMPLES, self.NUM_RX_ANTENNAS))
                    # Transpose zu (Antennen, Chirps, Samples) für das SDK Format
                    matrix = np.transpose(matrix, (2, 0, 1))
                    return time, sync_state, matrix
                else:
                    print(f"Frame unvollständig: {packed_bytes_expected} statt {self.SAMPLES_EXPECTED} Samples")
                    return None, None, None


# ... (Deine BGT60Sensor Klasse bleibt gleich) ...

class BGT60SensorThreaded(BGT60Sensor):
    def __init__(self, port, NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES):
        super().__init__(port, NUM_RX_ANTENNAS, NUM_CHIRPS, NUM_SAMPLES)
        self.frame_queue = queue.Queue(maxsize=100)
        self.stop_event = threading.Event()
        self.thread = None


    def start(self, gain_db=None, tx_power=None, fps=None):
        if self.thread is not None and self.thread.is_alive():
            print("Thread läuft bereits.")
            return
        
        self.stop_event.clear()

        super().start(gain_db=gain_db, tx_power=tx_power, fps=fps)

        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

        super().stop()
 
        if self.thread is not None:
            self.thread.join(timeout=1.0)

    def _run(self):
        """Dieser Loop läuft im Hintergrund und sammelt nur Daten."""
        while not self.stop_event.is_set():
            try:
                # Nutze get_next_frame_2 (die stabilere Version mit while True)
                time, sync_state, frame_contents = self.get_next_frame_2(self.stop_event)
                
                if frame_contents is not None:
                    try:
                        self.frame_queue.put(
                            (time, sync_state, frame_contents),
                            timeout=0.1
                        )
                    except queue.Full:
                        print("Warnung: Frame Queue voll, Frame verworfen.")


            except Exception as e:
                if not self.stop_event.is_set():
                    print(f"Fehler im Empfangs-Thread: {e}")
                break

    def get_next_frame(self):
        """Holt den nächsten fertigen Frame aus der Queue."""
        try:
            return self.frame_queue.get(timeout=1.0)
        except queue.Empty:
            return None, None, None
    

    def get_latest_frame(self):
        """Holt den neuesten Frame und verwirft ältere Frames."""
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
        while True:
            try:
                self.frame_queue.get_nowait()
            except queue.Empty:
                break