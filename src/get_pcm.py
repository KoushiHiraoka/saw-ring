import serial
import struct
import numpy as np
import sys
import signal

# 描画
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets

def analyze_signal(ser, curve, unpack_format, num_samples, SAMPLE_RATE):
    raw_data = ser.read(BUFFER_SIZE)

    if len(raw_data) == BUFFER_SIZE:
        pdm_samples_tuple = struct.unpack(unpack_format, raw_data)
        pdm_samples_np = np.array(pdm_samples_tuple, dtype=np.float32)
        fft_result = np.fft.fft(pdm_samples_np)
        amplitude = np.abs(fft_result) / num_samples
        freq = np.fft.fftfreq(num_samples, d=1/SAMPLE_RATE)

        positive_freq_indices = np.where(freq >= 0)
        amplitude_pos = amplitude[positive_freq_indices]
        freq_pos = freq[positive_freq_indices]

        # グラフを更新
        curve.setData(freq_pos, amplitude_pos)

def signal_handler(sig, frame):
    print("\nExiting program...")
    if ser.is_open:
        ser.close()
        print("Serial port closed.")
    sys.exit(0)

if __name__ == '__main__':
    SERIAL_PORT = '/dev/tty.usbmodem2101'
    BAUD_RATE = 921600
    BUFFER_SIZE = 2048
    SAMPLE_RATE = 44100
    num_samples = BUFFER_SIZE // 2
    unpack_format = f'<{num_samples}h'

    # シグナルハンドラを設定
    signal.signal(signal.SIGINT, signal_handler)

    app = pg.mkQApp("リアルタイム周波数解析")
    win = pg.GraphicsLayoutWidget(show=True, title="FFT Plot")
    win.resize(800, 400)
    win.setWindowTitle('リアルタイム周波数解析')
    pg.setConfigOptions(antialias=True)

    plot = win.addPlot(title="周波数スペクトル")
    plot.setLabel('bottom', '周波数 (Hz)')
    plot.setLabel('left', '振幅')
    plot.setLogMode(x=False, y=True)
    plot.setYRange(0, 10)
    curve = plot.plot(pen='y')

    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

    # QTimerを使用して非同期的にデータを処理
    timer = QtCore.QTimer()
    timer.timeout.connect(lambda: analyze_signal(ser, curve, unpack_format, num_samples, SAMPLE_RATE))
    timer.start(1)  # 50msごとに更新

    QtWidgets.QApplication.instance().exec()