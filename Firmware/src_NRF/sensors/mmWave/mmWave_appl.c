/*
 * -----------------------------------------------------------------------------
 *
 * File: mmwave_appl.c
 *
 * Copyright (C) 2026, ETH Zurich
 *
 * Authors:
 * - Benjamin Löliger, ETH Zurich
 *
 * -----------------------------------------------------------------------------
 * SPDX-License-Identifier: Apache-2.0
 *
 * Licensed under the Apache License, Version 2.0 (the License); you may
 * not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an AS IS BASIS, WITHOUT
 * WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * -----------------------------------------------------------------------------
 */

/**
 * @file mmwave_appl.c
 * @brief mmWave radar application layer implementation.
 *
 * This module implements the high-level control logic for the BGT60TR13C
 * mmWave radar sensor, including hardware initialization, power control,
 * radar configuration, parameter updates, and streaming control.
 */

#include <stdbool.h>
#include <stdint.h>
#include <zephyr/sys/__assert.h>
#include <zephyr/kernel.h>
#include <zephyr/logging/log.h>
#include <zephyr/drivers/spi.h>
#include <zephyr/toolchain.h>
#include <zephyr/sys/byteorder.h>
#include <hal/nrf_saadc.h>
#include <nrfx_spim.h>
#include <zephyr/irq.h>
#include <zephyr/sys/atomic.h>

// Include BLE application header for packet transmission
#include "ble/ble_appl.h"
#include "bsp/pwr_bsp.h"
#include "bsp/power/power.h"

#include "sensors/mmWave/mmWave_appl.h"
#include "sensors/mmWave/driver/xensiv_bgt60trxx.h"

#define XENSIV_BGT60TRXX_CONF_IMPL

/* Include the register header file here */
//include "sensors/mmWave/driver/25fps.h"
//include "sensors/mmWave/driver/50fps.h"
//include "sensors/mmWave/driver/100fps.h"
//include "sensors/mmWave/driver/150fps.h"
//include "sensors/mmWave/driver/200fps.h"
//include "sensors/mmWave/driver/static_distance.h"
#include "sensors/mmWave/driver/100fsp_32chirps_8samples_2000kHz.h"

/* Initialize the logging module */
LOG_MODULE_REGISTER(mmWave_appl, LOG_LEVEL_INF);

/*==============================================================================
 * Private Definitions
 *============================================================================*/

/** @brief Stack size of the mmWave streaming thread in bytes. */
#define mmWave_THREAD_STACK_SIZE 8192

/** @brief Thread priority of the mmWave streaming thread. */
#define mmWave_PRIORITY 6

/** @brief Enables BGT60TR13C internal test-pattern validation. */
#define TESTMODE false

/** @brief Selects packed 12-bit BLE transmission instead of 16-bit samples. */
#define MMWAVE_SEND_PACKED_12BIT true

/** @brief Number of ADC samples contained in one radar frame. */
#define NUM_SAMPLES_PER_FRAME   (XENSIV_BGT60TRXX_CONF_NUM_RX_ANTENNAS * \
                                XENSIV_BGT60TRXX_CONF_NUM_CHIRPS_PER_FRAME * \
                                XENSIV_BGT60TRXX_CONF_NUM_SAMPLES_PER_CHIRP)


/** @brief Unpacked frame size in bytes when samples are sent as uint16_t. */
#define FRAME_SIZE_BYTES_U16       (NUM_SAMPLES_PER_FRAME * sizeof(uint16_t))

/** @brief Packed frame size in bytes for 12-bit ADC samples. */
#define FRAME_SIZE_BYTES_PACKED    ((NUM_SAMPLES_PER_FRAME * 3U) / 2U)

/*Helpers for manipulating the register values and sending them via SPI to the Sensor*/
#define XENSIV_BGT60TRXX_SPI_REGADR_MSK                 (0xFE000000UL)
#define XENSIV_BGT60TRXX_SPI_REGADR_POS                 (25U)
#define XENSIV_BGT60TRXX_SPI_DATA_MSK                   (0x00FFFFFFUL)
#define XENSIV_BGT60TRXX_SPI_DATA_POS                   (0U)

#define TX_POWER_MASK 0x1F

/*MMWave BLE Packet defines for generating a payload*/
#define MMWAVE_HEADER       0xAA
#define MMWAVE_TRAILER      0x55
#define MMWAVE_HEADER_SIZE  8   // header + frame_idx + chunk + total + trailer
#define MMWAVE_DATA_SIZE    (BLE_PCKT_MAX_SIZE - MMWAVE_HEADER_SIZE) 


