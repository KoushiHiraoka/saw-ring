import sys
import serial
import serial.tools.list_ports
import numpy as np
import librosa
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel, QComboBox
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QTimer
import pyqtgraph as pg
from collections import deque
import time
import torch
import torch.nn as nn
from torch.nn import functional as F
import pyautogui
from utils import SimpleCNN, extract_pcen

# --- 基本設定 ---
# シリアル通信設定 (GUIで選択可能にします)
DEFAULT_BAUD_RATE = 2000000 

# 音声データ設定
SAMPLE_RATE = 24000
BUFFER_SIZE = 1024 # ESP32側から送られてくる1回のデータサイズに合わせる (int16なら2048byte)
DTYPE = np.int16
SPECTRO_TIME_STEPS = 100

# スペクトログラムの設定
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 128
SAMPLE_SIZE_FOR_INFERENCE = int(SAMPLE_RATE * 2)

INFERENCE_INTERVAL = 100
CONFIDENCE_THRESHOLD = 0.60
COOLDOWN_TIME = 3.0

# LABELS = ['double_tap', 'nail_tap','none', 'swipe', 'tap']
# MODEL_PATH = "../controller/cnn_model_weights_update.pth"

# --- データ受信を専門に行うWorkerクラス (シリアル版) ---
class SerialWorker(QObject):
    data_ready = pyqtSignal(np.ndarray)
    connection_failed = pyqtSignal(str)
    connection_lost = pyqtSignal(str)
    connection_success = pyqtSignal()

    def __init__(self, port, baud_rate):
        super().__init__()
        self.port = port
        self.baud_rate = baud_rate
        self.serial_conn = None
        self._is_running = True

    def run(self):
        """シリアル接続とデータ受信ループ"""
        try:
            self.serial_conn = serial.Serial(self.port, self.baud_rate, timeout=1)
            self.serial_conn.reset_input_buffer()
            self.connection_success.emit()
            print(f"Connected to {self.port} at {self.baud_rate}")
        except Exception as e:
            self.connection_failed.emit(f"接続失敗: {e}")
            return

        # 1サンプル2バイト (int16) なので、BUFFER_SIZE * 2 バイトずつ読む
        read_size = BUFFER_SIZE * 2 

        while self._is_running:
            try:
                if self.serial_conn.in_waiting >= read_size:
                    raw_data = self.serial_conn.read(read_size)
                    
                    if not raw_data:
                        continue

                    # バイナリデータをint16に変換
                    pcm_data = np.frombuffer(raw_data, dtype=DTYPE)
                    
                    if pcm_data.size > 0:
                        # -1.0 ~ 1.0 に正規化
                        normalized_data = pcm_data / 32768.0
                        self.data_ready.emit(normalized_data)
                else:
                    # データが足りないときは少し待つ（CPU負荷軽減）
                    self.thread().msleep(1)

            except Exception as e:
                self.connection_lost.emit(f"受信エラー: {e}")
                break
        
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
        print("シリアル受信スレッドを終了しました。")

    def stop(self):
        self._is_running = False


