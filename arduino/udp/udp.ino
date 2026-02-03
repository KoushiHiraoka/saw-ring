#include <WiFi.h>
#include <WiFiUdp.h>
#include "driver/i2s_pdm.h"

// I2Sピンの設定
#define I2S_PDM_CLK_IO      (GPIO_NUM_3)  // CLK
// ver.1
// #define I2S_PDM_DIN_IO      (GPIO_NUM_1)  // DATA
// ver.2
#define I2S_PDM_DIN_IO      (GPIO_NUM_2)  // DATA

// I2S設定
#define I2S_PORT            (I2S_NUM_0)   
constexpr int SAMPLE_RATE = 24000;       
constexpr int BITS_PER_SAMPLE = 16;         
constexpr size_t BUFFER_SIZE = 1024;

// WiFi設定
// saw-ring 1
// const char* ssid = "saw-ring";
// constexpr int udpPort = 8000; 
const char* ssid = "saw-ring-2";
constexpr int udpPort = 8800; 
WiFiUDP udp;

// 受信チャンネル
int16_t i2s_read_buff[BUFFER_SIZE / sizeof(int16_t)];
i2s_chan_handle_t rx_handle;



void setup_wifi() {
  // ESP32をアクセスポイントとして設定
  WiFi.disconnect(true);
  WiFi.mode(WIFI_AP);
  bool result = WiFi.softAP(ssid, nullptr);
  // if (result) {
  //     Serial.println("WiFi Access Point started successfully.");
  // } else {
  //     Serial.println("Failed to start WiFi Access Point.");
  // }
  IPAddress IP = WiFi.softAPIP();
  WiFi.setSleep(false);
  
  // Serial.print("AP IP address: ");
  // Serial.println(IP);

  udp.begin(udpPort);
}

void setup_i2s(){
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

  // Serial.println("I2S PDM RX 有効化");

}

void setup() {
  // デバッグ用
  // Serial.begin(9600);
  // Serial.println("Start SAW-Ring");

  setup_wifi();
  setup_i2s();
}

void loop() {
  size_t bytes_read = 0;

  // PCM from I2S
  esp_err_t ret = i2s_channel_read(rx_handle, i2s_read_buff, BUFFER_SIZE, &bytes_read, (250)); // タイムアウトを250msに設定
  if (ret == ESP_OK && bytes_read > 0) {
    // UDPでPCMデータを送信
    // IPAddress broadcastAddress = WiFi.softAPIP();
    // broadcastAddress[3] = 255;
    IPAddress pcIP(192, 168, 4, 2);

    if (udp.beginPacket(pcIP, udpPort)) {
      udp.write((uint8_t*)i2s_read_buff, bytes_read);
      udp.endPacket();
    } else {
      // Serial.println("Failed to start UDP");
    }
  } else {
    // Serial.printf("I2S Error Code: %d\n", ret);
  }
}