/** @brief Register 0x06 values for supported radar frame rates. */
static const uint32_t fps_reg0x06[] = {
  0x0d10207fUL, //0: 25fps
  0x0d1020ffUL, //1: 50fps
  0x0d1021ffUL, //2: 100fps
  0x0d10237fUL, //3: 150fps
  0x0d1024ffUL  //4: 200fps
};

/** @brief Register 0x02 values for supported radar frame rates. */
static const uint32_t fps_reg0x2d[] = {
  0x5b5de40aUL, // 0: 25fps
  0x5b616c0aUL, // 1: 50fps
  0x5b4d2c0aUL, // 2: 100fps
  0x5b46440aUL, // 3: 150fps
  0x5b4a1c0aUL  // 4: 200fps
};

/** @brief BGT60TR13C IF gain register values for the supported gain settings. */
static const uint32_t if_gain_regs[] = {
    0x25700c63UL, // 0: 18 dB
    0x25701ce7UL, // 1: 23 dB
    0x25702d6bUL, // 2: 28 dB
    0x25000c63UL, // 3: 30 dB

    0x25703defUL, // 4: 33 dB
    0x25001ce7UL, // 5: 35 dB
    0x25704e73UL, // 6: 38 dB
    0x25002d6bUL, // 7: 40 dB

    0x25705ef7UL, // 8: 43 dB
    0x25003defUL, // 9: 45 dB
    0x25706f7bUL, // 10: 48dB
    0x25004e73UL, // 11: 50dB

    0x25005ef7UL, // 12: 55dB
    0x25006f7bUL  // 13: 60dB
};
 
/*==============================================================================
 * Private Variables
 *============================================================================*/

/** @brief Current state of the mmWave application state machine. */
static volatile mmWave_state_t mmWave_state = mmWave_STATE_NO_HW;

/** @brief Currently selected IF gain register value. */
static uint32_t current_selected_gain_reg = 0x25703defUL;

/** @brief Currently selected TX power register value. */
static uint32_t current_tx_power_reg = 0x231ff41fUL;

/** @brief Currently selected frame-rate register value for register 0x06. */
static uint32_t current_fps_reg06 = 0x0d1021ffUL;
/** @brief Currently selected frame-rate register value for register 0x02. */
static uint32_t current_fps_reg2d = 0x5b4d2c0aUL;


/** @brief Controls whether the streaming loop should continue running. */
static volatile bool mmWave_keep_running = false;

/** @brief Semaphore used to start the mmWave streaming thread. */
static K_SEM_DEFINE(mmWave_start_sem, 0, 1);

/** @brief Semaphore signaled by the radar data-ready interrupt. */
static K_SEM_DEFINE(data_ready_mmWave_sem, 0, 1);

/** @brief Temporary buffer for packed 12-bit radar FIFO data. */
static uint8_t raw_bytes[FRAME_SIZE_BYTES_PACKED] __aligned(4);

/** @brief GPIO callback data structure for the BGT60TR13C data-ready interrupt. */
static struct gpio_callback irq_cb_data;

/** @brief BLE transmission buffer for one complete mmWave data packet. */
static uint8_t mmWave_tx_buf[MMWAVE_DATA_SIZE + MMWAVE_HEADER_SIZE];

/** @brief Unpacked radar sample buffer for one complete frame. */
static uint16_t samples[NUM_SAMPLES_PER_FRAME];

/** @brief Timestamp inserted into outgoing mmWave BLE packets. */
static uint32_t bgt_packet_timestamp = 0;

/** @brief BGT60TR13C driver instance. */
xensiv_bgt60trxx_t dev;

//GPIOS
static const struct gpio_dt_spec irq_pin = GPIO_DT_SPEC_GET(DT_NODELABEL(bgt60), irq_gpios);
static const struct gpio_dt_spec rst_pin = GPIO_DT_SPEC_GET(DT_NODELABEL(bgt60), reset_gpios);
static const struct gpio_dt_spec pwr_pin = GPIO_DT_SPEC_GET(DT_NODELABEL(bgt60), power_gpios);
static const struct gpio_dt_spec cs_pin  = GPIO_DT_SPEC_GET(DT_NODELABEL(bgt60), manual_cs_gpios);

//SPI
#define SPI_CONFIG		        SPI_WORD_SET(8) | SPI_TRANSFER_MSB
static const struct spi_dt_spec spi_cfg = SPI_DT_SPEC_GET(DT_NODELABEL(bgt60), SPI_CONFIG,0);


/*==============================================================================
 * Platform specific functions
 *============================================================================*/
void xensiv_bgt60trxx_platform_rst_set(const void* iface, bool val)
{
	gpio_pin_set_raw(rst_pin.port, rst_pin.pin, val ? 1 : 0);
}

