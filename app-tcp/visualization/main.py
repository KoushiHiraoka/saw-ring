import sys
import socket
import numpy as np
from scipy import fft
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject
import pyqtgraph as pg
import time

from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer
import pyqtgraph as pg
from collections import deque

# --- 基本設定 ---
ESP_IP = "192.168.4.1"
PORT = 8000
BUFFER_SIZE = 1024 * 2 # FFTの分解能を上げるため、バッファを少し増やす
SAMPLE_RATE = 24000
DTYPE = np.int16
# バッファサイズからサンプル数を計算
NUM_SAMPLES = BUFFER_SIZE // np.dtype(DTYPE).itemsize

# --- データ受信を専門に行うWorkerクラス ---
class DataWorker(QObject):
    data_ready = pyqtSignal(np.ndarray)
    connection_failed = pyqtSignal(str)
    connection_lost = pyqtSignal(str)
    connection_success = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.client = None
        self._is_running = True

    def run(self):
        """TCP接続とデータ受信ループ"""
        buffer = b''
        try:
            self.client = socket.create_connection((ESP_IP, PORT), timeout=5)
            self.connection_success.emit()
        except Exception as e:
            self.connection_failed.emit(f"接続失敗: {e}")
            return

        while self._is_running:
            try:
                raw_data = self.client.recv(BUFFER_SIZE)
                if not raw_data:
                    self.connection_lost.emit("接続が相手方から切断されました。")
                    break
                
                buffer += raw_data
                
                # 厳密にBUFFER_SIZEごとに処理
                while len(buffer) >= BUFFER_SIZE:
                    loop_start = time.perf_counter()

                    data_to_process = buffer[:BUFFER_SIZE]
                    buffer = buffer[BUFFER_SIZE:]
                    
                    pcm_data = np.frombuffer(data_to_process, dtype=DTYPE)
                    if pcm_data.size > 0:
                        normalized_data = pcm_data / 32768.0
                        self.data_ready.emit(normalized_data)
                    
                    loop_end = time.perf_counter()
                    elapsed = loop_end - loop_start
                    print(f"データ受信速度: {elapsed*1000:.3f} ms")

            except socket.timeout:
                continue # タイムアウトは許容
            except Exception as e:
                self.connection_lost.emit(f"受信エラー: {e}")
                break
        
        if self.client:
            self.client.close()
        print("データ受信スレッドを終了しました。")

    def stop(self):
        self._is_running = False

