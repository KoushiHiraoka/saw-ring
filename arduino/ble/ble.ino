#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <BLE2902.h>
#include "driver/i2s_pdm.h"

// I2Sピンの設定 (変更なし)
#define I2S_PDM_CLK_IO      (GPIO_NUM_3)  // CLK
#define I2S_PDM_DIN_IO      (GPIO_NUM_1)  // DATA

// I2S設定 (変更なし)
#define I2S_PORT            (I2S_NUM_0)
constexpr int SAMPLE_RATE = 24000;
constexpr int BITS_PER_SAMPLE = 16;
constexpr size_t BUFFER_SIZE = 1024;

// BLE設定
#define SERVICE_UUID        "65f27680-ab0b-4ede-b02e-5fab0fd4380a"
#define CHARACTERISTIC_UUID "13b73498-101b-4f22-aa2b-a72c6710e54f"

// グローバル変数
BLECharacteristic *pCharacteristic;
bool deviceConnected = false;
int16_t i2s_read_buff[BUFFER_SIZE / sizeof(int16_t)];
i2s_chan_handle_t rx_handle;

// BLEサーバーの接続/切断イベントを処理するコールバッククラス
class MyServerCallbacks: public BLEServerCallbacks {
    void onConnect(BLEServer* pServer) {
      deviceConnected = true;
      Serial.println("Client Connected.");
    }

    void onDisconnect(BLEServer* pServer) {
      deviceConnected = false;
      Serial.println("Client Disconnected.");
      // 次の接続に備えて、再度アドバタイジングを開始
      pServer->getAdvertising()->start();
      Serial.println("Start advertising...");
    }
};

// I2Sのセットアップ関数
void setup_i2s() {
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

  Serial.println("I2S PDM RX enabled.");
}

void setup() {
  // デバッグ用のシリアル通信を開始 (高速なデータ通信のためボーレートを上げることを推奨)
  Serial.begin(115200);
  Serial.println("Start SAW-Ring");

  // BLEデバイスの初期化
  BLEDevice::init("SAW-Ring"); // BLEデバイス名を設定

  // BLEサーバーの作成
  BLEServer *pServer = BLEDevice::createServer();
  pServer->setCallbacks(new MyServerCallbacks()); // 接続・切断のコールバックを設定

  // サービスの作成
  BLEService *pService = pServer->createService(SERVICE_UUID);

  // キャラクタリスティックの作成
  pCharacteristic = pService->createCharacteristic(
                      CHARACTERISTIC_UUID,
                      BLECharacteristic::PROPERTY_NOTIFY // Notifyプロパティを設定
                    );
  
  // Notifyを有効にするためにディスクリプタ(BLE2902)を追加
  pCharacteristic->addDescriptor(new BLE2902());

  // サービスの開始
  pService->start();

  // アドバタイジングの開始 (PCなどがこのデバイスを見つけられるようにする)
  BLEAdvertising *pAdvertising = pServer->getAdvertising();
  pAdvertising->addServiceUUID(SERVICE_UUID);
  pAdvertising->setScanResponse(true);
  pAdvertising->start();
  Serial.println("Waiting for a client connection...");

  // I2Sのセットアップ
  setup_i2s();
}

void loop() {
  // クライアントが接続されている場合のみデータを送信
  if (deviceConnected) {
    size_t bytes_read = 0;
    // I2SからPCMデータを読み込む (データが来るまで待機)
    esp_err_t ret = i2s_channel_read(rx_handle, i2s_read_buff, BUFFER_SIZE, &bytes_read, portMAX_DELAY);
    
    if (ret == ESP_OK && bytes_read > 0) {
      // BLEで一度に送信できるデータサイズ(MTU)には限りがあるため、データを分割して送信
      const int mtu = BLEDevice::getMTU();
      // ヘッダ(3バイト)を除いたペイロードサイズをチャンクサイズとする
      const size_t chunkSize = mtu > 23 ? mtu - 3 : 20;

      for (size_t i = 0; i < bytes_read; i += chunkSize) {
        size_t len = (bytes_read - i < chunkSize) ? (bytes_read - i) : chunkSize;
        
        // 分割したデータをセットしてクライアントに通知(Notify)
        pCharacteristic->setValue((uint8_t*)i2s_read_buff + i, len);
        pCharacteristic->notify();
      }
    } else if (ret != ESP_OK) {
      Serial.printf("I2S Read Error: %d\n", ret);
    }
  }
}