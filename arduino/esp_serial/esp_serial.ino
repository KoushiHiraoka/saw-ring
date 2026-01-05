#include "driver/i2s_pdm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

// --- シリアル通信設定 ---
// PC側の受信スクリプトもこのボーレートに合わせてください
#define SERIAL_BAUD_RATE    2000000 

// --- I2Sピン設定 (TCP.ino準拠) ---
#define I2S_PDM_CLK_IO      (GPIO_NUM_3)
#define I2S_PDM_DIN_IO      (GPIO_NUM_1) 

// --- I2S設定 ---
#define I2S_PORT            (I2S_NUM_0)   
#define SAMPLE_RATE         (24000)       
#define BITS_PER_SAMPLE     (I2S_DATA_BIT_WIDTH_16BIT)

// バッファサイズ (バイト数)
// I2Sから一度に読み取るサイズ。大きすぎると遅延、小さすぎるとオーバーヘッド増。
constexpr size_t BUFFER_SIZE = 1024; 

// --- マルチタスク用設定 ---
QueueHandle_t dataQueue; 
#define QUEUE_LENGTH 16  // バッファのストック数 (送信が詰まった時の保険)
#define QUEUE_ITEM_SIZE BUFFER_SIZE

// タスクハンドル
TaskHandle_t I2S_TaskHandle;
TaskHandle_t Serial_TaskHandle;
i2s_chan_handle_t rx_handle;

// --- I2S初期化 (TCP.inoと同じ) ---
void setup_i2s() {
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_PORT, I2S_ROLE_MASTER);
  ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));  

  i2s_pdm_rx_config_t pdm_rx_cfg = {
      .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
      .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(BITS_PER_SAMPLE, I2S_SLOT_MODE_MONO),
      .gpio_cfg = {
          .clk = I2S_PDM_CLK_IO,
          .din = I2S_PDM_DIN_IO,
          .invert_flags = { .clk_inv = false },
      },
  };
  
  ESP_ERROR_CHECK(i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_rx_cfg));
  ESP_ERROR_CHECK(i2s_channel_enable(rx_handle));
}

// --- I2S読み取りタスク (Core 1) ---
// マイクからデータを吸い出し、キューに入れることだけに集中する
void i2s_read_task(void *pvParameters) {
  uint8_t i2s_read_buff[BUFFER_SIZE];
  size_t bytes_read = 0;

  while (true) {
    // I2Sからデータ取得
    esp_err_t ret = i2s_channel_read(rx_handle, i2s_read_buff, BUFFER_SIZE, &bytes_read, portMAX_DELAY);
    
    if (ret == ESP_OK && bytes_read > 0) {
      // 取得したデータをキューへ送信
      // キューがいっぱいの場合は、空くまで待機 (portMAX_DELAY)
      xQueueSend(dataQueue, i2s_read_buff, portMAX_DELAY);
    } else {
      // エラー時は短いウェイトを入れてCPU暴走を防ぐ
      vTaskDelay(1);
    }
  }
}

// --- シリアル送信タスク (Core 0) ---
// キューからデータを取り出し、PCへ送信する
void serial_send_task(void *pvParameters) {
  uint8_t serial_send_buff[BUFFER_SIZE];
  
  while (true) {
    // キューからデータが来るのを待つ
    if (xQueueReceive(dataQueue, serial_send_buff, portMAX_DELAY) == pdPASS) {
      // バイナリデータとしてシリアル書き込み
      // Serial.writeはバッファが埋まるとブロックする可能性があるため、Core 0で実行するのが安全
      Serial.write(serial_send_buff, BUFFER_SIZE);
    }
  }
}

void setup() {
  // 高速シリアル通信を開始
  Serial.begin(SERIAL_BAUD_RATE);
  
  // キュー作成
  dataQueue = xQueueCreate(QUEUE_LENGTH, QUEUE_ITEM_SIZE);
  if (dataQueue == NULL) {
    while(1); // キュー生成失敗時は停止
  }

  // I2Sセットアップ
  setup_i2s();

  // I2S読み取りタスク (Core 1: アプリケーションコア)
  // 優先度高め(10)にして、サンプリング漏れを防ぐ
  xTaskCreatePinnedToCore(
    i2s_read_task,
    "I2S Read",
    4096,
    NULL,
    10, 
    &I2S_TaskHandle,
    1 
  );
  
  // シリアル送信タスク (Core 0: プロトコルコア)
  // 送信処理を担当。優先度はI2Sより少し下げる
  xTaskCreatePinnedToCore(
    serial_send_task,
    "Serial Send",
    4096,
    NULL,
    5, 
    &Serial_TaskHandle,
    0 
  );
}

void loop() {
  // メインループは何もしない（タスクに任せる）
  vTaskDelete(NULL);
}