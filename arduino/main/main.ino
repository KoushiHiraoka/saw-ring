#include "driver/i2s_pdm.h"

// I2Sピンの設定
#define I2S_PDM_CLK_IO      (GPIO_NUM_3)  // CLK
#define I2S_PDM_DIN_IO      (GPIO_NUM_1)  // DATA

// I2S設定
#define I2S_PORT            (I2S_NUM_0)   
#define SAMPLE_RATE         (44100)       
#define BITS_PER_SAMPLE     (16)          
#define BUFFER_SIZE         (2048)

int16_t i2s_read_buff[BUFFER_SIZE / sizeof(int16_t)];
i2s_chan_handle_t rx_handle; // 受信チャンネルのハンドル用変数

void setup(){
  Serial.begin(921600);

  // I2S PDM RXチャンネル
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_PORT, I2S_ROLE_MASTER);
  ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));  

  // PDM RXモードの設定
  i2s_pdm_rx_config_t pdm_rx_cfg = {
      .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
      .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
      .gpio_cfg = {
          .clk = I2S_PDM_CLK_IO,
          .din = I2S_PDM_DIN_IO,
          .invert_flags = {
              .clk_inv = false,
          },
      },
  };
  
  ESP_ERROR_CHECK(i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_rx_cfg));
  ESP_ERROR_CHECK(i2s_channel_enable(rx_handle));

  Serial.println("I2S PDM RX 有効化");

}

void loop() {
  size_t bytes_read = 0;
  // PCM from I2S
  esp_err_t ret = i2s_channel_read(rx_handle, i2s_read_buff, BUFFER_SIZE, &bytes_read, (100)); // タイムアウトを100msに設定
  if (ret == ESP_OK && bytes_read > 0) {
    // 読み込んだPCMデータをバイナリのままシリアルポートに書き出す
    Serial.write((uint8_t*)i2s_read_buff, bytes_read);
  }
  
  // if (ret == ESP_OK && bytes_read > 0) {
  //   for (int i = 0; i < bytes_read / 2; i++) {
  //       Serial.print(i2s_read_buff[i]);
  //       if (i < (bytes_read / 2) - 1) {
  //           Serial.print(","); // 数値をカンマで区切る
  //       }
  //   }
  //   Serial.println();
  // }

}









// #include "driver/i2s_pdm.h" // I2S PDM関連のヘッダー
// #include "driver/gpio.h"    // GPIO関連のヘッダー

// // I2Sチャンネルハンドル
// i2s_chan_handle_t rx_handle;

// // PDMマイクから読み取るPCMデータのバッファサイズ（バイト単位）
// // 16bitモノラルデータなので、1024サンプル = 1024 * 2バイト
// const int SAMPLE_BUFFER_SIZE_BYTES = 2048; // 1024サンプル * 2バイト/サンプル (16ビット)
// int16_t sampleBuffer[SAMPLE_BUFFER_SIZE_BYTES / sizeof(int16_t)]; // int16_t型配列

// void setup() {
//   // シリアル通信の初期化（ボーレートは高速推奨）
//   Serial.begin(115200);
//   while (!Serial);
//   Serial.println("Starting I2S PDM RX...");

//   // --- I2Sチャンネルの割り当てと初期化 ---
//   // I2Sチャンネルの設定 (I2S0をマスターモードでRXチャンネルとして使用)
//   i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_NUM_0, I2S_ROLE_MASTER);
//   // RXチャンネルを新規作成
//   esp_err_t err = i2s_new_channel(&chan_cfg, NULL, &rx_handle);
//   if (err != ESP_OK) {
//     Serial.printf("Failed to create I2S RX channel: %s\n", esp_err_to_name(err));
//     while(true); // エラー発生時は停止
//   }

//   // --- PDM RXモードの初期化設定 ---
//   i2s_pdm_rx_config_t pdm_rx_cfg = {
//       // クロック設定：PCMサンプルレートを24kHzに設定
//       .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(24000),
//       .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
//       .gpio_cfg = {
//           .clk = GPIO_NUM_6,
//           .din = GPIO_NUM_5,
//           .invert_flags = {
//               .clk_inv = false, // クロックは反転しない
//           },
//       },
//   };

//   // PDM RXモードでI2Sチャンネルを初期化
//   err = i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_rx_cfg);
//   if (err != ESP_OK) {
//     Serial.printf("Failed to initialize PDM RX mode: %s\n", esp_err_to_name(err));
//     while(true); // エラー発生時は停止
//   }

//   // I2Sチャンネルの開始
//   err = i2s_channel_enable(rx_handle);
//   if (err != ESP_OK) {
//     Serial.printf("Failed to start I2S channel: %s\n", esp_err_to_name(err));
//     while(true); // エラー発生時は停止
//   }

//   Serial.println("I2S PDM RX started successfully.");
// }

// void loop() {
//   size_t bytes_read; // 実際に読み取ったバイト数を格納する変数

//   // I2SチャンネルからPDMデータをPCM形式に変換して読み取る
//   // sampleBufferにSAMPLE_BUFFER_SIZE_BYTES分のデータを読み込み
//   esp_err_t err = i2s_channel_read(rx_handle, sampleBuffer, SAMPLE_BUFFER_SIZE_BYTES, &bytes_read, portMAX_DELAY);

//   if (err == ESP_OK) {
//     if (bytes_read > 0) {
//       // 読み取ったPCMデータをシリアルポートにバイナリ形式で送信
//       // PCMデータは生のバイナリデータなので、print/printlnではなくwriteを使用
//       Serial.write((uint8_t*)sampleBuffer, bytes_read);
//     }
//   } else {
//     Serial.printf("Failed to read from I2S channel: %s\n", esp_err_to_name(err));
//   }
// }

// /**
//  * シリアル通信の動作確認用スケッチ
//  */
// void setup() {
//   // シリアル通信を開始します。ボーレートは115200bpsに設定。
//   // シリアルモニタ側も同じ速度に設定してください。
//   Serial.begin(115200);

//   // 起動時に一度だけメッセージを送信
//   Serial.println("--- シリアル通信テスト開始 ---");
//   Serial.println("このメッセージが見えれば、セットアップは正常です。");
// }

// void loop() {
//   // 1秒（1000ミリ秒）ごとにカウンターの数字を送信し続ける
//   Serial.print("カウンター: ");
//   Serial.println(millis() / 1000); // 起動してからの秒数を表示

//   // 1秒待機
//   delay(1000);
// }