void xensiv_bgt60trxx_platform_spi_cs_set(const void* iface, bool val)
{
	gpio_pin_set_raw(cs_pin.port, cs_pin.pin, val? 1 : 0);
}

int32_t xensiv_bgt60trxx_platform_spi_transfer(void* iface,
                                               uint8_t* tx_data,
                                               uint8_t* rx_data,
                                               uint32_t len)
{
	const struct spi_dt_spec *spi = (const struct spi_dt_spec *)iface;

	struct spi_buf tx_spi_buf		 	= {.buf = tx_data, .len = tx_data ? len : 0};
	struct spi_buf_set tx_spi_buf_set 	= {.buffers = &tx_spi_buf, .count = tx_data ? 1 : 0};

	struct spi_buf rx_spi_bufs 			= {.buf = rx_data, .len = rx_data ? len : 0};
	struct spi_buf_set rx_spi_buf_set	= {.buffers = &rx_spi_bufs, .count = rx_data ? 1 : 0};
	
	int err = spi_transceive_dt(spi, tx_data ? &tx_spi_buf_set : NULL, rx_data ? &rx_spi_buf_set : NULL);

	if (err == 0) {
    return XENSIV_BGT60TRXX_STATUS_OK;
  } else {
    return XENSIV_BGT60TRXX_STATUS_COM_ERROR;
  }
}

int32_t xensiv_bgt60trxx_platform_spi_fifo_read(void* iface, 
												uint16_t* rx_data, 
												uint32_t len)
{
    const struct spi_dt_spec *spi = (const struct spi_dt_spec *)iface;
    
    uint32_t byte_len = (len * 3) / 2; 
    
    struct spi_buf rx_spi_bufs = {.buf = raw_bytes, .len = byte_len};
    struct spi_buf_set rx_spi_buf_set = {.buffers = &rx_spi_bufs, .count = 1};

    int ret = spi_read_dt(spi, &rx_spi_buf_set);

    if (ret != 0) {
      return XENSIV_BGT60TRXX_STATUS_COM_ERROR;
    }

    uint32_t byte_idx = 0;

    for (uint32_t i = 0; i < len; i += 2) {

        if (byte_idx + 1 < byte_len) {
            rx_data[i] = (raw_bytes[byte_idx] << 4) | (raw_bytes[byte_idx + 1] >> 4);
        }

        if (i + 1 < len && byte_idx + 2 < byte_len) {
            rx_data[i+1] = ((raw_bytes[byte_idx + 1] & 0x0F) << 8) | raw_bytes[byte_idx + 2];
        }
        byte_idx += 3;
    }
    return XENSIV_BGT60TRXX_STATUS_OK;
}

void xensiv_bgt60trxx_platform_delay(uint32_t ms)
{
	k_msleep(ms);
}

uint32_t xensiv_bgt60trxx_platform_word_reverse(uint32_t x)
{
	return __builtin_bswap32(x);
}

void xensiv_bgt60trxx_platform_assert(bool expr)
{
	__ASSERT_NO_MSG(expr);
}

/*==============================================================================
 * Addon, Sync Signal Generator
 *============================================================================*/


#define FINAPRES_SYNC_NODE DT_ALIAS(finapres_sync)

#if !DT_NODE_HAS_STATUS(FINAPRES_SYNC_NODE, okay)
#error "finapres_sync alias is not defined in the devicetree"
#endif

static atomic_t finapres_sync_state = ATOMIC_INIT(0);

static const struct gpio_dt_spec finapres_sync =
    GPIO_DT_SPEC_GET(FINAPRES_SYNC_NODE, gpios);

#define SYNC_TOGGLE_PERIOD_MS 500

static struct k_timer sync_timer;
static struct k_work sync_work;

static bool sync_running = false;
static bool sync_state = false;

static void sync_work_handler(struct k_work *work)
{
    ARG_UNUSED(work);

    if (!sync_running) {
        return;
    }

    sync_state = !sync_state;
    gpio_pin_set_dt(&finapres_sync, sync_state);
}

static void sync_timer_handler(struct k_timer *timer)
{
    ARG_UNUSED(timer);

    int new_state = !atomic_get(&finapres_sync_state);

    atomic_set(&finapres_sync_state, new_state);
    k_work_submit(&sync_work);
}

int finapres_sync_init(void)
{
    if (!gpio_is_ready_dt(&finapres_sync)) {
        LOG_ERR("Finapres sync GPIO not ready");
        return -ENODEV;
    }

    int ret = gpio_pin_configure_dt(&finapres_sync, GPIO_OUTPUT_INACTIVE);
    if (ret != 0) {
        LOG_ERR("Failed to configure Finapres sync GPIO: %d", ret);
        return ret;
    }

    k_work_init(&sync_work, sync_work_handler);
    k_timer_init(&sync_timer, sync_timer_handler, NULL);

    LOG_INF("Finapres sync output initialized");

    return 0;
}

