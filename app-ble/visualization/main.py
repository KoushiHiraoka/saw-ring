import sys
import asyncio
import numpy as np
from scipy import fft
from bleak import BleakScanner, BleakClient
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QPushButton, QLabel
)
from PyQt6.QtCore import QThread, pyqtSignal, QObject
import pyqtgraph as pg
from collections import deque
from PyQt6.QtCore import QTimer

# --- 基本設定 (BLE用に変更) ---
DEVICE_NAME = "SAW-Ring"
CHARACTERISTIC_UUID = "13b73498-101b-4f22-aa2b-a72c6710e54f"

# --- データ処理設定 (ESP32のコードと合わせる) ---
BUFFER_SIZE = 1024  # 処理単位となるデータサイズ (バイト)
SAMPLE_RATE = 24000
DTYPE = np.int16
NUM_SAMPLES = BUFFER_SIZE // np.dtype(DTYPE).itemsize

# --- データ受信を専門に行うWorkerクラス (BLE対応版) ---
class DataWorker(QObject):
    data_ready = pyqtSignal(np.ndarray)
    connection_failed = pyqtSignal(str)
    connection_lost = pyqtSignal(str)
    connection_success = pyqtSignal()
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._is_running = True
        self.buffer = b''
        # asyncioのイベントループを安全に停止させるためのイベント
        self.disconnected_event = asyncio.Event()

    def notification_handler(self, sender, data: bytearray):
        
        # self.buffer += data
        
        # # 定められたバッファサイズに達するまでデータを溜める
        # while len(self.buffer) >= BUFFER_SIZE:
        #     data_to_process = self.buffer[:BUFFER_SIZE]
        #     self.buffer = self.buffer[BUFFER_SIZE:]
            
        pcm_data = np.frombuffer(data, dtype=DTYPE)
        if pcm_data.size > 0:
            normalized_data = pcm_data / 32768.0
            self.data_ready.emit(normalized_data)

    async def main_ble_loop(self):
        """BLEデバイスのスキャン、接続、データ受信待機を行うメインループ"""
        self.status_update.emit("状態: <font color='blue'><b>BLEデバイスを検索中...</b></font>")
        device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=10.0)
        
        if not device:
            self.connection_failed.emit(f"デバイス '{DEVICE_NAME}' が見つかりません。")
            return

        self.status_update.emit(f"状態: <font color='orange'><b>'{DEVICE_NAME}' に接続中...</b></font>")

        def on_disconnect(client):
            print("BLE接続が切断されました。")
            self.disconnected_event.set() # イベントをセットして待機ループを終了させる
            if self._is_running:
                self.connection_lost.emit("BLE接続が予期せず切断されました。")

        async with BleakClient(device, disconnected_callback=on_disconnect) as client:
            if not client.is_connected:
                self.connection_failed.emit("デバイスへの接続に失敗しました。")
                return
            
            self.connection_success.emit()
            print("BLE接続成功。通知の受信を開始します。")
            
            await client.start_notify(CHARACTERISTIC_UUID, self.notification_handler)
            
            # stop()が呼ばれるか、接続が切断されるまでここで待機
            await self.disconnected_event.wait()
        
        print("BLEクライアントの処理が終了しました。")

    def run(self):
        """Qtスレッドからasyncioのイベントループを開始する"""
        try:
            asyncio.run(self.main_ble_loop())
        except Exception as e:
            self.connection_failed.emit(f"非同期処理エラー: {e}")
        print("データ受信スレッドを終了しました。")

    def stop(self):
        """データ受信ループの停止を要求する"""
        self._is_running = False
        self.disconnected_event.set()

