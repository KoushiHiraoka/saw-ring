import serial
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import struct

# --- シリアルポート設定 ---
# '/dev/tty.usbmodemXXXX' or '/dev/ttyUSBx'
SERIAL_PORT = '/dev/tty.usbmodem21301'
BAUD_RATE = 115200 # ESP32スケッチと合わせる

# --- オーディオ設定 ---
SAMPLE_RATE = 24000 #Hz
BUFFER_SIZE_SAMPLES = 1024 
# バッファサイズをバイト単位で計算 (16ビットデータなので2バイト/サンプル)
BUFFER_SIZE_BYTES = BUFFER_SIZE_SAMPLES * 2

# --- FFT設定 ---
FFT_SIZE = BUFFER_SIZE_SAMPLES # FFTのポイント数 (バッファサイズと同じ)
# 周波数軸を計算 (Nyquist周波数まで)
# FFTの結果は対称なので、半分だけ使う
freqs = np.fft.fftfreq(FFT_SIZE, d=1/SAMPLE_RATE)[:FFT_SIZE//2]

# --- Matplotlib初期設定 ---
# # アニメーションを高速化するための対話モードオフ
# plt.ion()
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
fig.suptitle('Real-time Audio Waveform and FFT')

# 時間領域波形プロットの初期化
line1, = ax1.plot(np.arange(BUFFER_SIZE_SAMPLES) / SAMPLE_RATE, np.zeros(BUFFER_SIZE_SAMPLES), color='blue')
ax1.set_title('Time Domain Waveform')
ax1.set_xlabel('Time (s)')
ax1.set_ylabel('Amplitude')
ax1.set_ylim(-32768, 32767) # 16bit signed int の範囲
ax1.grid(True)

# 周波数スペクトルプロットの初期化
line2, = ax2.plot(freqs, np.zeros(FFT_SIZE // 2), color='red')
ax2.set_title('Frequency Spectrum (FFT)')
ax2.set_xlabel('Frequency (Hz)')
ax2.set_ylabel('Magnitude (dB)')
ax2.set_xlim(0, SAMPLE_RATE / 2) # Nyquist周波数まで
ax2.set_ylim(-100, 0) # 適当なdB範囲。後で自動調整しても良い
ax2.grid(True)


# シリアルポートの初期化
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=0.1) # timeoutを設定
    print(f"Connected to serial port: {SERIAL_PORT}")
except serial.SerialException as e:
    print(f"Error opening serial port: {e}")
    print("Please check the SERIAL_PORT setting and ensure ESP32 is connected.")
    exit()

# リアルタイム更新関数
def update(frame):
    try:
        # シリアルバッファから指定バイト数だけ読み込み
        # read_until() を使うと、読み込みがより確実になる場合がありますが、
        # 今回は固定長で read() を使います
        raw_bytes = ser.read(BUFFER_SIZE_BYTES)
        print(f"Raw bytes: {raw_bytes}")

        if len(raw_bytes) == BUFFER_SIZE_BYTES:
            # バイトデータを16ビット整数（リトルエンディアン）のNumPy配列に変換
            # '<h' はリトルエンディアンのsigned short (2バイト)
            # unpack でタプルを返し、それを numpy array に変換
            # bytearray.fromhex も検討できるが、struct.unpack_from が効率的
            samples = np.array(struct.unpack('<' + 'h' * BUFFER_SIZE_SAMPLES, raw_bytes), dtype=np.int16)

            # --- 時間領域波形を更新 ---
            line1.set_ydata(samples)

            # --- 周波数スペクトルを計算・更新 ---
            # Hamming窓を適用してリーケージを低減
            windowed_samples = samples * np.hamming(FFT_SIZE)
            fft_result = np.fft.fft(windowed_samples)
            # マグニチュードを計算し、dBスケールに変換
            magnitude = 20 * np.log10(np.abs(fft_result[:FFT_SIZE//2]))
            line2.set_ydata(magnitude)

            # dBスケールのy軸を自動調整（オプション）
            # min_db = np.min(magnitude) - 10 if len(magnitude) > 0 else -100
            # max_db = np.max(magnitude) + 10 if len(magnitude) > 0 else 0
            # ax2.set_ylim(min_db, max_db)

        else:
            # 必要なバイト数が読み込めなかった場合 (データが途切れたなど)
            # print(f"Warning: Expected {BUFFER_SIZE_BYTES} bytes, got {len(raw_bytes)} bytes.")
            pass # スキップして次のフレームへ

    except Exception as e:
        print(f"Error during data processing: {e}")
        # 例外が発生してもアニメーションを停止しないようにする
        # return [] # Matplotlib Animationの仕様により、エラー時は空リストを返す

    # 更新されたLineオブジェクトを返す
    return line1, line2

# アニメーションの開始
# interval: 更新間隔 (ms), blit=True: 高速描画 (一部環境で問題がある場合falseに)
ani = animation.FuncAnimation(fig, update, interval=50, blit=False)

# グラフを表示
plt.show()

# # プログラム終了時にシリアルポートを閉じる (Ctrl+Cなどで終了されることを想定)
# def on_close(event):
#     if ser.is_open:
#         ser.close()
#         print("Serial port closed.")

# fig.canvas.mpl_connect('close_event', on_close)

# # ここに到達することは通常ないが、明示的にポートを閉じる
# # プログラムを強制終了しない限り、on_closeイベントハンドラが呼ばれる
# # ser.close()

if __name__ == "__main__":
    try:
        plt.show()
    except KeyboardInterrupt:
        print("Interrupted by user, closing serial port.")
        if ser.is_open:
            ser.close()
            print("Serial port closed.")
    except Exception as e:
        print(f"Unexpected error: {e}")
        if ser.is_open:
            ser.close()
            print("Serial port closed.")