void finapres_sync_start(void)
{
    sync_state = false;
    sync_running = true;

    atomic_set(&finapres_sync_state, 0);
    gpio_pin_set_dt(&finapres_sync, 0);

    k_timer_start(
        &sync_timer,
        K_MSEC(SYNC_TOGGLE_PERIOD_MS),
        K_MSEC(SYNC_TOGGLE_PERIOD_MS)
    );

    LOG_INF("Finapres sync started");
}

void finapres_sync_stop(void)
{
    sync_running = false;

    k_timer_stop(&sync_timer);
    
    atomic_set(&finapres_sync_state, 0);
    gpio_pin_set_dt(&finapres_sync, 0);

    LOG_INF("Finapres sync stopped");
}

/*==============================================================================
 * Private Functions
 *============================================================================*/

/**
 * @brief GPIO interrupt callback for the BGT60TR13C data-ready signal.
 *
 * Signals the streaming thread that a new radar frame can be read from the FIFO.
 */
static void bgt60tr13c_irq_callback(const struct device *dev, struct gpio_callback *cb, uint32_t pins)
{   
  ARG_UNUSED(dev);
  ARG_UNUSED(cb);
  ARG_UNUSED(pins);
  
  k_sem_give(&data_ready_mmWave_sem);
}


/**
 * @brief Send a raw payload over BLE using the mmWave packet format.
 *
 * Splits the payload into BLE-sized chunks and adds the mmWave packet header,
 * timestamp, chunk index, total chunk count, and trailer.
 *
 * @param data Pointer to the payload data.
 * @param data_len Payload length in bytes.
 */
static void mmwave_send_payload(const uint8_t *data, uint32_t data_len)
{
    uint8_t total_chunks = (data_len + MMWAVE_DATA_SIZE - 1U) / MMWAVE_DATA_SIZE;

    bgt_packet_timestamp = k_cyc_to_us_floor32(k_cycle_get_32());
    uint8_t sync_state = (uint8_t)atomic_get(&finapres_sync_state) & 0x01;

    bgt_packet_timestamp = (bgt_packet_timestamp & ~0x01UL) | sync_state;    

    mmWave_tx_buf[0] = MMWAVE_HEADER;
    mmWave_tx_buf[1] = (uint8_t)((bgt_packet_timestamp >> 24) & 0xFF);
    mmWave_tx_buf[2] = (uint8_t)((bgt_packet_timestamp >> 16) & 0xFF);
    mmWave_tx_buf[3] = (uint8_t)((bgt_packet_timestamp >>  8) & 0xFF);
    mmWave_tx_buf[4] = (uint8_t)((bgt_packet_timestamp      ) & 0xFF);
    mmWave_tx_buf[6] = total_chunks;
    mmWave_tx_buf[243] = MMWAVE_TRAILER;

    for (uint8_t chunk = 0; chunk < total_chunks; chunk++) {
        uint32_t offset = chunk * MMWAVE_DATA_SIZE;
        uint32_t chunk_len = MIN(MMWAVE_DATA_SIZE, data_len - offset);

        mmWave_tx_buf[5] = chunk;

        memcpy(&mmWave_tx_buf[7], &data[offset], chunk_len);

        if (chunk_len < MMWAVE_DATA_SIZE) {
            memset(&mmWave_tx_buf[7 + chunk_len], 0, MMWAVE_DATA_SIZE - chunk_len);
        }

        add_data_to_send_buffer(mmWave_tx_buf, 244);
    }
}


/**
 * @brief Send the current radar frame as unpacked uint16_t samples.
 */
static void mmwave_send_frame_u16(void)
{
    mmwave_send_payload((const uint8_t *)samples, FRAME_SIZE_BYTES_U16);
}


/**
 * @brief Send the current radar frame as packed 12-bit ADC samples.
 */
static void mmwave_send_frame_packed(void)
{
    mmwave_send_payload((const uint8_t *)raw_bytes, FRAME_SIZE_BYTES_PACKED);
}


/**
 * @brief Synchronize configurable register values with the generated header.
 *
 * Reads the default IF gain, TX power, and frame-rate register values from the
 * generated BGT60TR13C register list so later runtime updates modify the correct
 * base values.
 */
