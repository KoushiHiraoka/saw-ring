import sys
import socket
import numpy as np
import librosa
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer
import pyqtgraph as pg
from collections import deque
import time

# --- 基本設定 ---
# TCP接続設定
ESP_IP = "saw-ring.local" 
PORT = 8000

# 音声データ設定
BUFFER_SIZE = 1024 * 2 
SAMPLE_RATE = 24000 # WiFiだと帯域に余裕があるので24kでOK
DTYPE = np.int16
NUM_SAMPLES = BUFFER_SIZE // np.dtype(DTYPE).itemsize

# スペクトログラムの設定 (BLEコードと同じ)
N_FFT = 512
HOP_LENGTH = 128
N_MELS = 64
SPECTRO_TIME_STEPS = 100

# --- データ受信を専門に行うWorkerクラス (TCP版) ---
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
            # 接続タイムアウトを少し長めに設定
            self.client = socket.create_connection((ESP_IP, PORT), timeout=5)
            # Nagleアルゴリズムを無効化（遅延対策）
            self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.connection_success.emit()
        except Exception as e:
            self.connection_failed.emit(f"接続失敗: {e}")
            return

        while self._is_running:
            try:
                # データ受信
                raw_data = self.client.recv(BUFFER_SIZE)
                if not raw_data:
                    self.connection_lost.emit("接続が相手方から切断されました。")
                    break
                
                buffer += raw_data
                
                # BUFFER_SIZEごとに切り出して処理
                while len(buffer) >= BUFFER_SIZE:
                    data_to_process = buffer[:BUFFER_SIZE]
                    buffer = buffer[BUFFER_SIZE:]
                    
                    pcm_data = np.frombuffer(data_to_process, dtype=DTYPE)
                    
                    if pcm_data.size > 0:
                        # -1.0 ~ 1.0 に正規化
                        normalized_data = pcm_data / 32768.0
                        self.data_ready.emit(normalized_data)

            except socket.timeout:
                continue 
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
        self.setWindowTitle("Real-time Waveform and Spectrogram (TCP)")
        self.setGeometry(100, 100, 1000, 600)

        self.display_mode = 'waveform'
        
        # スペクトログラム用データバッファ初期化
        self.spectro_data = np.full((N_MELS, SPECTRO_TIME_STEPS), -80.0)

        self._setup_ui()
        self._init_plots()

        # サブウィンドウの作成
        self.spectro_window = SpectrogramWindow()
        self.spectro_window.hide()

        self.worker = None
        self.thread = None
        self.data_buffer = deque()

        # 描画更新用タイマー
        self.plot_timer = QTimer(self)
        self.plot_timer.setInterval(16)  # 約60fps
        self.plot_timer.timeout.connect(self.triggered_update_plot)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        main_layout.addWidget(self.plot_widget, stretch=1)

        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 5, 0, 0)
        
        self.start_button = QPushButton("接続開始")
        self.stop_button = QPushButton("切断")
        self.toggle_button = QPushButton("ヒートマップ")
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
        # 波形プロット用
        self.plot_data_size = NUM_SAMPLES * 10
        self.y_data = np.zeros(self.plot_data_size)
        self.waveform_pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.waveform_plot_item = self.plot_widget.plot(self.y_data, pen=self.waveform_pen)
        
        # スペクトログラム用 (ImageItem)
        self.image_item = pg.ImageItem()
        self.plot_widget.addItem(self.image_item)
        cmap = pg.colormap.get('viridis')
        self.image_item.setLookupTable(cmap.getLookupTable())
        self.image_item.setLevels([-60, 0])        
        self.image_item.setImage(self.spectro_data.T)

        self.image_item.hide()
        self._setup_waveform_view()

    def toggle_display_mode(self):
        if self.display_mode == 'waveform':
            self.display_mode = 'spectrogram'
            self.toggle_button.setText("波形表示へ")
            self._setup_spectrogram_view()
        else:
            self.display_mode = 'waveform'
            self.toggle_button.setText("ヒートマップへ")
            self._setup_waveform_view()

    def _setup_waveform_view(self):
        self.plot_widget.setTitle("リアルタイム波形")
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time (Samples)')
        self.plot_widget.setYRange(-1.1, 1.1)
        self.plot_widget.setXRange(0, self.plot_data_size)
        self.plot_widget.setLogMode(x=False, y=False)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.waveform_plot_item.show()
        self.image_item.hide()

    def _setup_spectrogram_view(self):
        self.plot_widget.setTitle("ヒートマップ")
        self.plot_widget.setLabel('left', 'Mel Bins')
        self.plot_widget.setLabel('bottom', 'Time (Frames)')
        
        self.image_item.setRect(0, 0, SPECTRO_TIME_STEPS, N_MELS)
        self.plot_widget.setXRange(0, SPECTRO_TIME_STEPS)
        self.plot_widget.setYRange(0, N_MELS)
        self.plot_widget.showGrid(x=False, y=False)

        self.waveform_plot_item.hide()
        self.image_item.show()

    def start_plotting(self):
        if self.thread and self.thread.isRunning():
            return
        
        # サブウィンドウを表示
        self.spectro_window.show()
        
        self.data_buffer.clear()
        self.thread = QThread()
        self.worker = DataWorker()
        self.worker.moveToThread(self.thread)

        self.worker.data_ready.connect(self.queue_data)
        self.worker.connection_success.connect(self._on_connection_success)
        self.worker.connection_failed.connect(self._on_connection_failed)
        self.worker.connection_lost.connect(self._on_connection_lost)
        
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

        self.plot_timer.start()
        self.start_button.setEnabled(False)
        self.status_label.setText("状態: <font color='orange'><b>接続中...</b></font>")

    def stop_plotting(self):
        self.plot_timer.stop()
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

    def triggered_update_plot(self):
        """QTimerから呼ばれる描画更新処理"""
        if not self.data_buffer:
            return

        data_to_plot = self.data_buffer.popleft()

        # サブウィンドウにもデータを送る
        if self.spectro_window:
            self.spectro_window.update_plot(data_to_plot)

        if self.display_mode == 'waveform':
            self.y_data[:-NUM_SAMPLES] = self.y_data[NUM_SAMPLES:]
            self.y_data[-NUM_SAMPLES:] = data_to_plot
            self.waveform_plot_item.setData(self.y_data)
        else:
            # librosaでメルスペクトログラム計算
            S = librosa.feature.melspectrogram(
                y=data_to_plot, 
                sr=SAMPLE_RATE, 
                n_fft=N_FFT, 
                hop_length=HOP_LENGTH, 
                n_mels=N_MELS
            )
            S_db = librosa.power_to_db(S, ref=1.0)

            num_new_frames = S_db.shape[1]
            if num_new_frames == 0:
                return

            if num_new_frames > SPECTRO_TIME_STEPS:
                S_db = S_db[:, -SPECTRO_TIME_STEPS:]
                num_new_frames = SPECTRO_TIME_STEPS

            self.spectro_data = np.roll(self.spectro_data, -num_new_frames, axis=1)
            self.spectro_data[:, -num_new_frames:] = S_db
            
            self.image_item.setImage(self.spectro_data.T, autoLevels=False)

    # --- 接続状態用スロット ---
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
        self.stop_plotting()
        if self.spectro_window:
            self.spectro_window.close()
        event.accept()


