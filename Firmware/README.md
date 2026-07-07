
# mmWave Raw Data Stream

This folder contains the firmware to use the mmWave shield on BioGAP in streaming mode.

## Getting Started
If the SENSEI-SDK is not set up yet follow the steps in [../Documentation/getting_started.md](../Documentation/getting_started.md).

Make sure to attach the Mainboard to the mmWave shield.

1. Flash the NRF application by opening it in Visual Studio Code using the NRF Connect SDK extension.
```sh
cd src_NRF
west build -b nrf5340_senseiv1_cpuapp
west flash
```

Make sure your `SENSEI_SDK_ROOT` environment variable is set to the path of the SENSEI SDK.

## mmWave Firmware Extensions

This firmware is based on the existing BioGAP firmware and was extended to support the custom mmWave radar shield.

The following files and functions were added or modified for the mmWave integration.

### Added files

#### Device-tree and shield files

The following files define the custom mmWave shield and the BGT60TR13C device-tree binding.

These files need to be copied into the Sensei-SDK / firmware tree as described in [../Documentation/getting_started.md](../Documentation/getting_started.md).

```text
custom_dts/bgt60tr13c/
└── infineon,bgt60tr13c.yaml

custom_shields/mmWaveShield/
├── Kconfig.shield
├── mmWaveShield.defconfig
└── mmWaveShield.overlay
```

#### Radar register configuration files

The following files contain predefined BGT60TR13C register configurations for different radar settings. The base configuration is used for the main measurements, while the remaining files contain alternative or test configurations.

```text
src_NRF/sensors/mmwave/driver/
├── 100fps_32chirps_8samples_2000kHz.h
├── 200fps.h
├── 150fps.h
├── 100fps.h
├── 50fps.h
├── 25fps.h
└── static_distance.h
```

#### XENSIV BGT60TRxx driver files

The following files contain the general Infineon XENSIV BGT60TRxx radar driver used to communicate with the BGT60TR13C radar sensor.

```text
src_NRF/sensors/mmwave/driver/
├── xensiv_bgt60trxx_platform.h
├── xensiv_bgt60trxx_regs.h
├── xensiv_bgt60trxx.c
└── xensiv_bgt60trxx.h
```

#### mmWave application layer

The following files implement the project-specific mmWave application interface. They wrap the lower-level radar driver and provide the functions used by the rest of the firmware to power, configure, start, stop, and read out the radar sensor.

```text
src_NRF/sensors/mmwave/
├── mmWave_appl.c
└── mmWave_appl.h
```

#### Sensor stubs

A stub file was added to provide weak function definitions for unused sensors. This avoids compilation warnings or linker errors without requiring large changes to the existing BioGAP firmware structure.

```text
src_NRF/stubs/
└── sensor_stubs.c
```

### Modified files

The following existing firmware files were modified to integrate the mmWave radar sensor into the BioGAP firmware and to improve compatibility with different sensor configurations.

The build system and configuration files were extended to include the mmWave sensor code and to allow sensor modules to be enabled or disabled through configuration options. In main.c, only the required hardware initialization was added. Runtime control of the mmWave sensor is handled through tasks and BLE commands.

```text
src_NRF/
├── CMakeLists.txt
├── Kconfig
├── nrf5340_senseiv1_cpuapp.overlay
├── prj.conf
└── main.c
```
The BLE command interface was extended to support mmWave control commands and raw radar data streaming.

```text
src_NRF/ble/
├── ble_commands.h
└── ble_appl.c
```

The power-management code was adjusted for the mmWave shield.

```text
src_NRF/bsp/
├── pwr_bsp.c
├── battery/battery.c
└── power/power.c
```

A detailed overview of the modified existing files and code-level changes, excluding newly added files, is available in [../Documentation/firmware_changes.md](../Documentation/firmware_changes.md).


### Added mmWave Functions

The following functions were added to control the mmWave radar subsystem:

| Function | Description |
|---|---|
| `mmWave_HW_init()` | Initializes the BGT60TR13C hardware interface |
| `mmWave_power_on()` | Enables power to the mmWave shield |
| `mmWave_power_off()` | Disables power to the mmWave shield |
| `mmWave_configure()` | Configures the BGT60TR13C radar sensor |
| `mmWave_start_streaming()` | Starts raw radar data streaming |
| `mmWave_stop_streaming()` | Stops raw radar data streaming |
| `mmWave_set_ifGain()` | Changes the radar IF gain setting |
| `mmWave_set_txPower()` | Changes the radar TX power level |
| `mmWave_set_fps()` | Changes the radar frame rate |

### Data format

The firmware streams raw radar frames with the following logical structure:

```text
num_rx_antennas × num_chirps × num_samples
```

On the host side, the data is reconstructed into NumPy arrays with shape:

```text
num_frames × num_rx_antennas × num_chirps × num_samples
```

For the final measurement configuration, the typical frame format was:

```text
1 RX antenna × 32 chirps × 8 samples
```

The raw ADC samples are 12-bit values and are packed before BLE transmission to reduce the required data bandwidth.



## License

The files in the Firmware/ directory contain third-party sources that come with their own licenses. See the respective folders and source files' headers for the licenses used.