# SAW-Ring

VPU (Voice Pick Up) センサを搭載したリング型デバイスからSAW（Surface Acoustic Wave）データをリアルタイム受信し、信号可視化・表面認識推論を行うシステムです。

## 機能

- **リアルタイム可視化**: 波形・周波数スペクトル・メルスペクトログラムをGUIで表示
- **表面認識**: ResNet18 モデルによる触れている素材のリアルタイム推論
- **データ収集**: ラベル付き音響データを WAV ファイルとして保存するGUIアプリ

## 必要環境

- Python 3.11 以上 3.15 未満
- macOS（日本語フォント `/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc` を使用）
- SAW-Ring デバイス（UDP でデータを送信）
- Arduino IDE 2.3.6（Arduino スケッチの書き込みに使用）

## セットアップ
事前にデバイスとPort番号の対応を確認して、適宜コードを書き換えてください。

### Poetry を使う場合

```bash
poetry install
poetry shell
```

### pip を使う場合

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 使い方

### データ可視化 & 表面認識

```bash
cd src
python main.py
```

GUIが起動します。**Start** ボタンを押すと UDP 受信を開始します。

使用するデバイスに合わせて [src/config.py](src/config.py) の `UDP_PORT` を変更してください。

| 設定項目 | 値 |
| -------- | -- |
| サンプリングレート | 24,000 Hz |

### データ収集
UDP通信用のプログラムを実行

```bash
cd data_collection/src
python udp_data_collector.py
```

使用するデバイスに合わせて [data_collection/src/udp_data_collector.py](data_collection/src/udp_data_collector.py) の `PORT` を変更してください。

| 設定項目 | 値 |
| -------- | -- |
| サンプリングレート | 24,000 Hz |

#### 操作方法

1. Texture・Gesture・Person・Index を入力
2. **収集スタート** ボタンを押す
3. **Option キーを押している間**だけ録音される
4. 離すと自動で WAV ファイルが保存される

保存先: `data/experiment/<texture>/<person>/<gesture>_<index>.wav`

パケットロス率が **10%** を超えた場合は保存が中止されます。

### Arduino スケッチの書き込み

スケッチ内で、ESP32S3シリーズのI2S/PDMライブラリを利用するため、
以下より、i2s_pdm.hファイルをダウンロードして、Arduinoライブラリとして利用できるディレクトリに配置します。
https://github.com/espressif/esp-idf/blob/master/components/esp_driver_i2s/include/driver/i2s_pdm.h

Arduino IDE (2.3.6 確認済) で [arduino/udp/udp.ino](arduino/udp/udp.ino) を開き、ESP32 に書き込みます。

書き込み前に、接続先 PC の IP アドレスを確認して設定してください。
ESP32 はアクセスポイントモード (192.168.4.1) で動作するため、接続した PC には `192.168.4.2` が割り当てられます。

```cpp
// arduino/udp/udp.ino
IPAddress pcIP(192, 168, 4, 2);  // 接続先PCのIPアドレス
```

デバイスごとの設定値：

| デバイス | SSID | UDP ポート |
| -------- | ---- | ---------- |
| saw-ring-1 | `saw-ring` | 8000 |
| saw-ring-2 | `saw-ring-2` | 8800 |
| saw-ring-3 | `saw-ring-3` | 8880 |
| saw-ring-4 | `saw-ring-4` | 8888 |

## ディレクトリ構成

```text
.
├── src/                        # 実行コード
│   ├── main.py                 # エントリポイント（GUIアプリ）
│   ├── config.py               # 各種パラメータ設定
│   ├── udp.py                  # UDP 受信
│   ├── signal_process.py       # DSP処理（FFT, メルスペクトログラム）
│   └── surface_recognition/
│       ├── models.py           # ResNet18 モデル定義
│       └── inference.py        # 推論エンジン
├── data_collection/
│   └── src/
│       └── udp_data_collector.py  # データ収集GUIアプリ
├── arduino/                    # Arduino スケッチ
├── pyproject.toml              # Poetry 依存関係
└── requirements.txt            # pip 依存関係
```
