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
  Serial.begin(9600);

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
    // Serial.write((uint8_t*)i2s_read_buff, bytes_read);
    Serial.println(bytes_read);
  }
  

}

