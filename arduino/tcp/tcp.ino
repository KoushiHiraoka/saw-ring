#include <WiFi.h>
#include <WiFiManager.h>
#include <ESPmDNS.h>
#include "driver/i2s_pdm.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"

// --- I2Sピン設定 ---
#define I2S_PDM_CLK_IO      (GPIO_NUM_3)
#define I2S_PDM_DIN_IO      (GPIO_NUM_1) 

// --- I2S設定 ---
#define I2S_PORT            (I2S_NUM_0)   

constexpr int SAMPLE_RATE = 24000;   
constexpr size_t BUFFER_SIZE = 1024; // I2S読み取りバッファ

// --- TCPサーバー設定 ---
constexpr int tcpPort = 8000; 
WiFiServer server(tcpPort);
WiFiClient client;

// --- マルチタスク用設定 ---
QueueHandle_t dataQueue; 
#define QUEUE_LENGTH 8
#define QUEUE_ITEM_SIZE BUFFER_SIZE

// I2S読み取りタスクのハンドル
TaskHandle_t I2S_TaskHandle;
TaskHandle_t TCP_TaskHandle;
i2s_chan_handle_t rx_handle;

// I2Sセットアップ
void setup_i2s() {
  i2s_chan_config_t chan_cfg = I2S_CHANNEL_DEFAULT_CONFIG(I2S_PORT, I2S_ROLE_MASTER);
  ESP_ERROR_CHECK(i2s_new_channel(&chan_cfg, NULL, &rx_handle));  

  i2s_pdm_rx_config_t pdm_rx_cfg = {
      .clk_cfg = I2S_PDM_RX_CLK_DEFAULT_CONFIG(SAMPLE_RATE),
      .slot_cfg = I2S_PDM_RX_SLOT_DEFAULT_CONFIG(I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO),
      .gpio_cfg = {
          .clk = I2S_PDM_CLK_IO,
          .din = I2S_PDM_DIN_IO,
          .invert_flags = { .clk_inv = false },
      },
  };
  
  ESP_ERROR_CHECK(i2s_channel_init_pdm_rx_mode(rx_handle, &pdm_rx_cfg));
  ESP_ERROR_CHECK(i2s_channel_enable(rx_handle));
  Serial.println("I2S PDM RX Enabled");
}

// I2S読み取り専用タスク (Core 1で実行)
void i2s_read_task(void *pvParameters) {
  uint8_t i2s_read_buff[BUFFER_SIZE];
  size_t bytes_read = 0;

  while (true) {
    // I2Sからデータを読み込む (データが来るまでここで待機)
    esp_err_t ret = i2s_channel_read(rx_handle, i2s_read_buff, BUFFER_SIZE, &bytes_read, portMAX_DELAY);
    
    if (ret == ESP_OK && bytes_read > 0) {
      // 読み取ったデータをキューに送信 (Core 0のタスクが受け取るまで待機)
      xQueueSend(dataQueue, &i2s_read_buff, portMAX_DELAY);
    } else {
      Serial.printf("I2S Read Error: %d\n", ret);
    }
  }
}

void tcp_send_task(void *pvParameters) {
  Serial.println("TCP/IP task running on Core 0");
  
  while (true) {
    if (!client || !client.connected()) {
      client = server.available(); // 新しいクライアントを探す
      if (client) {
        Serial.println("New client connected.");
        client.setNoDelay(true); // 高速化
      }
    }

    if (client && client.connected()) {
      uint8_t tcp_send_buff[BUFFER_SIZE];
      
      // Core 1 (I2Sタスク) からデータが来るまで待機
      if (xQueueReceive(dataQueue, &tcp_send_buff, portMAX_DELAY) == pdPASS) {
        // データをTCPクライアントに送信
        client.write((const uint8_t*)tcp_send_buff, BUFFER_SIZE);
      }
    } else {
      // クライアント未接続時
      xQueueReset(dataQueue); // キューを空にする
      vTaskDelay(pdMS_TO_TICKS(10)); // CPUを休ませる
    }
  }
}

void setup() {
  Serial.begin(115200);
  Serial.println("Start SAW-Ring (Multi-Core TCP)");

  WiFiManager wm;

  wm.resetSettings(); 

  bool res = wm.autoConnect("SAW-Ring-Setup");
  if(!res) {
    Serial.println("Failed to connect");
    ESP.restart();
  } 
  
  Serial.println("WiFi Connected!");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());

  if (MDNS.begin("saw-ring")) {
    Serial.println("MDNS responder started. Connect to: saw-ring.local");
  }

  server.begin();
  Serial.println("TCP server started.");

  // データキューを作成
  dataQueue = xQueueCreate(QUEUE_LENGTH, QUEUE_ITEM_SIZE);

  setup_i2s();
  
  // I2S読み取りタスクを Core 1 で起動
  xTaskCreatePinnedToCore(
    i2s_read_task,    // タスク関数
    "I2S Read Task",  // 名前
    4096,             // スタックサイズ
    NULL,             // 引数
    10,               // 優先度 (高くする)
    &I2S_TaskHandle,  // タスクハンドル
    1                 // Core 1
  );
  
  xTaskCreatePinnedToCore(
    tcp_send_task,
    "TCP Send Task",
    4096,
    NULL,
    5, // I2Sより優先度を下げる
    &TCP_TaskHandle,
    0  // Core 0 (Wi-Fiスタックと同じコア)
  );

  Serial.println("TCP/IP task running on Core 0");
}

void loop() {

}