# --- メインウィンドウクラス (UI部分はほぼ変更なし) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("リアルタイム波形・周波数解析")
        self.setGeometry(100, 100, 1000, 600)

        self.display_mode = 'waveform'
        
        self._setup_ui()
        self._init_plots()

        self.worker = None
        self.thread = None

        self.data_buffer = deque()
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
        
        self.start_button = QPushButton("📡 接続開始")
        self.stop_button = QPushButton("🔌 切断")
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
        self.plot_data_size = NUM_SAMPLES * 10
        self.y_data = np.zeros(self.plot_data_size)
        self.waveform_pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.waveform_plot_item = self.plot_widget.plot(self.y_data, pen=self.waveform_pen)

        self.fft_freqs = fft.rfftfreq(NUM_SAMPLES, 1 / SAMPLE_RATE)
        self.fft_power = np.zeros(len(self.fft_freqs))
        self.fft_pen = pg.mkPen(color=(215, 60, 0), width=2)
        self.fft_plot_item = self.plot_widget.plot(self.fft_freqs, self.fft_power, pen=self.fft_pen)
        
        self.fft_plot_item.hide()
        self._setup_waveform_view()

    def toggle_display_mode(self):
        if self.display_mode == 'waveform':
            self.display_mode = 'fft'
            self.toggle_button.setText("📉 波形表示へ")
            self._setup_fft_view()
        else:
            self.display_mode = 'waveform'
            self.toggle_button.setText("📊 周波数解析へ (FFT)")
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
        self.fft_plot_item.hide()

    def _setup_fft_view(self):
        self.plot_widget.setTitle("リアルタイム周波数解析 (FFT)")
        self.plot_widget.setLabel('left', 'Power (Magnitude)')
        self.plot_widget.setLabel('bottom', 'Frequency (Hz)')
        self.plot_widget.setXRange(0, SAMPLE_RATE / 2)
        self.plot_widget.setYRange(0, 30)
        self.plot_widget.setLogMode(x=False, y=False)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.waveform_plot_item.hide()
        self.fft_plot_item.show()

    def start_plotting(self):
        if self.thread and self.thread.isRunning():
            return
        
        self.data_buffer.clear()
        self.thread = QThread()
        self.worker = DataWorker()
        self.worker.moveToThread(self.thread)

        self.worker.data_ready.connect(self.queue_data)
        self.worker.connection_success.connect(self._on_connection_success)
        self.worker.connection_failed.connect(self._on_connection_failed)
        self.worker.connection_lost.connect(self._on_connection_lost)
        self.worker.status_update.connect(self._on_status_update)
        
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

        self.plot_timer.start()
        
        self.start_button.setEnabled(False)

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
        """Workerからデータを受け取り、バッファに追加するだけ"""
        self.data_buffer.append(new_data)

    def triggered_update_plot(self):
        """QTimerによって呼び出され、バッファのデータをまとめて描画する"""
        if not self.data_buffer:
            return

        # バッファに溜まったデータを全て連結して一つの塊にする
        all_new_data = np.concatenate(list(self.data_buffer))
        self.data_buffer.clear()
        
        # 描画処理は update_plot に任せる
        self.update_plot(all_new_data)

    def update_plot(self, new_data):
        """実際にプロットを更新する処理"""
        num_new_samples = len(new_data)
        if num_new_samples == 0:
            return

        if self.display_mode == 'waveform':
            # np.rollを使う代わりに、スライスで効率的に更新
            self.y_data[:-num_new_samples] = self.y_data[num_new_samples:]
            self.y_data[-num_new_samples:] = new_data
            self.waveform_plot_item.setData(self.y_data)
        else: # 'fft'
            # FFTは最後の一定数のデータで行う (例: NUM_SAMPLES)
            fft_data = new_data[-NUM_SAMPLES:]
            processed_data = fft_data - np.mean(fft_data)
            window = np.hanning(len(processed_data))
            fft_result = fft.rfft(processed_data * window)
            self.fft_power = np.abs(fft_result)
            self.fft_plot_item.setData(self.fft_freqs, self.fft_power)

    # --- 接続状態に関するスロット ---
    def _on_connection_success(self):
        self.stop_button.setEnabled(True)
        self.toggle_button.setEnabled(True)
        self.status_label.setText("状態: <font color='green'><b>接続成功</b></font>")
    
    def _on_status_update(self, message):
        self.status_label.setText(message)
        
    def _on_connection_failed(self, message):
        self.status_label.setText(f"状態: <font color='red'><b>{message}</b></font>")
        self.start_button.setEnabled(True)

    def _on_connection_lost(self, message):
        self.status_label.setText(f"状態: <font color='red'><b>{message}</b></font>")
        self.stop_plotting()

    def closeEvent(self, event):
        self.stop_plotting()
        event.accept()

# --- アプリケーションの実行 ---
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())