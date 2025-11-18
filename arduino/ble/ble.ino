#include <NimBLEDevice.h>
#include "driver/i2s_pdm.h"

// I2Sピンの設定
#define I2S_PDM_CLK_IO      (GPIO_NUM_3)
#define I2S_PDM_DIN_IO      (GPIO_NUM_1)
#define I2S_PORT            (I2S_NUM_0)

constexpr int SAMPLE_RATE = 24000;
constexpr int BITS_PER_SAMPLE = 16;
constexpr size_t BUFFER_SIZE = 4096; 

#define SERVICE_UUID        "65f27680-ab0b-4ede-b02e-5fab0fd4380a"
#define CHARACTERISTIC_UUID "13b73498-101b-4f22-aa2b-a72c6710e54f"

NimBLECharacteristic *pCharacteristic;
bool deviceConnected = false;
int16_t i2s_read_buff[BUFFER_SIZE / sizeof(int16_t)];
i2s_chan_handle_t rx_handle;
TaskHandle_t I2S_TaskHandle;

// 接続コールバック (NimBLE 2.x 仕様)
class MyServerCallbacks: public NimBLEServerCallbacks {
    
    // ★修正1: 引数が NimBLEConnInfo& に変わりました
    void onConnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo) {
      deviceConnected = true;
      Serial.println("Client Connected.");
      
      // ★修正2: connInfo からハンドルを取得して高速化要求
      pServer->updateConnParams(connInfo.getConnHandle(), 6, 12, 0, 100);
    }

    void onDisconnect(NimBLEServer* pServer, NimBLEConnInfo& connInfo, int reason) {
      deviceConnected = false;
      Serial.println("Client Disconnected.");
      delay(500);
      NimBLEDevice::startAdvertising();
      Serial.println("Start advertising...");
    }
};

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
  Serial.println("I2S PDM RX enabled.");
}

void i2s_ble_task(void *pvParameters) {
  Serial.print("I2S BLE Task started on Core: ");
  Serial.println(xPortGetCoreID());
  
  for(;;) {
    if (deviceConnected) {
      size_t bytes_read = 0;
      esp_err_t ret = i2s_channel_read(rx_handle, i2s_read_buff, BUFFER_SIZE, &bytes_read, pdMS_TO_TICKS(50));
      
      if (ret == ESP_OK && bytes_read > 0) {
        size_t mtu = NimBLEDevice::getMTU();
        size_t chunkSize = (mtu > 5) ? mtu - 5 : 20;

        for (size_t i = 0; i < bytes_read; i += chunkSize) {
          size_t len = (bytes_read - i < chunkSize) ? (bytes_read - i) : chunkSize;
          
          pCharacteristic->setValue((uint8_t*)i2s_read_buff + i, len);
          pCharacteristic->notify(); 
        }
      } else if (ret != ESP_OK && ret != ESP_ERR_TIMEOUT) {
        Serial.printf("I2S Read Error: %d\n", ret);
      }
    } else {
      vTaskDelay(pdMS_TO_TICKS(50));
    }
  }
}

void setup() {
  delay(2000); 
  Serial.begin(115200);
  Serial.println("Start SAW-Ring (NimBLE 2.x)");

  NimBLEDevice::init("SAW-Ring");
  NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  NimBLEDevice::setMTU(517);

  NimBLEServer *pServer = NimBLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks());

  NimBLEService *pService = pServer->createService(SERVICE_UUID);

  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      NIMBLE_PROPERTY::NOTIFY 
                    );

  pService->start();

  NimBLEAdvertising *pAdvertising = NimBLEDevice::getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  
  // ★修正3: エラーが出ていた行を削除 (v2.xでは不要/非推奨)
  // pAdvertising->setScanResponse(true); 

  pAdvertising->start();
  Serial.println("Waiting for a client connection...");

  setup_i2s();
  
  xTaskCreatePinnedToCore(
    i2s_ble_task,
    "I2S BLE Task",
    8192,
    NULL,
    1,
    &I2S_TaskHandle,
    1 
  );
}

void loop() {
  vTaskDelay(1000);
}