# --- メインウィンドウクラス ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-time Sensing (Serial)")
        self.setGeometry(100, 100, 1000, 600)

        self.display_mode = 'waveform'
        self.spectro_data = np.full((N_MELS, SPECTRO_TIME_STEPS), -80.0)
        
        # モデル読み込み
        # self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        # self.model = SimpleCNN(num_classes=len(LABELS)).to(self.device)
        # try:
        #     self.model.load_state_dict(torch.load(MODEL_PATH, map_location=self.device))
        #     self.model.eval()
        #     print("Model loaded successfully.")
        # except Exception as e:
        #     print(f"Model load failed: {e}")

        # 変数初期化
        self.last_action_time = 0
        self.last_recognized_gesture = "None"
        self.last_confidence = 0.0
        self.overlap_size = N_FFT - HOP_LENGTH
        self.prev_audio_main = np.zeros(self.overlap_size, dtype=np.float32)
        self.full_audio_buffer = deque(np.zeros(SAMPLE_SIZE_FOR_INFERENCE, dtype=np.float32), maxlen=SAMPLE_SIZE_FOR_INFERENCE)
        self.current_gesture_status = "認識: N/A"

        self.worker = None
        self.thread = None
        self.data_buffer = deque()

        self._setup_ui()
        self._init_plots()

        # サブウィンドウ
        self.spectro_window = SpectrogramWindow()
        self.spectro_window.hide()

        # タイマー設定
        self.plot_timer = QTimer(self)
        self.plot_timer.setInterval(16) # 60fps
        self.plot_timer.timeout.connect(self.triggered_update_plot)

        self.inference_timer = QTimer(self)
        self.inference_timer.setInterval(INFERENCE_INTERVAL)
        # self.inference_timer.timeout.connect(self._run_inference)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # プロットエリア
        pg.setConfigOptions(antialias=True)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        main_layout.addWidget(self.plot_widget, stretch=1)

        # コントロールパネル
        control_panel = QWidget()
        control_layout = QHBoxLayout(control_panel)
        control_layout.setContentsMargins(0, 5, 0, 0)
        
        # COMポート選択ボックス
        self.port_combo = QComboBox()
        self.refresh_ports()
        
        self.refresh_btn = QPushButton("更新")
        self.start_button = QPushButton("接続開始")
        self.stop_button = QPushButton("切断")
        self.toggle_button = QPushButton("ヒートマップ")
        
        self.stop_button.setEnabled(False)
        self.toggle_button.setEnabled(False)
        
        self.status_label = QLabel("状態: 待機中")
        
        control_layout.addWidget(QLabel("Port:"))
        control_layout.addWidget(self.port_combo)
        control_layout.addWidget(self.refresh_btn)
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.toggle_button)
        control_layout.addStretch()
        control_layout.addWidget(self.status_label)
        
        main_layout.addWidget(control_panel)

        # シグナル接続
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.start_button.clicked.connect(self.start_plotting)
        self.stop_button.clicked.connect(self.stop_plotting)
        self.toggle_button.clicked.connect(self.toggle_display_mode)

    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port in ports:
            self.port_combo.addItem(port.device)
        if not ports:
            self.port_combo.addItem("No ports found")

    def _init_plots(self):
        self.gesture_label = pg.TextItem(
            html=f'<div style="text-align: right;"><span style="color: #0078D4; font-size: 50pt;">{self.current_gesture_status}</span></div>', 
            anchor=(1, 0)
        )
        self.plot_widget.addItem(self.gesture_label)

        # 波形用
        self.plot_data_size = BUFFER_SIZE * 10
        self.y_data = np.zeros(self.plot_data_size)
        self.waveform_pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.waveform_plot_item = self.plot_widget.plot(self.y_data, pen=self.waveform_pen)
        
        # スペクトログラム用
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
        self.plot_widget.setTitle("リアルタイム波形 (Serial)")
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time')
        self.plot_widget.setYRange(-1.1, 1.1)
        self.plot_widget.setXRange(0, self.plot_data_size)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.waveform_plot_item.show()
        self.image_item.hide()
        self.gesture_label.setPos(self.plot_data_size, 1.1)
        self.gesture_label.show()

    def _setup_spectrogram_view(self):
        self.plot_widget.setTitle("ヒートマップ")
        self.plot_widget.setLabel('left', 'Mel Bins')
        self.plot_widget.setLabel('bottom', 'Time')
        self.image_item.setRect(0, 0, SPECTRO_TIME_STEPS, N_MELS)
        self.plot_widget.setXRange(0, SPECTRO_TIME_STEPS)
        self.plot_widget.setYRange(0, N_MELS)
        self.plot_widget.showGrid(x=False, y=False)
        self.waveform_plot_item.hide()
        self.image_item.show()

    def start_plotting(self):
        port = self.port_combo.currentText()
        if port == "No ports found" or not port:
            self.status_label.setText("ポートを選択してください")
            return

        if self.thread and self.thread.isRunning():
            return
        
        self.spectro_window.show()
        self.data_buffer.clear()
        
        # シリアルWorkerの作成
        self.thread = QThread()
        self.worker = SerialWorker(port, DEFAULT_BAUD_RATE)
        self.worker.moveToThread(self.thread)

        # シグナル接続
        self.worker.data_ready.connect(self.queue_data)
        self.worker.connection_success.connect(self._on_connection_success)
        self.worker.connection_failed.connect(self._on_connection_failed)
        self.worker.connection_lost.connect(self._on_connection_lost)
        
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

        self.plot_timer.start()
        self.inference_timer.start()
        self.start_button.setEnabled(False)
        self.status_label.setText("状態: <font color='orange'><b>接続中...</b></font>")

    def stop_plotting(self):
        self.plot_timer.stop()
        self.inference_timer.stop()
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
        self.status_label.setText("状態: <font color='gray'><b>切断</b></font>")

    def queue_data(self, new_data):
        self.data_buffer.append(new_data)
        self.full_audio_buffer.extend(new_data)

    def triggered_update_plot(self):
        if not self.data_buffer:
            return

        data_to_plot = self.data_buffer.popleft()

        if self.spectro_window:
            self.spectro_window.update_plot(data_to_plot)

        if self.display_mode == 'waveform':
            self.y_data[:-len(data_to_plot)] = self.y_data[len(data_to_plot):]
            self.y_data[-len(data_to_plot):] = data_to_plot
            self.waveform_plot_item.setData(self.y_data)
        else:
            # スペクトログラム計算 (簡易版)
            combined_y = np.concatenate((self.prev_audio_main, data_to_plot))
            self.prev_audio_main = data_to_plot[-self.overlap_size:]
            
            S = librosa.feature.melspectrogram(
                y=combined_y, sr=SAMPLE_RATE, n_fft=N_FFT, 
                hop_length=HOP_LENGTH, n_mels=N_MELS, center=False
            )
            S_db = librosa.power_to_db(S, ref=1.0)

            num_new_frames = S_db.shape[1]
            if num_new_frames > 0:
                if num_new_frames > SPECTRO_TIME_STEPS:
                    S_db = S_db[:, -SPECTRO_TIME_STEPS:]
                    num_new_frames = SPECTRO_TIME_STEPS

                self.spectro_data = np.roll(self.spectro_data, -num_new_frames, axis=1)
                self.spectro_data[:, -num_new_frames:] = S_db
                self.image_item.setImage(self.spectro_data.T, autoLevels=False)

    # def _run_inference(self):
    #     current_time = time.time()
    #     if current_time - self.last_action_time < COOLDOWN_TIME:
    #         self._update_gesture_display(f"{self.last_recognized_gesture} (Hold)", color="#FF0000")
    #         return
            
    #     y_samples = np.array(self.full_audio_buffer)
    #     # PCEN特徴量抽出 (utils.pyの実装に依存)
    #     try:
    #         input_tensor = extract_pcen(y_samples).to(self.device)
    #     except:
    #         return # バッファ不足などの場合はスキップ

    #     with torch.no_grad():
    #         outputs = self.model(input_tensor)
    #         probs = F.softmax(outputs, dim=1).squeeze().cpu().numpy()
            
    #     label_idx = np.argmax(probs)
    #     confidence = probs[label_idx]
    #     label_name = LABELS[label_idx]

    #     # 表示ロジック
    #     if label_name == 'none':
    #         self._update_gesture_display(f"--- ({confidence*100:.1f}%)", color="#555555")
        
    #     elif confidence > CONFIDENCE_THRESHOLD:
    #         # 認識成功時の処理
    #         display_name = label_name
    #         if label_name == "double_tap":
    #             display_name = "Double Tap"
    #             # pyautogui.press('right') # 必要に応じて有効化
    #         elif label_name == "swipe":
    #             display_name = "Swipe"
            
    #         self._update_gesture_display(f"{display_name} ({confidence*100:.1f}%)", color="#FF0000")
    #         self.last_recognized_gesture = display_name
    #         self.last_action_time = current_time
    #         print(f"[DETECT] {label_name} : {confidence:.2f}")
    #     else:
    #         self._update_gesture_display(f"{label_name} ({confidence*100:.1f}%)", color="#555555")

    def _update_gesture_display(self, text, color='#0078D4'):
        html = f'<div style="text-align: right;"><span style="color: {color}; font-size: 50pt; font-weight: bold;">{text}</span></div>'
        self.gesture_label.setHtml(html)
        if self.display_mode == 'waveform':
            self.gesture_label.setPos(self.plot_data_size, 1.1)
        else:
            self.gesture_label.setPos(SPECTRO_TIME_STEPS, N_MELS)

    def _on_connection_success(self):
        self.stop_button.setEnabled(True)
        self.toggle_button.setEnabled(True)
        self.status_label.setText("状態: <font color='green'><b>接続成功 (Serial)</b></font>")
    
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


