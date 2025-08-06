import socket
import struct
import numpy as np
import sys
import signal
import queue
import threading
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

# UDP設定
ESP_IP = "0.0.0.0"
PORT = 8000
BUFFER_SIZE = 1024
SAMPLE_RATE = 44100
num_samples = BUFFER_SIZE // 2
unpack_format = f'<{num_samples}h'

# ソケット初期化
client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 受信設定
client.bind((ESP_IP, PORT))
print(f"Connected to {ESP_IP}:{PORT}")

data_queue = queue.Queue()
# スレッド停止用イベント
stop_event = threading.Event()
def analyze_signal(client, unpack_format, num_samples, SAMPLE_RATE, stop_event):
    buffer = b''  # データを蓄積するバッファ

    while not stop_event.is_set():  # stop_eventがセットされるまでループ
        try:
            # UDPデータを受信
            raw_data, addr = client.recvfrom(BUFFER_SIZE)
            buffer += raw_data  # バッファにデータを追加
            print(f"Received {len(raw_data)} bytes")

            # バッファがBUFFER_SIZEに達したら処理を行う
            while len(buffer) >= BUFFER_SIZE:
                # 必要なサイズだけ切り出して処理
                data_to_process = buffer[:BUFFER_SIZE]
                buffer = buffer[BUFFER_SIZE:]  

                # データをデコードしてFFT解析
                pdm_samples_tuple = struct.unpack(unpack_format, data_to_process)
                pdm_samples_np = np.array(pdm_samples_tuple, dtype=np.float32)
                fft_result = np.fft.fft(pdm_samples_np)
                amplitude = np.abs(fft_result) / num_samples
                freq = np.fft.fftfreq(num_samples, d=1/SAMPLE_RATE)

                positive_freq_indices = np.where(freq >= 0)
                amplitude_pos = amplitude[positive_freq_indices]
                freq_pos = freq[positive_freq_indices]

                # グラフを更新
                data_queue.put((freq_pos, amplitude_pos))
        except Exception as e:
            if not stop_event.is_set():
                print(f"エラーが発生しました: {e}")

def signal_handler(sig, frame):
    print("\nExiting program...")
    stop_event.set()
    client.close()
    sys.exit(0)

def update_plot():
    if not data_queue.empty():
        # キューからデータを取得
        freq_pos, amplitude_pos = data_queue.get()
        curve.setData(freq_pos, amplitude_pos)

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal_handler)

    # PyQtGraphのセットアップ
    app = pg.mkQApp("リアルタイムFFT")
    win = pg.GraphicsLayoutWidget(show=True, title="FFT Plot")
    win.resize(800, 400)
    win.setWindowTitle('リアルタイムFFT')
    pg.setConfigOptions(antialias=True)

    plot = win.addPlot(title="周波数スペクトル")
    plot.setLabel('bottom', '周波数 (Hz)')
    plot.setLabel('left', '振幅')
    plot.setLogMode(x=False, y=True)
    plot.setYRange(0, 10)
    curve = plot.plot(pen='y')
    print("Plot initialized. Waiting for data...")

    # データ処理スレッドを開始
    processing_thread = threading.Thread(target=analyze_signal, args=(client, unpack_format, num_samples, SAMPLE_RATE, stop_event))
    processing_thread.daemon = True
    processing_thread.start()

    # QTimerを使用してグラフを定期的に更新
    t = 0
    timer = QtCore.QTimer()
    timer.timeout.connect(update_plot)
    timer.start(1)  # 50msごとに更新
    t += 1

    QtWidgets.QApplication.instance().exec()

    # スレッドの終了を待機
    stop_event.set()
    processing_thread.join()