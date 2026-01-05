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

# --- Configuration ---
UDP_IP = "0.0.0.0" # Listen on all network interfaces
UDP_PORT = 8000    # Must match the port in your ESP32 code

# Audio Settings
SAMPLE_RATE = 24000
BUFFER_SIZE = 1024  # Size of the UDP packet payload (bytes)
DTYPE = np.int16   # Data type sent by ESP32 (16-bit PCM)
SPECTRO_TIME_STEPS = 100

# Spectrogram Settings
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 128

# --- UDP Worker Class ---
class UDPWorker(QObject):
    data_ready = pyqtSignal(np.ndarray)
    status_update = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.sock = None
        self._is_running = True

    def run(self):
        """UDP listening loop"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sock.bind((UDP_IP, UDP_PORT))
            # Increase buffer size to prevent packet drops during heavy load
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            
            self.status_update.emit(f"Listening on UDP Port {UDP_PORT}")
            print(f"Listening on UDP port {UDP_PORT}...")
            
        except Exception as e:
            self.status_update.emit(f"Bind Error: {e}")
            return

        while self._is_running:
            try:
                # Receive data (read slightly more than BUFFER_SIZE to be safe)
                data, addr = self.sock.recvfrom(BUFFER_SIZE * 4)
                
                if not data: continue

                # Convert binary data to numpy array
                pcm_data = np.frombuffer(data, dtype=DTYPE)
                
                if pcm_data.size > 0:
                    # Normalize to -1.0 ~ 1.0 range
                    normalized_data = pcm_data / 32768.0
                    self.data_ready.emit(normalized_data)

            except Exception as e:
                print(f"Receive Error: {e}")
        
        if self.sock: self.sock.close()

    def stop(self):
        self._is_running = False


# --- Main Window Class ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Real-time Waveform and Spectrogram (UDP)")
        self.setGeometry(100, 100, 1000, 600)

        self.display_mode = 'waveform'
        
        # Buffer for spectrogram visualization
        self.spectro_data = np.full((N_MELS, SPECTRO_TIME_STEPS), -80.0)
        self.overlap_size = N_FFT - HOP_LENGTH
        self.prev_audio_main = np.zeros(self.overlap_size, dtype=np.float32)

        self.worker = None
        self.thread = None
        self.data_buffer = deque()

        self._setup_ui()
        self._init_plots()

        # Create Spectrogram Sub-window
        self.spectro_window = SpectrogramWindow()
        self.spectro_window.hide()

        # Plot Update Timer (approx 60 FPS)
        self.plot_timer = QTimer(self)
        self.plot_timer.setInterval(16) 
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
        
        self.start_button = QPushButton("Start Receiving")
        self.stop_button = QPushButton("Stop")
        self.toggle_button = QPushButton("Show Spectrogram")
        self.stop_button.setEnabled(False)
        self.toggle_button.setEnabled(False)
        
        self.status_label = QLabel("Status: Idle")
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.toggle_button)
        control_layout.addStretch()
        control_layout.addWidget(self.status_label)
        
        main_layout.addWidget(control_panel)

        self.start_button.clicked.connect(self.start_receiving)
        self.stop_button.clicked.connect(self.stop_receiving)
        self.toggle_button.clicked.connect(self.toggle_display_mode)

    def _init_plots(self):
        # Waveform Plot
        self.plot_data_size = SAMPLE_RATE * 2 # Display 2 seconds of data
        self.y_data = np.zeros(self.plot_data_size)
        self.waveform_pen = pg.mkPen(color=(0, 120, 215), width=2)
        self.waveform_plot_item = self.plot_widget.plot(self.y_data, pen=self.waveform_pen)
        
        # Spectrogram ImageItem
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
            self.toggle_button.setText("Show Waveform")
            self._setup_spectrogram_view()
        else:
            self.display_mode = 'waveform'
            self.toggle_button.setText("Show Spectrogram")
            self._setup_waveform_view()

    def _setup_waveform_view(self):
        self.plot_widget.setTitle("Real-time Waveform")
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time')
        self.plot_widget.setYRange(-1.1, 1.1)
        self.plot_widget.setXRange(0, self.plot_data_size)
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.waveform_plot_item.show()
        self.image_item.hide()

    def _setup_spectrogram_view(self):
        self.plot_widget.setTitle("Spectrogram")
        self.plot_widget.setLabel('left', 'Mel Bins')
        self.plot_widget.setLabel('bottom', 'Time')
        
        self.image_item.setRect(0, 0, SPECTRO_TIME_STEPS, N_MELS)
        self.plot_widget.setXRange(0, SPECTRO_TIME_STEPS)
        self.plot_widget.setYRange(0, N_MELS)
        self.plot_widget.showGrid(x=False, y=False)

        self.waveform_plot_item.hide()
        self.image_item.show()

    def start_receiving(self):
        if self.thread and self.thread.isRunning():
            return
        
        self.spectro_window.show()
        self.data_buffer.clear()
        
        self.thread = QThread()
        self.worker = UDPWorker()
        self.worker.moveToThread(self.thread)

        self.worker.data_ready.connect(self.queue_data)
        self.worker.status_update.connect(self.update_status)
        
        self.thread.started.connect(self.worker.run)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

        self.plot_timer.start()
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.toggle_button.setEnabled(True)

    def stop_receiving(self):
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
        self.status_label.setText("Status: <font color='red'><b>Stopped</b></font>")

    def queue_data(self, new_data):
        self.data_buffer.append(new_data)

    def update_status(self, msg):
        self.status_label.setText(f"Status: <font color='green'><b>{msg}</b></font>")

    def triggered_update_plot(self):
        """Called by QTimer to update the plots"""
        if not self.data_buffer:
            return

        # Process all available data chunks to catch up
        while self.data_buffer:
            data_to_plot = self.data_buffer.popleft()

            # Update Sub Window
            if self.spectro_window and self.spectro_window.isVisible():
                self.spectro_window.update_plot(data_to_plot)

            if self.display_mode == 'waveform':
                self.y_data[:-len(data_to_plot)] = self.y_data[len(data_to_plot):]
                self.y_data[-len(data_to_plot):] = data_to_plot
                self.waveform_plot_item.setData(self.y_data)
            else:
                # Calculate Spectrogram
                combined_y = np.concatenate((self.prev_audio_main, data_to_plot))
                self.prev_audio_main = data_to_plot[-self.overlap_size:]
                
                S = librosa.feature.melspectrogram(
                    y=combined_y, 
                    sr=SAMPLE_RATE, 
                    n_fft=N_FFT, 
                    hop_length=HOP_LENGTH, 
                    n_mels=N_MELS,
                    center = False
                )
                S_db = librosa.power_to_db(S, ref=1.0)

                num_new_frames = S_db.shape[1]
                if num_new_frames == 0:
                    continue

                if num_new_frames > SPECTRO_TIME_STEPS:
                    S_db = S_db[:, -SPECTRO_TIME_STEPS:]
                    num_new_frames = SPECTRO_TIME_STEPS

                self.spectro_data = np.roll(self.spectro_data, -num_new_frames, axis=1)
                self.spectro_data[:, -num_new_frames:] = S_db
                self.image_item.setImage(self.spectro_data.T, autoLevels=False)

    def closeEvent(self, event):
        self.stop_receiving()
        if self.spectro_window:
            self.spectro_window.close()
        event.accept()


# --- Sub Window (Spectrogram) ---
class SpectrogramWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Spectrogram (Sub Window)")
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

        self._setup_spectrogram_view()

    def _setup_spectrogram_view(self):
        self.plot_widget.setTitle("Spectrogram")
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
                y=combined_y, 
                sr=SAMPLE_RATE, 
                n_fft=N_FFT, 
                hop_length=HOP_LENGTH, 
                n_mels=N_MELS,
                center=False
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
            print(f"Spectrogram Update Error: {e}")


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())