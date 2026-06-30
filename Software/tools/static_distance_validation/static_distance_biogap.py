# ===========================================================================
# Copyright (C) 2021-2022 Infineon Technologies AG
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
#    this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
# ===========================================================================
#
# Modifications:
# Copyright (C) 2026, ETH Zurich
#
# Author:
# - Benjamin Löliger, ETH Zurich
#
# This file was adapted for the BioGAP mmWave radar project.
# Modifications include:
# - adapted radar configuration handling so BioGap can be used as a Device
#
# SPDX-License-Identifier: BSD-3-Clause
# ===========================================================================


import argparse

from enum import IntEnum
from acquisition.bgt_com_class import BGT60SensorThreaded
from tools.static_distance_validation.third_party.DistanceAlgo import *

try:
    from ifxradarsdk import get_version_full
    from ifxradarsdk.fmcw import DeviceFmcw
    from ifxradarsdk.fmcw.types import FmcwSimpleSequenceConfig, FmcwMetrics
except ImportError as exc:
    raise ImportError(
        "The Infineon Radar SDK Python package is required for this script. "
        "Install it from the Radar SDK wheel as described in the README."
    ) from exc



# -------------------------------------------------
# Helpers
# -------------------------------------------------
def parse_program_arguments(description, def_nframes, def_frate):
    # Parse all program attributes
    # description:   describes program
    # def_nframes:   default number of frames
    # def_frate:     default frame rate in Hz

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-n', '--nframes', type=int,
                        default=def_nframes, help="number of frames, default " + str(def_nframes))
    parser.add_argument('-f', '--frate', type=int, default=def_frate,
                        help="frame rate in Hz, default " + str(def_frate))
    return parser.parse_args()

class RadarSensor(IntEnum):
    """Radar sensors"""
    BGT60TR13C    = 0,   # BGT60TR13C
    BGT60ATR24C   = 1,   # BGT60ATR24C
    BGT60UTR13DAIP= 2,   # BGT60UTR13DAIP
    BGT60TR12E    = 3,   # BGT60TR12E
    BGT60UTR11AIP = 4,   # BGT60UTR11AIP
    BGT120UTR13E  = 5,   # BGT120UTR12E
    BGT24LTR24    = 6,   # BGT24LTR24
    BGT120UTR24   = 7,   # BGT120UTR24
    BGT60ATR24EAIP= 8,   # BGT60ATR24EAIP
    BGT24LTR13E   = 9,   # BGT24LTR13E
    Unknown_Avian = 10,  # Unknown Avian device        
    BGT60LTR11AIP = 256, # BGT60LTR11AIP
    BGT24ATR22    = 257, # BGT24ATR22
    Unknown_sensor= 4095 # Unknown sensor

# -------------------------------------------------
# Main logic
# -------------------------------------------------
if __name__ == '__main__':

        args = parse_program_arguments(
            '''Displays distance plot from Radar Data''',
            def_nframes=100,
            def_frate=5)

        
with DeviceFmcw(sensor_type = RadarSensor.BGT60TR13C) as device:
        print(f"Radar SDK Version: {get_version_full()}")
        print("Sensor: " + str(device.get_sensor_type()))

        i_ant = 0  # use only 1st RX antenna
        num_rx_antennas = 1

        metrics = FmcwMetrics(
            range_resolution_m=0.05,
            max_range_m=1.6,
            max_speed_m_s=3,
            speed_resolution_m_s=0.2,
            center_frequency_Hz=60_750_000_000,
        )

        # create acquisition sequence based on metrics parameters
        sequence = device.create_simple_sequence(FmcwSimpleSequenceConfig())
        sequence.loop.repetition_time_s = 1 / args.frate  # set frame repetition time

        # convert metrics into chirp loop parameters
        chirp_loop = sequence.loop.sub_sequence.contents
        device.sequence_from_metrics(metrics, chirp_loop)

        # set remaining chirp parameters which are not derived from metrics
        chirp = chirp_loop.loop.sub_sequence.contents.chirp
        chirp.sample_rate_Hz = 1_000_000
        chirp.rx_mask = (1 << num_rx_antennas) - 1
        chirp.tx_mask = 1
        chirp.tx_power_level = 31
        chirp.if_gain_dB = 33
        chirp.lp_cutoff_Hz = 500000
        chirp.hp_cutoff_Hz = 80000


        device.set_acquisition_sequence(sequence)


        device.ifx_fmcw_print_sequence((device.get_acquisition_sequence()))

        algo = DistanceAlgo(chirp, chirp_loop.loop.num_repetitions)
        
        sensor = BGT60SensorThreaded(
                port='COM4',
                NUM_RX_ANTENNAS=1,
                NUM_CHIRPS=32,
                NUM_SAMPLES=64)

        sensor.start()



        try:
            for i in range(args.nframes):
                _, _,  frame_contents = sensor.get_latest_frame()
                
                if frame_contents is not None:
                    # frame_contents hat jetzt Form (1, 32, 64)
                    antenna_samples = frame_contents[0, :, :] # Erste Antenne
                    
                    distance_peak_m, distance_data = algo.compute_distance(antenna_samples)
                    print(f"Distance: {distance_peak_m:05.3f}m")
                else:
                    print("Frame übersprungen...")
        
        except KeyboardInterrupt:
            pass
        finally:
            sensor.stop()
            sensor.close()
