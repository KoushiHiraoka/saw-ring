#include <Arduino.h>
#include "driver/i2s.h"

// 使用する I2S ポート
#define I2S_PORT           I2S_NUM_0

// I2S 設定
#define SAMPLE_RATE        24000                // 音声サンプルレート
#define BITS_PER_SAMPLE    I2S_BITS_PER_SAMPLE_16BIT
#define DMA_BUF_COUNT      4
#define DMA_BUF_LEN        256                  // 16bit ワード ×256 = 512Byte

// 配線したピン番号
const int I2S_BCK_PIN     = 26;  // VPU の CLK
const int I2S_WS_PIN      = I2S_PIN_NO_CHANGE; // PDM では WS は使わない
const int I2S_DATA_IN_PIN = 25;  // レベルシフタ経由で VPU の DATA

void setup() {
  Serial.begin(921600);
  delay(500);

  // 1) I2S ドライバのインストール
  i2s_config_t i2s_config;
  i2s_config.mode               = i2s_mode_t(I2S_MODE_MASTER | I2S_MODE_RX);
  i2s_config.sample_rate        = SAMPLE_RATE;
  i2s_config.bits_per_sample    = BITS_PER_SAMPLE;
  i2s_config.channel_format     = I2S_CHANNEL_FMT_ONLY_LEFT;
  i2s_config.communication_format = I2S_COMM_FORMAT_I2S_MSB;
  i2s_config.intr_alloc_flags   = 0;
  i2s_config.dma_buf_count      = DMA_BUF_COUNT;
  i2s_config.dma_buf_len        = DMA_BUF_LEN;
  i2s_config.use_apll           = false;

  esp_err_t err = i2s_driver_install(I2S_PORT, &i2s_config, 0, NULL);
  if (err != ESP_OK) {
    Serial.printf("Error installing I2S driver: %d\n", err);
    while (true) delay(10);
  }

  // 2) ピンマッピング
  i2s_pin_config_t pin_config;
  pin_config.bck_io_num   = I2S_BCK_PIN;
  pin_config.ws_io_num    = I2S_WS_PIN;
  pin_config.data_out_num = I2S_PIN_NO_CHANGE;
  pin_config.data_in_num  = I2S_DATA_IN_PIN;

  err = i2s_set_pin(I2S_PORT, &pin_config);
  if (err != ESP_OK) {
    Serial.printf("Error setting I2S pins: %d\n", err);
    while (true) delay(10);
  }

  // 3) DMA バッファクリア
  i2s_zero_dma_buffer(I2S_PORT);
}

void loop() {
  // 4) PDM ビットストリームの読み出し
  static int16_t pdm_buf[DMA_BUF_LEN];
  size_t bytes_read = 0;
  esp_err_t err = i2s_read(I2S_PORT,
                           (void*)pdm_buf,
                           sizeof(pdm_buf),
                           &bytes_read,
                           portMAX_DELAY);
  if (err != ESP_OK) {
    Serial.printf("I2S read error: %d\n", err);
    return;
  }

  int words = bytes_read / sizeof(int16_t);
  const int DECIMATE = 32;  // 簡易デシメーション幅
  int samples = words / DECIMATE;

  // 5) 簡易デシメーション + シリアル出力
  for (int i = 0; i < samples; i++) {
    int sum = 0;
    for (int j = 0; j < DECIMATE; j++) {
      // PDM ビットは 16bit ワードの MSB
      sum += (pdm_buf[i * DECIMATE + j] & 0x8000) ? 1 : 0;
    }
    // 0～1 の振幅に正規化してから signed 16bit にスケーリング
    float norm = float(sum) / DECIMATE;      
    int16_t pcm = int16_t((norm * 2.0f - 1.0f) * 32767);

    Serial.write((uint8_t*)&pcm, sizeof(pcm));
  }
}
