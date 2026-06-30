
# mmWave Stream Demo

This folder contains the firmware to use BioGAP in streaming mode.

## Getting Started
Make sure to attach the e Mainboard to the mmWave shield.

1. Flash the NRF application by opening it in Visual Studio Code using the NRF Connect SDK extension.
```sh
cd src_NRF
west build -b nrf5340_senseiv1_cpuapp
west flash
```

Make sure your `SENSEI_SDK_ROOT` environment variable is set to the path of the SENSEI SDK.

## License

The files in the Firmware/ directory contain third-party sources that come with their own licenses. See the respective folders and source files' headers for the licenses used.