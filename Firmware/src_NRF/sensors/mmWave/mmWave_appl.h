#ifndef MMWAVE_APPL_H
#define MMWAVE_APPL_H

#include <stdbool.h>
#include <stdint.h>



/*==============================================================================
 * Type Definitions
 *============================================================================*/

/**
 * @enum mmWave_state_t
 * @brief mmWave Device states
 */
typedef enum {
    mmWave_STATE_NO_HW,     /**< mmWave off, HW not ready, initial state */
    mmWave_STATE_HW_ACTIVE, /**< mmWave off, HW ready */
    mmWave_STATE_IDLE,      /**< mmWave on, not configured */
    mmWave_STATE_CONFIGURED,/**< mmWave configured, not streaming */
    mmWave_STATE_STREAMING, /**< mmWave actively streaming data */
    mmWave_STATE_STOPPING,  /**< mmWave stopping */
    mmWave_STATE_ERROR      /**< Error state */
} mmWave_state_t;

/*==============================================================================
 * Function Declarations
 *============================================================================*/

/**
 * @brief Initialize the mmWave hardware.
 *
 * Initializes the BGT60TR13C sensor hardware interface.
 * Must be called before mmWave_power_on().
 *
 * @return 0 on success.
 * @return -EALREADY if the hardware has already been initialized.
 * @return Negative error code on other failures.
 */
int mmWave_HW_init(void); 


/**
 * @brief Power on the mmWave system.
 *
 * Enables power to the BGT60TR13C sensor hardware. After this call, the
 * sensor is powered and ready to be configured.
 *
 * Must be called before mmWave_configure().
 *
 * While the mmWave system is powered on, the power control pin is reserved
 * for the mmWave subsystem and cannot be used by the ADC to read the battery
 * status.
 *
 * @return 0 on success.
 * @return -EALREADY if the mmWave system is already powered on.
 * @return Negative error code on other failures.
 */
int mmWave_power_on(void);


/**
 * @brief Configure the mmWave sensor.
 *
 * Configures the BGT60TR13C sensor and prepares it for streaming.
 *
 * Must be called before mmWave_start_streaming() after the sensor has been
 * powered on. If the system was powered off, it must be configured again
 * after the next mmWave_power_on() call.
 *
 * @return 0 on success.
 * @return -EBUSY if the device is currently streaming.
 * @return Negative error code on other failures.
 */
int mmWave_configure(void);


/**
 * @brief Power off the mmWave system.
 *
 * Disables power to the BGT60TR13C sensor and releases the power control pin
 * for use by other subsystems.
 *
 * After powering the system off and on again, mmWave_configure() must be
 * called before streaming can be started.
 *
 * @return 0 on success.
 * @return -EBUSY if the device is currently streaming.
 * @return Negative error code on other failures.
 */
int mmWave_power_off(void);


/**
 * @brief Change ifGain of the ADCs
 *
 * Updates the IF gain register(only first shape) value without requiring a separate
 * configuration header file.
 *
 * If the device has already been configured, this function attempts to
 * reconfigure the device with the new IF gain value and stores the value for
 * future configuration calls.
 *
 * If the device has not been configured yet, this function only stores the new
 * IF gain value. The value will then be applied during the next configuration.
 *
 * @param ifGain IF gain value in dB. Must be one of the supported gain values.
 *
 * @return 0 on success.
 * @return -EINVAL if the IF gain value is not supported.
 * @return Negative error code on other failures.
 */
int mmWave_set_ifGain(uint8_t ifGain);


/**
 * @brief Change ifGain of the ADCs
 *
 * Updates the txPower register(only first shape) value without requiring a separate
 * configuration header file.
 *
 * If the device has already been configured, this function attempts to
 * reconfigure the device with the new txPower value and stores the value for
 * future configuration calls.
 *
 * If the device has not been configured yet, this function only stores the new
 * tx Power value. The value will then be applied during the next configuration.
 *
 * @param txPower txPower level. Must be between 0-31.
 *
 * @return 0 on success.
 * @return -EINVAL if the txPower value is not supported.
 * @return Negative error code on other failures.
 */
int mmWave_set_txPower(uint8_t txPower);




int mmWave_set_fps(uint8_t fps);


/**
 * @brief Start mmWave streaming.
 *
 * Starts the mmWave data stream.
 *
 * @return 0 on success.
 * @return -EALREADY if streaming is already active.
 * @return -EBUSY if the device is not in the idle state.
 * @return Negative error code on other failures.
 */
int mmWave_start_streaming(void);


/**
 * @brief Stop mmWave streaming.
 *
 * Stops the active mmWave data stream.
 *
 * @return 0 on success.
 * @return -EINVAL if streaming is not currently active.
 * @return -ETIMEDOUT if the stop operation times out.
 * @return Negative error code on other failures.
 */
int mmWave_stop_streaming(void);


#endif 