static void mmWave_sync_config_from_header(void) {
  for (int i = 0; i < XENSIV_BGT60TRXX_CONF_NUM_REGS; i++) {
    uint8_t addr = (uint8_t)(register_list[i] >> 25);
    
    if (addr == 0x06) {
      current_fps_reg06 = register_list[i];
      LOG_INF("Synced fps reg06 from Header: 0x%08x", current_fps_reg06);
    }

    if (addr == 0x11) {
      current_tx_power_reg = register_list[i];
      LOG_INF("Synced tx_power from Header: 0x%08x", current_tx_power_reg);
    }

    if (addr == 0x12) {
      current_selected_gain_reg = register_list[i];
      LOG_INF("Synced Gain from Header: 0x%08x", current_selected_gain_reg);
    }

    if (addr == 0x2d) {
      current_fps_reg2d = register_list[i];
      LOG_INF("Synced fps reg2d from Header: 0x%08x", current_fps_reg2d);
      return;
    }

  }
  LOG_WRN("Gain Register 0x12 not found in header, using hardcoded default.");
}


/**
 * @brief Apply one full BGT60TR13C register value to the hardware.
 *
 * Extracts the register address and data field from the packed register value
 * used in the generated configuration header.
 *
 * @param dev Pointer to the BGT60TR13C driver instance.
 * @param full_reg Packed register value containing address and data.
 *
 * @return XENSIV_BGT60TRXX_STATUS_OK on success.
 * @return XENSIV_BGT60TRXX_STATUS_COM_ERROR on communication failure.
 */
static int mmWave_apply_reg_to_hw(xensiv_bgt60trxx_t* dev, uint32_t full_reg) {

  uint32_t reg_addr = ((full_reg & XENSIV_BGT60TRXX_SPI_REGADR_MSK) >>
                        XENSIV_BGT60TRXX_SPI_REGADR_POS);
  uint32_t reg_data = ((full_reg & XENSIV_BGT60TRXX_SPI_DATA_MSK) >>
                        XENSIV_BGT60TRXX_SPI_DATA_POS);

  int ret = xensiv_bgt60trxx_set_reg(dev, reg_addr, reg_data);
    
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("write failed");
  } else {
    LOG_DBG("Register updated");
  }
  return ret;
}


/**
 * @brief Apply the currently selected IF gain register value to the radar.
 */
static int mmWave_apply_gain_to_hw(xensiv_bgt60trxx_t* dev) {

  uint32_t full_reg = current_selected_gain_reg;
  
  return mmWave_apply_reg_to_hw(dev, full_reg);
}


/**
 * @brief Apply the currently selected TX power register value to the radar.
 */
static int mmWave_apply_tx_power_to_hw(xensiv_bgt60trxx_t* dev) {

  uint32_t full_reg = current_tx_power_reg;
  
  return mmWave_apply_reg_to_hw(dev, full_reg);
}

/**
 * @brief Apply the currently selected frame-rate register values to the radar.
 */
static int mmWave_apply_fps_to_hw(xensiv_bgt60trxx_t* dev) {

  uint32_t full_reg = current_fps_reg06;

  int ret = mmWave_apply_reg_to_hw(dev, full_reg);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("Failed to apply FPS register 0x06: %d", ret);
    return ret;
  }

  full_reg = current_fps_reg2d;

  ret = mmWave_apply_reg_to_hw(dev, full_reg);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("Failed to apply FPS register 0x02: %d", ret);
    return ret;
  }

  return ret;
}


/**
 * @brief Main mmWave streaming thread.
 *
 * Waits for a start signal, starts radar frame acquisition, reads frames on each
 * data-ready interrupt, and forwards the received data over BLE until streaming
 * is stopped.
 */