# --- サブウィンドウクラス (変更なし) ---
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
        self.overlap_size = N_FFT - HOP_LENGTH
        self.prev_audio_sub = np.zeros(self.overlap_size, dtype=np.float32)
        self._setup_view()

    def _setup_view(self):
        self.plot_widget.setLabel('left', 'Mel Bins')
        self.plot_widget.setLabel('bottom', 'Time')
        self.image_item.setRect(0, 0, SPECTRO_TIME_STEPS, N_MELS)
        self.plot_widget.setXRange(0, SPECTRO_TIME_STEPS)
        self.plot_widget.setYRange(0, N_MELS)
        self.plot_widget.showGrid(x=False, y=False)

    def update_plot(self, data_to_plot: np.ndarray):
        try:
            combined_y = np.concatenate((self.prev_audio_sub, data_to_plot))
            self.prev_audio_sub = data_to_plot[-self.overlap_size:]
            S = librosa.feature.melspectrogram(
                y=combined_y, sr=SAMPLE_RATE, n_fft=N_FFT, 
                hop_length=HOP_LENGTH, n_mels=N_MELS, center=False
            )
            S_db = librosa.power_to_db(S, ref=1.0)
            num = S_db.shape[1]
            if num == 0: return
            if num > SPECTRO_TIME_STEPS:
                S_db = S_db[:, -SPECTRO_TIME_STEPS:]
                num = SPECTRO_TIME_STEPS
            self.spectro_data = np.roll(self.spectro_data, -num, axis=1)
            self.spectro_data[:, -num:] = S_db
            self.image_item.setImage(self.spectro_data.T, autoLevels=False)
        except:
            pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())