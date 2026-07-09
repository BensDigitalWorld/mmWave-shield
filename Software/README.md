# Software

This folder contains the Python software used for acquiring, visualizing, processing, and plotting mmWave radar data from the BioGAP mmWave shield.

The software is organized around a reusable device communication class in `acquisition/bgt_com_class.py`. The other scripts use this class for live visualization, single recordings, FPS sweeps, and offline analysis.


## Getting Started

Create a local Python virtual environment inside the `Software/` folder:

```powershell
cd Software
python -m venv .venv
```

Activate the environment.

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install the required Python packages:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Optional: Infineon Radar SDK Python Wheel

Some scripts in `tools/devkit_exploration/` and `tools/static_distance_validation/` require the Infineon Radar SDK Python wrapper.

The Infineon Radar SDK wheel is not included in this repository and is not installed through `requirements.txt`. It has to be installed manually from the Infineon Radar SDK release package.

The required wheel can usually be found in the `python_wheels/` folder of the Infineon Radar SDK package. Choose the wheel that matches your operating system, CPU architecture, and Python version.

For example on windows: After creating and activating the Python virtual environment, install the wheel with:

```powershell
python -m pip install "path\to\radar_sdk\python_wheels\ifxradarsdk-3.6.4+4b4a6245-py3-none-win_amd64.whl"
```
Make sure that the wheel matches your operating system, CPU architecture, and Python version.

This is only required for scripts that directly use the Infineon DevKit or SDK-based processing examples. The BioGAP acquisition and plotting scripts do not require the SDK wheel unless they explicitly import `ifxradarsdk`.

## Measurement Data

Most scripts expect the measurement data to be available inside the `Software/data/` folder. The raw measurement data is not included in this repository because it can be large and may contain external measurement files.

If the measurement data is provided separately, for example via Dropbox, copy it into the `Software/` folder before running the analysis scripts.

Example structure:

```text
Software/
├── data/
│   ├── biogap_measurments/
│   │   └── radar_fps_sweep/
│   │       ├── radar_invivo_fps_sweep_2026-05-22_17-28/
│   │       ├── radar_invivo_fps_sweep_2026-05-22_17-51/
│   │       └── ...
│   │
│   ├── finaPress_measurments/
│   │   ├── 2026-05-22_19.24.20.nsc
│   │   ├── 2026-05-22_18.46.42.nsc
│   │   └── ...
│   │
│   ├── power_measurements/
│   │   └── powerLogs/
│   │       ├── Baseboard/
│   │       ├── shield3_3/
│   │       └── shield1_8/
│   │
│   └── processed/
│       ├── wrist/
│       └── temple/
```

The exact folder names should match the paths configured in the corresponding Python scripts.

The BioGAP acquisition and live-viewer scripts can be used without previously recorded data. However, the offline analysis and plotting scripts require the corresponding measurement files.

Scripts related to Finapres / maneuver analysis require both:

* the recorded mmWave radar data
* the corresponding Finapres / NovaScope `.nsc` files

Scripts related to power analysis require exported `.csv` logs recorded with the Nordic nRF Power Profiler Kit.

Some example data is provided and can be used in the jupyter notebook to get started with!

## Device Communication Class

The main interface to the BioGAP mmWave shield is implemented in:

```text
acquisition/bgt_com_class.py
```

The class wraps the communication with the BioGAP firmware and provides a Python interface for controlling the mmWave sensor and receiving radar frames.

Typical capabilities include:

* opening and closing the communication interface
* powering the mmWave shield on and off
* configuring the radar
* starting and stopping radar streaming
* setting radar parameters such as IF gain, TX power, and frame rate
* receiving raw radar frames
* optionally receiving frames in a background thread
* accessing either the next available frame or the most recent frame

The received raw radar frames are represented as NumPy arrays with the shape:

```text
(num_rx_antennas, num_chirps, num_samples)
```

For complete recordings, the resulting saved data usually has the shape:

```text
(num_frames, num_rx_antennas, num_chirps, num_samples)
```

## Usage

Scripts should be started as Python modules from inside the `Software/` folder. This keeps imports and relative data paths and imports consistent.

Example:

```powershell
python -m tools.static_distance_validation.static_distance_devkit
```

### Record some Data Example:

```powershell
python -m acquisition.record_fps_sweep_biogap
```

### Start the Live-Viewer:

```powershell
python -m live_viewer.live_waveform_viewer
```

### Run the Static Distance Validation:

```powershell
python -m tools.static_distance_validation.static_distance_biogap
```

### Analysis Examples:

Run the offline SNR analysis:

```powershell
python -m analysis_plotting.snr_analysis
```

Run the power analysis:

```powershell
python -m analysis_plotting.power_analysis
```


Most scripts contain configuration variables at the top of the file, such as input paths, output folders, recording names, frame rates, or selected measurement locations. These should be checked and adjusted before running the script.

## Notes

The scripts in `tools/devkit_exploration/` and `tools/static_distance_validation/` were mainly used during sensor bring-up and validation. They are useful for debugging and reference, but they are not the main BioGAP acquisition pipeline.



## License

Unless stated otherwise, the software in this folder is licensed under the Apache License 2.0. See `Software/LICENSE` file for details.

The `tools/devkit_exploration/` and `tools/static_distance_validation/third_party/` directories contain third-party sources from the Infineon Radar SDK or files based on Infineon example code. Some of these files were adapted for this project.

See the respective source file headers for the original copyright notices, modification notes, and license terms.