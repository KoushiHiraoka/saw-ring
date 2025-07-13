#!/usr/bin/env python3
# realtime_pcm_fft.py
import serial, struct, collections, argparse
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# --- 引数 ------------------------------------------------------------
parser = argparse.ArgumentParser(description="ESP32 PCM + FFT realtime plot")
parser.add_argument("--port",   required=True,              help="COMポート名 例: COM3 / /dev/ttyUSB0")
parser.add_argument("--baud",   type=int, default=115200,   help="ボーレート (デフォルト 921600)")
parser.add_argument("--buf",    type=int, default=2048,     help="FFT & 波形バッファ長 (サンプル数・2のべき乗推奨)")
parser.add_argument("--fs",     type=int, default=24000,    help="サンプリングレート [Hz] (デフォルト 48000)")
args = parser.parse_args()

# --- シリアルオープン ------------------------------------------------
ser = serial.Serial(args.port, args.baud)
print(f"Opened {args.port} @ {args.baud}bps")

# --- バッファ --------------------------------------------------------
buf = collections.deque([0]*args.buf, maxlen=args.buf)   # 時系列バッファ

# --- プロット準備 ----------------------------------------------------
fig, (ax_t, ax_f) = plt.subplots(2, 1, figsize=(10, 6))

# 時系列プロット
line_t, = ax_t.plot(range(args.buf), list(buf))
ax_t.set_ylim(-32768, 32767)
ax_t.set_xlim(0, args.buf)
ax_t.set_title("Realtime PCM from ESP32")
ax_t.set_xlabel("Sample")
ax_t.set_ylabel("Amplitude (int16)")

# FFTプロット
# x 軸: 周波数、y 軸: 振幅(dB)
freqs = np.fft.rfftfreq(args.buf, d=1/args.fs)
line_f, = ax_f.semilogx(freqs, np.zeros_like(freqs))     # 対数軸で見やすく
ax_f.set_ylim(-120, 0)                                   # dBスケール
ax_f.set_xlim(20, args.fs/2)
ax_f.set_xlabel("Frequency (Hz)")
ax_f.set_ylabel("Magnitude (dB)")
ax_f.grid(True, which="both", ls="--", alpha=0.3)
ax_f.set_title("Realtime FFT Spectrum")

# --- アニメーション更新関数 ------------------------------------------
def update(frame):
    # --- シリアルから読み取ってバッファに貯める ---
    while ser.in_waiting >= 2:                       # 2バイトずつ読む
        raw = ser.read(2)
        sample = struct.unpack('<h', raw)[0]         # int16 little-endian
        buf.append(sample)

    # ========== 時系列プロット ==========
    line_t.set_ydata(buf)

    # ========== FFT計算 & プロット =========
    pcm_np = np.array(buf, dtype=np.float32)

    # 窓関数でリーク抑制（ハミング窓）
    windowed = pcm_np * np.hamming(len(pcm_np))
    fft_mag = np.abs(np.fft.rfft(windowed)) + 1e-12  # 1e-12 で log(0) 回避
    fft_db  = 20 * np.log10(fft_mag / np.max(fft_mag))

    line_f.set_ydata(fft_db)

    return line_t, line_f

ani = animation.FuncAnimation(fig, update, interval=50, blit=True)
plt.tight_layout()
plt.show()

