import serial
import time
import collections
import numpy as np
import threading
import queue
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- シリアルポート設定 ---
SERIAL_PORT = '/dev/tty.usbmodem21301'  # Windowsの場合 'COMx'、macOS/Linuxの場合 '/dev/ttyUSB0' や '/dev/tty.usbmodemXXXX'
BAUD_RATE = 921600

# --- ウィンドウ処理設定 (オーディオレベルデータ用) ---
WINDOW_DURATION_SEC = 1.0
STEP_SIZE_SEC = 0.1
SAMPLING_INTERVAL_MS = 100 # Arduino側で100msごとにデータを出力していると仮定

SAMPLES_IN_WINDOW = int(WINDOW_DURATION_SEC * (1000 / SAMPLING_INTERVAL_MS))
SAMPLES_IN_STEP = int(STEP_SIZE_SEC * (1000 / SAMPLING_INTERVAL_MS))

print(f"ウィンドウ内のサンプル数: {SAMPLES_IN_WINDOW}")
print(f"ステップあたりのサンプル数: {SAMPLES_IN_STEP}")

# データバッファ (リアルタイム描画と処理用の共通バッファ)
# 描画のために、より多くの履歴を保持するdequeを使用
# ここでは、直近の一定数のデータポイント（例えば5秒分）を表示する
DISPLAY_DURATION_SEC = 5.0
DISPLAY_SAMPLES = int(DISPLAY_DURATION_SEC * (1000 / SAMPLING_INTERVAL_MS))
current_audio_levels = collections.deque(maxlen=DISPLAY_SAMPLES)
timestamps_for_plot = collections.deque(maxlen=DISPLAY_SAMPLES)


# スレッド間通信用のキュー
serial_data_queue = queue.Queue()
plot_update_queue = queue.Queue() # グラフ更新のためのキュー

# --- シリアルデータ読み取りスレッド ---
def read_serial_data():
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print(f"シリアルポート {SERIAL_PORT} に接続しました。")
    except serial.SerialException as e:
        print(f"エラー: シリアルポート {SERIAL_PORT} に接続できませんでした。{e}")
        print("正しいポートが指定されているか、Arduinoが接続されているか確認してください。")
        # エラーが発生したら、シリアル読み取りスレッドを停止させるためにフラグを設定することも可能
        return

    while True:
        try:
            line = ser.readline().decode('utf-8').strip()
            if line:
                parts = line.split(',')
                if len(parts) == 2:
                    try:
                        timestamp_ms = int(parts[0])
                        audio_level = int(parts[1])
                        serial_data_queue.put((timestamp_ms, audio_level))
                    except ValueError:
                        print(f"不正なデータ形式をスキップ: {line}")
        except UnicodeDecodeError:
            print(f"UnicodeDecodeError: 不正なバイトシーケンスを受信しました。")
        except serial.SerialTimeoutException:
            pass
        except Exception as e:
            print(f"シリアル読み取り中にエラーが発生しました: {e}")
            break
    ser.close()
    print("シリアルポートの読み取りを終了しました。")

# --- データ処理関数 (オーディオレベルデータ用) ---
# この関数は、シリアルから読み取ったデータごとに呼び出されます
def process_audio_level_data(timestamp, level):
    global current_audio_levels, timestamps_for_plot

    # 描画用のバッファにデータを追加
    current_audio_levels.append(level)
    timestamps_for_plot.append(timestamp / 1000.0) # 秒単位に変換

    # グラフ更新キューに新しいデータがあることを通知
    # ここでは、単純にプロットを更新するためのトリガーとして使用
    plot_update_queue.put(True)

    # 以下は元のコードのデータ処理ロジック
    # これを別のスレッドや別のタイミングで実行することも可能です
    # （例: plot_update_queueのデータを使って処理するのではなく、serial_data_queueから直接処理）

    # リアルタイム解析用のデータバッファ（オーディオレベルデータ用）
    # 描画用のバッファとは別に、解析専用のバッファを用意する方が明確
    analysis_buffer = collections.deque(maxlen=SAMPLES_IN_WINDOW)
    
    # 処理ロジックは、必要に応じて特定のトリガー（例: 0.1秒ごと）で実行する
    # これはmain_processing_loopで制御されるべき

    # 例: 処理されたレベルをコンソールに出力
    # print(f"受信: {timestamp}ms, レベル: {level}")


