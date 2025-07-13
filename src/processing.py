import serial
import struct
import collections
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import argparse

# --- 引数でポート名とボーレートを指定 ---------------------------------------
parser = argparse.ArgumentParser(description="ESP32 PCM realtime plot")
parser.add_argument("--port", required=True, help="COMポート名 例: COM3 / /dev/ttyUSB0")
parser.add_argument("--baud", type=int, default=921600, help="ボーレート (デフォルト 921600)")
parser.add_argument("--buf", type=int, default=4096, help="表示バッファ長 (サンプル数)")
args = parser.parse_args()

# --- シリアルポートを開く ------------------------------------------------------
ser = serial.Serial(args.port, args.baud)
print(f"Opened {args.port} @ {args.baud}bps")

# --- 描画用バッファ ------------------------------------------------------------
buf = collections.deque([0]*args.buf, maxlen=args.buf)
# --- matplotlib の準備 ---------------------------------------------------------
fig, ax = plt.subplots(figsize=(10, 4))
line, = ax.plot(range(args.buf), list(buf))
# ax.set_ylim(-32768, 32767)
ax.set_ylim(-52768, 52767)
ax.set_xlim(0, args.buf)
ax.set_title("Realtime PCM from ESP32")
ax.set_xlabel("Sample")
ax.set_ylabel("Amplitude (int16)")

# --- アニメーション関数 --------------------------------------------------------
def update(frame):
    while ser.in_waiting >= 2:
        # 1サンプル = 2バイト little-endian signed16
        raw = ser.read(2)  # 2バイトまとめて読む
        sample = struct.unpack('<h', raw)[0]
        buf.append(sample)
    line.set_ydata(buf)
    return line,

ani = animation.FuncAnimation(fig, update, interval=20, blit=True)
plt.show()

#実行
# python processing.py --port /dev/cu.usbserial-D30AK57K --baud 921600