# --- メインウィンドウクラス ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("リアルタイム波形・周波数解析")
        self.setGeometry(100, 100, 1000, 600)

        # 表示モードの状態を管理 ('waveform' or 'fft')
        self.display_mode = 'waveform'
        
        self._setup_ui()
        self._init_plots() # プロットの初期化を分離

        self.worker = None
        self.thread = None

        # dequeは高速に要素を追加・削除できるリストのようなもの
        self.data_buffer = deque()

        # 描画更新用のタイマー
        self.plot_timer = QTimer(self)
        self.plot_timer.setInterval(16) # 約30fps (1000ms / 30)
        self.plot_timer.timeout.connect(self.triggered_update_plot)

    def _setup_ui(self):
        """UIウィジェットの作成とレイアウト設定"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # プロットウィジェット
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        main_layout.addWidget(self.plot_widget, stretch=1)

        # 操作パネル
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 5, 0, 0)
        
        self.start_button = QPushButton("📈 接続開始")
        self.stop_button = QPushButton("⏹️ 切断")
        self.toggle_button = QPushButton("📊 周波数解析へ (FFT)")
        self.stop_button.setEnabled(False)
        self.toggle_button.setEnabled(False)
        
        self.status_label = QLabel("状態: 待機中")
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.toggle_button)
        control_layout.addStretch()
        control_layout.addWidget(self.status_label)
        
        main_layout.addWidget(control_panel)

        self.start_button.clicked.connect(self.start_plotting)
        self.stop_button.clicked.connect(self.stop_plotting)
        self.toggle_button.clicked.connect(self.toggle_display_mode)

    def _init_plots(self):
        """波形とFFTのプロットアイテムを初期化"""
        # 波形プロット用データ
        self.plot_data_size = NUM_SAMPLES * 10
        self.y_data = np.zeros(self.plot_data_size)
        self.waveform_pen = pg.mkPen(color=(0, 120, 215), width=8)
        self.waveform_plot_item = self.plot_widget.plot(self.y_data, pen=self.waveform_pen, name="Waveform")

        # FFTプロット用データ
        # rfftを使うので、データ点数は N/2 + 1
        self.fft_freqs = fft.rfftfreq(NUM_SAMPLES, 1 / SAMPLE_RATE)
        self.fft_power = np.zeros(len(self.fft_freqs))
        self.fft_pen = pg.mkPen(color=(215, 60, 0), width=2)
        self.fft_plot_item = self.plot_widget.plot(self.fft_freqs, self.fft_power, pen=self.fft_pen, name="FFT")
        
        # 最初はFFTプロットを非表示にする
        self.fft_plot_item.hide()
        # 初期表示を波形モードに設定
        self._setup_waveform_view()

    def toggle_display_mode(self):
        """表示モードを切り替える"""
        if self.display_mode == 'waveform':
            self.display_mode = 'fft'
            self.toggle_button.setText("📉 波形表示へ")
            self._setup_fft_view()
        else:
            self.display_mode = 'waveform'
            self.toggle_button.setText("📊 周波数解析へ (FFT)")
            self._setup_waveform_view()

    def _setup_waveform_view(self):
        """波形表示モードの見た目を設定"""
        self.plot_widget.setTitle("リアルタイム波形")
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time (Samples)')
        self.plot_widget.setYRange(-1.1, 1.1)
        self.plot_widget.setXRange(0, self.plot_data_size)
        self.plot_widget.setLogMode(x=False, y=False)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        self.waveform_plot_item.show()
        self.fft_plot_item.hide()

    def _setup_fft_view(self):
        """FFT表示モードの見た目を設定"""
        self.plot_widget.setTitle("リアルタイム周波数解析 (FFT)")
        self.plot_widget.setLabel('left', 'Power (Magnitude)')
        self.plot_widget.setLabel('bottom', 'Frequency (Hz)')
        # X軸はナイキスト周波数まで
        self.plot_widget.setXRange(0, SAMPLE_RATE / 2)
        # Y軸の範囲はデータの様子を見て調整
        self.plot_widget.setYRange(0, 30) 
        self.plot_widget.setLogMode(x=False, y=False) # 必要に応じて y=True にすると見やすい
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        self.waveform_plot_item.hide()
        self.fft_plot_item.show()

    def start_plotting(self):
        """描画・通信開始処理"""
        if self.thread is not None and self.thread.isRunning():
            return
        
        self.thread = QThread()
        self.worker = DataWorker()
        self.worker.moveToThread(self.thread)

        # self.worker.data_ready.connect(self.update_plot)
        self.worker.data_ready.connect(self.queue_data)
        self.worker.connection_success.connect(self._on_connection_success)
        self.worker.connection_failed.connect(self._on_connection_failed)
        self.worker.connection_lost.connect(self._on_connection_lost)
        
        self.thread.started.connect(self.worker.run)
        self.thread.start()
        self.plot_timer.start()
        
        self.start_button.setEnabled(False)
        self.status_label.setText("状態: <font color='orange'><b>接続中...</b></font>")

    def stop_plotting(self):
        self.plot_timer.stop()
        """描画・通信停止処理"""
        if self.worker:
            self.worker.stop()
        if self.thread:
            self.thread.quit()
            self.thread.wait()

        self.thread = None
        self.worker = None

        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.toggle_button.setEnabled(False)
        self.status_label.setText("状態: <font color='red'><b>切断</b></font>")

    def queue_data(self, new_data):
        self.data_buffer.append(new_data)

    def update_plot(self, new_data):
        """Workerからデータを受け取り、現在のモードに応じてプロットを更新"""
        update_start = time.perf_counter()

        if self.display_mode == 'waveform':
            self.y_data = np.roll(self.y_data, -NUM_SAMPLES)
            self.y_data[-NUM_SAMPLES:] = new_data # 未処理のデータをまず連結CD
            display_data = self.y_data

            # 処理後のデータをプロットにセットする
            self.waveform_plot_item.setData(display_data)
            update_end = time.perf_counter()
            elapsed_update = update_end - update_start
            
            print(f"描画更新時間: {elapsed_update*1000:.2f} ms")

        else:
            # FFTを計算して更新
            processed_data = new_data - np.mean(new_data)
            # ハニング窓を適用してスペクトル漏れを軽減
            window = np.hanning(len(processed_data))
            fft_result = fft.rfft(processed_data * window)
            # パワースペクトル（振幅）を計算
            self.fft_power = np.abs(fft_result)
            self.fft_plot_item.setData(self.fft_freqs, self.fft_power)

    def triggered_update_plot(self):
        """
        ★ QTimerによって呼び出され、バッファのデータをまとめて描画する
        """

        update_start = time.perf_counter()

        if not self.data_buffer:
            return # バッファにデータがなければ何もしない

        # バッファに溜まっているデータを全て取り出す
        # 今回は最新のデータ1つだけで更新するシンプルな例
        # 連続性を重視する場合は、溜まったデータを全て処理するループをここに書く
        data_to_plot = self.data_buffer.popleft()
        # バッファを空にする場合は self.data_buffer.clear() でも良い

        if self.display_mode == 'waveform':
            self.y_data[:-NUM_SAMPLES] = self.y_data[NUM_SAMPLES:]
            self.y_data[-NUM_SAMPLES:] = data_to_plot
            self.waveform_plot_item.setData(self.y_data)
            update_endd = time.perf_counter()
            elapsed_update = update_endd - update_start

            print(f"描画更新時間: {elapsed_update*1000:.3f} ms")
        else:
            processed_data = data_to_plot - np.mean(data_to_plot)
            window = np.hanning(len(processed_data))
            fft_result = fft.rfft(processed_data * window)
            self.fft_power = np.abs(fft_result)
            self.fft_plot_item.setData(self.fft_freqs, self.fft_power)
    
        # while self.data_buffer:
        #     new_data = self.data_buffer.popleft()

        #     # 波形表示用のデータ配列(self.y_data)を更新
        #     if self.display_mode == 'waveform':
        #         self.y_data[:-NUM_SAMPLES] = self.y_data[NUM_SAMPLES:]
        #         self.y_data[-NUM_SAMPLES:] = new_data
            
        #     # FFT表示用のデータも更新しておく（表示されていなくても計算だけする）
        #     # こうすることで、モード切替時に最新のFFTが表示される
        #     else:
        #         # この部分は、実際にFFT表示モードの時だけ計算する方がより効率的
        #         # しかし、計算負荷は低いのでこのままでも問題ないことが多い
        #         processed_data = new_data - np.mean(new_data)
        #         window = np.hanning(len(processed_data))
        #         fft_result = fft.rfft(processed_data * window)
        #         self.fft_power = np.abs(fft_result)

        # # --- 描画処理はループの外で、最後に一回だけ！ ---
        # if self.display_mode == 'waveform':
        #     self.waveform_plot_item.setData(self.y_data)
        # else:
        #     self.fft_plot_item.setData(self.fft_freqs, self.fft_power)
    
    # --- 接続状態に関するスロット ---
    def _on_connection_success(self):
        self.stop_button.setEnabled(True)
        self.toggle_button.setEnabled(True)
        self.status_label.setText("状態: <font color='green'><b>接続成功</b></font>")
        
    def _on_connection_failed(self, message):
        self.status_label.setText(f"状態: <font color='red'><b>{message}</b></font>")
        self.start_button.setEnabled(True)

    def _on_connection_lost(self, message):
        self.status_label.setText(f"状態: <font color='red'><b>{message}</b></font>")
        self.stop_plotting()

    def closeEvent(self, event):
        """ウィンドウが閉じられたときの処理"""
        self.stop_plotting()
        event.accept()

# --- アプリケーションの実行 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())