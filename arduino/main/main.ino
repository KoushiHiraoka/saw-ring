#include "driver/i2s_pdm.h" // I2S PDM関連のヘッダー
#include "driver/gpio.h"    // GPIO関連のヘッダー

// I2Sチャンネルハンドル
i2s_chan_handle_t rx_handle;

// PDMマイクから読み取るPCMデータのバッファサイズ（バイト単位）
// 16bitモノラルデータなので、1024サンプル = 1024 * 2バイト
const int SAMPLE_BUFFER_SIZE_BYTES = 2048; // 1024サンプル * 2バイト/サンプル (16ビット)
int16_t sampleBuffer[SAMPLE_BUFFER_SIZE_BYTES / sizeof(int16_t)]; // int16_t型配列

void setup() {
  // シリアル通信の初期化（ボーレートは高速推奨）
  Serial.begin(115200);
  while (!Serial);
  Serial.println("Starting I2S PDM RX...");

  // --- I2Sチャンネルの割り当てと初期化 ---
  // I2Sチャンネルの設定 (I2S0をマスターモードでRXチャンネルとして使用)
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
  // RXチャンネルを新規作成
  esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &rx_handle);
  if (err != ESP_OK) {
    Serial.printf("Failed to create I2S RX channel: %s\n", esp_err_to_name(err));
    while(true); // エラー発生時は停止
  }

  // --- PDM RXモードの初期化設定 ---
  i2s_pdm_rx_config_t pdm_rx_cfg = {
      // クロック設定：PCMサンプルレートを24kHzに設定
      .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(24000),
      .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
      .gpio_cfg = {
          .clk = GPIO_NUM_3,
          .din = GPIO_NUM_1,
          .invert_flags = {
              .clk_inv = false, // クロックは反転しない
          },
      },
  };

  // PDM RXモードでI2Sチャンネルを初期化
  err = i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_rx_cfg);
  if (err != ESP_OK) {
    Serial.printf("Failed to initialize PDM RX mode: %s\n", esp_err_to_name(err));
    while(true); // エラー発生時は停止
  }

  // I2Sチャンネルの開始
  err = i2s_channel_enable(rx_handle);
  if (err != ESP_OK) {
    Serial.printf("Failed to start I2S channel: %s\n", esp_err_to_name(err));
    while(true); // エラー発生時は停止
  }

  Serial.println("I2S PDM RX started successfully.");
}

void loop() {
  size_t bytes_read; // 実際に読み取ったバイト数を格納する変数

  // I2SチャンネルからPDMデータをPCM形式に変換して読み取る
  // sampleBufferにSAMPLE_BUFFER_SIZE_BYTES分のデータを読み込み
  esp_err_t err = i2s_channel_read(rx_handle, sampleBuffer, SAMPLE_BUFFER_SIZE_BYTES, &bytes_read, portMAX_DELAY);

  if (err == ESP_OK) {
    if (bytes_read > 0) {
      // 読み取ったPCMデータをシリアルポートにバイナリ形式で送信
      // PCMデータは生のバイナリデータなので、print/printlnではなくwriteを使用
      Serial.write((uint8_t*)sampleBuffer, bytes_read);
    }
  } else {
    Serial.printf("Failed to read from I2S channel: %s\n", esp_err_to_name(err));
  }
}