static void mmWave_streaming_thread(void *arg1, void *arg2, void *arg3) {
  ARG_UNUSED(arg1);
  ARG_UNUSED(arg2);
  ARG_UNUSED(arg3);

  int ret;
  uint32_t frame_idx = 0;
	uint32_t errors = 0;
  uint16_t test_word = XENSIV_BGT60TRXX_INITIAL_TEST_WORD;
	

  LOG_INF("mmWave streaming thread started");

  while (1) {
    /* Wait for start signal */
    k_sem_take(&mmWave_start_sem, K_FOREVER);
    frame_idx = 0; 
    
    ret = xensiv_bgt60trxx_soft_reset(&dev, XENSIV_BGT60TRXX_RESET_FIFO);
    if(ret != 0) {
      LOG_ERR("Soft Reset failed: %d", ret);
      mmWave_state = mmWave_STATE_ERROR;
      continue;
    }

    finapres_sync_start();
    
    ret = xensiv_bgt60trxx_start_frame(&dev, true);
    if(ret != 0) {
      LOG_ERR("Starting frame capture failed: %d", ret);
      mmWave_state = mmWave_STATE_ERROR;
      continue;
    }

    LOG_INF("Starting mmWave capture");
    mmWave_state = mmWave_STATE_STREAMING;

    while (mmWave_keep_running) {
      
      if (k_sem_take(&data_ready_mmWave_sem, K_MSEC(1000)) != 0) {
        LOG_ERR("IRQ timeout - no data");
        break;
      }

      if(xensiv_bgt60trxx_get_fifo_data(&dev, samples, NUM_SAMPLES_PER_FRAME)== XENSIV_BGT60TRXX_STATUS_OK) {
    	/* IF TESTMODE we check data recived against testword*/
        if(TESTMODE) {
          for (int32_t sample_idx = 0; sample_idx < NUM_SAMPLES_PER_FRAME; ++sample_idx) {
            if (test_word != samples[sample_idx]) {
              if (errors == 0){
                LOG_WRN("Frame %u error detected. "
                        "Expected: %u "
                        "Received: %u \n",
                        frame_idx, test_word, samples[sample_idx]);
              }
              errors++;
            }
            // Generate next test_word
            test_word = xensiv_bgt60trxx_get_next_test_word(test_word);
          }
        }
        #if MMWAVE_SEND_PACKED_12BIT
            mmwave_send_frame_packed();
        #else
            mmwave_send_frame_u16();
        #endif
            frame_idx++;
      }

      if(TESTMODE && frame_idx%25 == 0) {
			  if(TESTMODE) {
				  LOG_INF("%u errors in the last 25 frames\r\n", errors);
				  errors = 0;
			  } else {	
				  LOG_HEXDUMP_INF(samples, 6, "RAW DATA BYTES:");
			  }
		  }
    }

    mmWave_state = mmWave_STATE_STOPPING;
    
    ret = xensiv_bgt60trxx_start_frame(&dev, false);
    if(ret != 0) {
      LOG_ERR("Stopping frame capture failed: %d", ret);
      mmWave_state = mmWave_STATE_ERROR;
      continue;
    }

    finapres_sync_stop();

    ret = xensiv_bgt60trxx_soft_reset(&dev, XENSIV_BGT60TRXX_RESET_FIFO);
    if(ret != 0) {
      LOG_ERR("Soft Reset failed: %d", ret);
      mmWave_state = mmWave_STATE_ERROR;
      continue;
    }

    mmWave_state = mmWave_STATE_CONFIGURED;
    LOG_INF("mmWave streaming stopped");
  }
}

/*==============================================================================
 * Thread Definition
 *============================================================================*/

K_THREAD_DEFINE(mmWave_thread_id, mmWave_THREAD_STACK_SIZE, mmWave_streaming_thread, NULL, NULL, NULL, mmWave_PRIORITY, 0, 0);

/*==============================================================================
 * Public Functions - Initialization & Configuration
 *============================================================================*/

int mmWave_HW_init() {

  int ret;
  if (mmWave_state != mmWave_STATE_NO_HW) {
    LOG_DBG("mmWave HW already initialized");
    return -EALREADY;
  }

  ret = finapres_sync_init();
  if (ret != 0) {
    LOG_ERR("Failed to init Finapres sync: %d", ret);
    return ret;
  }

  LOG_INF("Starting mmWave HW initialization...");

  if (!gpio_is_ready_dt(&irq_pin) || !gpio_is_ready_dt(&rst_pin) ||
      !gpio_is_ready_dt(&pwr_pin) || !gpio_is_ready_dt(&cs_pin)  ||
      !spi_is_ready_dt(&spi_cfg)) {
    LOG_ERR("Hardware devices not ready");
	  return -ENODEV;
  }


  ret = gpio_pin_configure_dt(&irq_pin, GPIO_INPUT);
  if (ret < 0) {
    LOG_ERR("Failed to configure GPIO pin %d (error %d)", irq_pin.pin, ret);
    return ret;
  }
  gpio_init_callback(&irq_cb_data, bgt60tr13c_irq_callback, BIT(irq_pin.pin));
	gpio_add_callback(irq_pin.port, &irq_cb_data);

  //Init the n_cs and n_rst as ACTIVE, so no voltag at GPIOs of BGT present during startup
  ret = gpio_pin_configure_dt(&rst_pin, GPIO_OUTPUT_ACTIVE);
  if (ret < 0) {
    LOG_ERR("Failed to configure GPIO pin %d (error %d)", rst_pin.pin, ret);
    return ret;
  }

  ret = gpio_pin_configure_dt(&cs_pin, GPIO_OUTPUT_ACTIVE); 
  if (ret < 0) {
    LOG_ERR("Failed to configure GPIO pin %d (error %d)", cs_pin.pin, ret);
    return ret;
  }
  
  //Power pin init as GPIO Disconnected so ADC function remains
  ret = gpio_pin_configure_dt(&pwr_pin, GPIO_DISCONNECTED);
  if (ret < 0) {
    LOG_ERR("Failed to configure GPIO pin %d (error %d)", pwr_pin.pin, ret);
    return ret;
  }

  mmWave_sync_config_from_header();

  mmWave_state = mmWave_STATE_HW_ACTIVE; 
  return 0;
}