# --- サブウィンドウ（ヒートマップ専用）クラス ---
class SpectrogramWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ヒートマップ (Sub Window)")
        self.setGeometry(110, 110, 800, 400) 

        self.spectro_data = np.full((N_MELS, SPECTRO_TIME_STEPS), -60.0)

        main_layout = QVBoxLayout(self)
        pg.setConfigOptions(antialias=True)
        
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        main_layout.addWidget(self.plot_widget)
        
        self.image_item = pg.ImageItem()
        self.plot_widget.addItem(self.image_item)
        cmap = pg.colormap.get('viridis')
        self.image_item.setLookupTable(cmap.getLookupTable())
        
        self.image_item.setLevels([-30, 0]) 
        self.image_item.setImage(self.spectro_data.T)
        self._setup_spectrogram_view()

    def _setup_spectrogram_view(self):
        self.plot_widget.setTitle("ヒートマップ")
        self.plot_widget.setLabel('left', 'Mel Bins')
        self.plot_widget.setLabel('bottom', 'Time (Frames)')
        
        self.image_item.setRect(0, 0, SPECTRO_TIME_STEPS, N_MELS)
        self.plot_widget.setXRange(0, SPECTRO_TIME_STEPS)
        self.plot_widget.setYRange(0, N_MELS)
        self.plot_widget.showGrid(x=False, y=False)

    def update_plot(self, data_to_plot: np.ndarray):
        try:
            S = librosa.feature.melspectrogram(
                y=data_to_plot, 
                sr=SAMPLE_RATE, 
                n_fft=N_FFT, 
                hop_length=HOP_LENGTH, 
                n_mels=N_MELS
            )
            S_db = librosa.power_to_db(S, ref=1.0) 
            
            num_new_frames = S_db.shape[1]
            if num_new_frames == 0:
                return
            if num_new_frames > SPECTRO_TIME_STEPS:
                S_db = S_db[:, -SPECTRO_TIME_STEPS:]
                num_new_frames = SPECTRO_TIME_STEPS

            self.spectro_data = np.roll(self.spectro_data, -num_new_frames, axis=1)
            self.spectro_data[:, -num_new_frames:] = S_db
            self.image_item.setImage(self.spectro_data.T, autoLevels=False)
        except Exception as e:
            print(f"サブスペクトログラム更新エラー: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())