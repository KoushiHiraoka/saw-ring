import wave
import numpy as np
import matplotlib.pyplot as plt

def plot_waveform(wav_file, name):
    with wave.open(wav_file, 'rb') as wf:
        n_channels = wf.getnchannels()  # チャンネル数
        sample_width = wf.getsampwidth()  # サンプル幅
        frame_rate = wf.getframerate()  # サンプリングレート
        n_frames = wf.getnframes()  # 総フレーム数

        print(f"Channels: {n_channels}")
        print(f"Sample Width: {sample_width} bytes")
        print(f"Frame Rate: {frame_rate} Hz")
        print(f"Total Frames: {n_frames}")

        # WAVデータを読み取る
        frames = wf.readframes(n_frames)
        # numpy配列に変換
        waveform = np.frombuffer(frames, dtype=np.int16)
        waveform = waveform / 15000
        

        # 時間軸を計算
        time = np.linspace(0, n_frames / frame_rate, num=n_frames)

        plt.figure(figsize=(10, 4))
        plt.plot(time, waveform, color='blue')
        plt.title(f"Waveform ({name})")
        plt.xlabel("Time (seconds)")
        plt.ylabel("Amplitude")
        plt.ylim(-1, 1)  # 振幅の範囲を設定
        plt.yticks([-1, 0, 1])
        plt.axhline(0, color='gray', linestyle='--', linewidth=0.8)  # y=0の線を追加
        plt.show()

if __name__ == "__main__":
    # 可視化したいWAVファイルのパスを指定
    dir = "noise_" 
    num = 90


    wav_file_path = f"../data_collection/data/{dir}/swipe_{num}.wav"  # 適切なパスに変更してください
    plot_waveform(wav_file_path, dir)