int mmWave_power_on() {

  if(mmWave_state != mmWave_STATE_HW_ACTIVE) {
    LOG_ERR("HW not ready or already on");
    return -EPERM;
  }

  //take over PWR Pin
  nrf_saadc_channel_input_set(NRF_SAADC, 0, 
  NRF_SAADC_INPUT_DISABLED, 
  NRF_SAADC_INPUT_DISABLED);
  
  gpio_pin_configure_dt(&pwr_pin, GPIO_OUTPUT_ACTIVE);
  gpio_pin_set_dt(&pwr_pin, 1);

  /* Perform hard reset. */
  k_msleep(5);
  gpio_pin_set_dt(&cs_pin,  0);
  gpio_pin_set_dt(&rst_pin, 0);
  k_msleep(1);
  gpio_pin_set_dt(&rst_pin, 1);
  k_msleep(1);
  gpio_pin_set_dt(&rst_pin, 0);
  k_msleep(1);

  //Init device driver
  int ret = xensiv_bgt60trxx_init(&dev, (void *)&spi_cfg, false);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
      LOG_ERR("BGT60 Init Error: %d", ret);
      return -EIO;
  }

  mmWave_state = mmWave_STATE_IDLE;
  LOG_INF("mmWave powered on and ready for config.");
  return 0;
}

int mmWave_configure() {

  if(mmWave_state != mmWave_STATE_IDLE && mmWave_state != mmWave_STATE_CONFIGURED) {
    LOG_ERR("Device not ready for configuration");
    return -EPERM;
  }

  //Configures the XENSIV(TM) BGT60TRxx radar sensor device.
	int ret = xensiv_bgt60trxx_config(&dev, register_list, XENSIV_BGT60TRXX_CONF_NUM_REGS);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("BGT60 Config Error: %d", ret);
    return -EIO;
  }

  ret = mmWave_apply_gain_to_hw(&dev);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("Failed to set ifGain: %d", ret);
    return -EIO;
  }

  ret = mmWave_apply_tx_power_to_hw(&dev);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("Failed to set tx_power: %d", ret);
    return -EIO;
  }

  ret = mmWave_apply_fps_to_hw(&dev);
  if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
    LOG_ERR("Failed to set fps: %d", ret);
    return -EIO;
  }


  xensiv_bgt60trxx_set_fifo_limit(&dev, NUM_SAMPLES_PER_FRAME);
  xensiv_bgt60trxx_enable_data_test_mode(&dev, TESTMODE);

  gpio_pin_interrupt_configure_dt(&irq_pin, GPIO_INT_EDGE_TO_ACTIVE);
	
  k_msleep(3);
  mmWave_state = mmWave_STATE_CONFIGURED;
  LOG_INF("mmWave configured successfully.");
  return 0;
}

int mmWave_power_off() {

  if(mmWave_state == mmWave_STATE_STREAMING ||
     mmWave_state == mmWave_STATE_STOPPING) {
     LOG_ERR("Device still Streaming");
    return -EPERM;
  }

  /* Disable interrupt. */
  gpio_pin_interrupt_configure_dt(&irq_pin, GPIO_INT_DISABLE);

  //disable all power, also to gpios
  gpio_pin_set_dt(&rst_pin, 1); 
  gpio_pin_set_dt(&cs_pin, 1); 
  gpio_pin_set_dt(&pwr_pin, 0);
  
  k_msleep(5);

  gpio_pin_configure_dt(&pwr_pin, GPIO_DISCONNECTED);


  nrf_saadc_channel_input_set(NRF_SAADC, 0, 
  NRF_SAADC_INPUT_AIN3, 
  NRF_SAADC_INPUT_DISABLED);

  mmWave_state = mmWave_STATE_HW_ACTIVE;
  LOG_INF("mmWave powered down, pin freed for ADC.");
  return 0;
}

