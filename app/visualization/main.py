import sys
import socket
import numpy as np
from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import QThread, pyqtSignal, QObject
import pyqtgraph as pg

# --- 基本設定 ---
ESP_IP = "192.168.4.1"
PORT = 8000
BUFFER_SIZE = 1024
SAMPLE_RATE = 24000
DTYPE = np.int16
NUM_SAMPLES = BUFFER_SIZE // np.dtype(DTYPE).itemsize

# --- データ受信を専門に行うWorkerクラス ---
# QThread内で動作し、GUIをブロックしないようにする
class DataWorker(QObject):
    # 新しいデータを受信したら、このシグナルを送信（emit）する
    data_ready = pyqtSignal(np.ndarray)

    def __init__(self):
        super().__init__()
        self.client = None
        self.is_running = True

    def run(self):
        """TCP接続とデータ受信ループ"""
        buffer = b''
        try:
            self.client = socket.create_connection((ESP_IP, PORT), timeout=5)
            print(f"接続成功: {ESP_IP}:{PORT}")
        except Exception as e:
            print(f"接続失敗: {e}")
            return # 接続に失敗したらスレッドを終了

        while self.is_running:
            try:
                raw_data = self.client.recv(BUFFER_SIZE)
                if not raw_data:
                    print("接続が相手方から切断されました。")
                    break

                buffer += raw_data

                if len(buffer) >= BUFFER_SIZE:
                    data_to_process = buffer[:BUFFER_SIZE]
                    buffer = buffer[BUFFER_SIZE:]
                    pcm_data = np.frombuffer(data_to_process, dtype=DTYPE)
                    
                    if pcm_data.size > 0:
                        # 正規化してシグナルを送信
                        normalized_data = pcm_data / 32768.0
                        self.data_ready.emit(normalized_data)

            except Exception as e:
                print(f"受信エラー: {e}")
                break
        
        if self.client:
            self.client.close()
        print("データ受信スレッドを終了しました。")

    def stop(self):
        self.is_running = False


# --- メインウィンドウクラス ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyQtGraph リアルタイム波形モニター")
        self.setGeometry(100, 100, 1000, 500)

        # PyQtGraphのプロットウィジェットを作成
        self.plot_widget = pg.PlotWidget()
        self.setCentralWidget(self.plot_widget)
        
        # プロットの外観を設定
        self.plot_widget.setBackground('w')
        self.plot_widget.setYRange(-1, 1, padding=0)
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time (Samples)')
        self.plot_widget.showGrid(x=True, y=True)
        
        # 表示するデータ全体のサイズ (スクロールさせるため、一度に受信する量より大きくする)
        self.plot_data_size = NUM_SAMPLES * 10 
        self.x_data = np.arange(self.plot_data_size)
        self.y_data = np.zeros(self.plot_data_size)

        # 描画する線（Pen）を作成
        self.pen = pg.mkPen(color=(0, 0, 255), width=2)
        self.plot_data_item = self.plot_widget.plot(self.x_data, self.y_data, pen=self.pen)
        
        # データ受信スレッドを開始
        self.setup_worker_thread()
    
    def setup_worker_thread(self):
        self.thread = QThread()
        self.worker = DataWorker()
        self.worker.moveToThread(self.thread)

        # Workerスレッドが開始したら、worker.runを実行
        self.thread.started.connect(self.worker.run)
        # Workerからdata_readyシグナルが来たら、update_plotを呼び出す
        self.worker.data_ready.connect(self.update_plot)
        
        self.thread.start()

    def update_plot(self, new_data):
        """新しいデータでプロットを更新する（リングバッファ方式）"""
        # 既存のデータを左にシフト
        self.y_data = np.roll(self.y_data, -NUM_SAMPLES)
        # 新しいデータを末尾に追加
        self.y_data[-NUM_SAMPLES:] = new_data
        # プロットデータを更新
        self.plot_data_item.setData(self.x_data, self.y_data)

    def closeEvent(self, event):
        """ウィンドウが閉じられたときの処理"""
        print("ウィンドウを閉じています...")
        self.worker.stop()  # スレッドに停止を指示
        self.thread.quit()  # スレッドを終了
        self.thread.wait()  # スレッドが完全に終了するのを待つ
        event.accept()

# --- アプリケーションの実行 ---
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())