# --- メイン処理ループ ---
# ここでシリアルからキューに入ったデータを取り出し、処理関数に渡す
def main_processing_loop():
    last_processed_timestamp = 0
    while True:
        try:
            timestamp, level = serial_data_queue.get(timeout=0.1) # キューからデータを取得
            process_audio_level_data(timestamp, level) # データを処理（描画用バッファに追加など）

            # ここで、解析ロジック（ウィンドウ処理、無音除去、特徴抽出）を呼び出す
            # 例えば、SAMPLING_INTERVAL_MS * SAMPLES_IN_STEP ごとに解析を実行
            # (これは、元のコードの main_processing_loop のロジック)
            # if timestamp - last_processed_timestamp >= (SAMPLING_INTERVAL_MS * SAMPLES_IN_STEP):
            #     # ここに元の process_audio_level_data の解析部分を移動
            #     # （データバッファの管理や特徴抽出ロジック）
            #     # 例: perform_feature_extraction(current_audio_levels)
            #     last_processed_timestamp = timestamp

        except queue.Empty:
            # キューが空の場合（新しいデータがない場合）
            time.sleep(0.01) # 少し待ってから再試行
        except Exception as e:
            print(f"メイン処理ループ中にエラーが発生しました: {e}")
            break

# --- リアルタイムプロット関数 ---
def animate(i, line, ax):
    # グラフ更新キューにデータがある場合のみ描画を更新
    if not plot_update_queue.empty():
        plot_update_queue.get_nowait() # キューから項目を取り出す（キューをクリアする意味合い）
        
        # dequeをリストに変換
        x_data = list(timestamps_for_plot)
        y_data = list(current_audio_levels)

        if not x_data or not y_data:
            return line, # データがない場合は更新しない

        line.set_data(x_data, y_data)
        
        # x軸の表示範囲を最新データに合わせて自動調整
        # 例: 直近のDISPLAY_DURATION_SEC秒分を表示
        ax.set_xlim(max(0, x_data[-1] - DISPLAY_DURATION_SEC), x_data[-1])
        
        # y軸はデータの最大値と最小値に合わせて自動調整
        ax.set_ylim(min(y_data) * 0.9, max(y_data) * 1.1)
        
        # グラフを再描画
        plt.draw()
        plt.pause(0.001) # 短時間ポーズして描画を更新
    
    return line,

# --- メイン実行部 ---
if __name__ == "__main__":
    # シリアル読み取りスレッドを開始
    serial_thread = threading.Thread(target=read_serial_data)
    serial_thread.daemon = True # メインスレッド終了時に一緒に終了
    serial_thread.start()

    # データ処理スレッドを開始 (メインスレッドとは別に)
    processing_thread = threading.Thread(target=main_processing_loop)
    processing_thread.daemon = True
    processing_thread.start()

    # プロットのセットアップ
    fig, ax = plt.subplots(figsize=(10, 6))
    line, = ax.plot([], [], 'b-') # 青い線でプロット
    ax.set_title('Real-time Audio Level from XIAO ESP32S3')
    ax.set_xlabel('Time (s)')
    ax.set_ylabel('Audio Level')
    ax.grid(True)

    # グラフのアニメーションを設定
    # `interval` はミリ秒単位で、アニメーションフレーム間の遅延を設定
    # データ受信速度に合わせて調整すると良いでしょう。
    # この例では、データが到着した時だけ更新するように `plot_update_queue` を使うので、intervalは短めでも良い
    ani = animation.FuncAnimation(fig, animate, fargs=(line, ax), interval=50, blit=True, cache_frame_data=False) 
    
    plt.tight_layout()
    plt.show() # グラフウィンドウを表示