int mmWave_set_ifGain(uint8_t ifGain) {

  switch (ifGain) {
    case 18: current_selected_gain_reg = if_gain_regs[0]; break;
    case 23: current_selected_gain_reg = if_gain_regs[1]; break;
    case 28: current_selected_gain_reg = if_gain_regs[2]; break;
    case 30: current_selected_gain_reg = if_gain_regs[3];  break;
    case 33: current_selected_gain_reg = if_gain_regs[4];  break;
    case 35: current_selected_gain_reg = if_gain_regs[5];  break;
    case 38: current_selected_gain_reg = if_gain_regs[6];  break;
    case 40: current_selected_gain_reg = if_gain_regs[7];  break;
    case 43: current_selected_gain_reg = if_gain_regs[8];  break;
    case 45: current_selected_gain_reg = if_gain_regs[9];  break;
    case 48: current_selected_gain_reg = if_gain_regs[10]; break;
    case 50: current_selected_gain_reg = if_gain_regs[11]; break;
    case 55: current_selected_gain_reg = if_gain_regs[12]; break;
    case 60: current_selected_gain_reg = if_gain_regs[13]; break;
    
    default:
      LOG_ERR("Invalid Gain value: %d dB", ifGain);
      return -EINVAL;
  }

  if (mmWave_state == mmWave_STATE_CONFIGURED) {
    
    int ret = mmWave_apply_gain_to_hw(&dev);

    if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
      LOG_ERR("Failed to update Gain on the fly");
      return -EIO;
    }
    LOG_INF("IF Gain updated to %d dB", ifGain);

  } else {
    LOG_INF("Gain saved. Will be applied on next power-on/config.");
  }
  return 0;
}

int mmWave_set_txPower(uint8_t txPower) {
  if (txPower > TX_POWER_MASK) {
    LOG_ERR("Tx Power Level: %d not within range 0-31", txPower);
    return -EINVAL;
  }

  current_tx_power_reg &= ~TX_POWER_MASK;             /* Clear lower 5 bits. */
  current_tx_power_reg |= (txPower & TX_POWER_MASK);  /* Set new TX power. */

  if (mmWave_state == mmWave_STATE_CONFIGURED) {
    int ret = mmWave_apply_tx_power_to_hw(&dev);

    if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
      LOG_ERR("Failed to update tx power on the fly");
      return -EIO;
    }
    LOG_INF("TX power updated to %d ", txPower);

  } else {
    LOG_INF("tx power saved. Will be applied on next power-on/config.");
  }
  return 0;
}

int mmWave_set_fps(uint8_t fps) {

  switch (fps) {
    case 25: 
      current_fps_reg06 = fps_reg0x06[0]; 
      current_fps_reg2d = fps_reg0x2d[0];
      break;
    case 50: 
      current_fps_reg06 = fps_reg0x06[1]; 
      current_fps_reg2d = fps_reg0x2d[1];
      break;
    case 100: 
      current_fps_reg06 = fps_reg0x06[2]; 
      current_fps_reg2d = fps_reg0x2d[2];
      break;
    case 150: 
      current_fps_reg06 = fps_reg0x06[3]; 
      current_fps_reg2d = fps_reg0x2d[3];
      break;
    case 200:
      current_fps_reg06 = fps_reg0x06[4]; 
      current_fps_reg2d = fps_reg0x2d[4];
      break;

    default:
      LOG_ERR("Invalid fps value: %d fps", fps);
      return -EINVAL;
  }

  if (mmWave_state == mmWave_STATE_CONFIGURED) {
    
    int ret = mmWave_apply_fps_to_hw(&dev);

    if (ret != XENSIV_BGT60TRXX_STATUS_OK) {
      LOG_ERR("Failed to update fps on the fly");
      return -EIO;
    }
    LOG_INF("fps updated to %d fps", fps);

  } else {
    LOG_INF("fps saved. Will be applied on next power-on/config.");
  }
  return 0;
}



int mmWave_start_streaming(void) {
  if (mmWave_state == mmWave_STATE_STREAMING) {
    LOG_WRN("mmWave already streaming");
    return -EALREADY;
  }

  if (mmWave_state != mmWave_STATE_CONFIGURED) {
    LOG_ERR("mmWave not in configured state (current: %d)", mmWave_state);
    return -EBUSY;
  }

  mmWave_keep_running = true;
  k_sem_give(&mmWave_start_sem);

  return 0;
}

int mmWave_stop_streaming(void) {
  if (mmWave_state != mmWave_STATE_STREAMING) {
    LOG_WRN("mmWave not streaming");
    return -EINVAL;
  }

  mmWave_keep_running = false;

  /* Wait for the streaming thread to stop */
  int timeout = 100; /* 1 second timeout (100 * 10ms) */
  while (mmWave_state != mmWave_STATE_CONFIGURED && timeout > 0) {
    k_msleep(10);
    timeout--;
  }

  if (timeout == 0) {
    LOG_ERR("Timeout waiting for mmWave to stop");
    return -ETIMEDOUT;
  }

  return 0;
}


