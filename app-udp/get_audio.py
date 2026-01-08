import tkinter as tk
import pyaudio
import wave
import threading
import os
import time
from collections import deque
import socket
import re
import numpy as np
import matplotlib.pyplot as plt
import wave

from utils import *

# udp config 
FORMAT = pyaudio.paInt16
CHANNELS = 1             
SAMPLE_RATE = 24000       
BUFFER_SIZE = 1024  
LESS_THRESHOLD = 10.0  # データ損失率閾値     
UDP_IP = "0.0.0.0"  
PORT = 8000 

# mac config
MAC_FORMAT = pyaudio.paInt16
MAC_CHANNELS = 1
MAC_SAMPLE_RATE = 44100 # 調べる
MAC_CHUNK_SIZE = 1024



class AudioDataCollector:
    def __init__(self, root):
        self.root = root
        width, height = 600, 400
        dx, dy = self.centering_window(width, height)
        self.root.geometry(f"{width}x{height}+{dx}+{dy}")

        self.is_collecting_active = False 
        self.is_recording = False
        self.socket = None
        self.receive_thread = None

        # udp
        self.recorded_chunks = []
        self.stream_buffer = deque(maxlen=200) 

        # mac
        self.mac_stream = None
        self.mac_recorded_chunks = []
        self.mac_stream_buffer = deque(maxlen=int(MAC_SAMPLE_RATE / MAC_CHUNK_SIZE * 2))

        self.start_time = 0
        self.actual_duration = 0

        self.start_button = tk.Button(root, text="収集スタート", font=("Helvetica", 14), command=self.start_collection)
        self.start_button.pack(pady=10)
        self.reset_button = tk.Button(root, text="リセット", font=("Helvetica", 14), command=self.reset_app)
        self.reset_button.pack(pady=10)
        self.quit_button = tk.Button(root, text="終了", font=("Helvetica", 14), command=self.quit_app)
        self.quit_button.pack(pady=10)
        
        # ステータス表示
        self.status_label = tk.Label(root, text="「収集スタート」を押してください", font=("Helvetica", 14))
        self.status_label.pack(pady=10)

        self.p = pyaudio.PyAudio()
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def centering_window(self, width, height):
        """ 画面位置調整用 """
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        dx = screen_width // 2 - width // 2
        dy = screen_height // 2 - height // 2
        return dx, dy

    def start_collection(self):
        if self.is_collecting_active:
            return
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024 * 4)
            self.socket.bind((UDP_IP, PORT))
            self.socket.settimeout(1.0)

            self.mac_stream = self.p.open(
                format=MAC_FORMAT,
                channels=MAC_CHANNELS,
                rate=MAC_SAMPLE_RATE,
                input=True,
                frames_per_buffer=MAC_CHUNK_SIZE,
                stream_callback=self.mac_audio_callback
            )
            self.mac_stream.start_stream()
            
            self.is_collecting_active = True
            self.start_button.config(state=tk.DISABLED)
            self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue")
            
            self.root.bind("<Alt_L>", self.on_key_press)
            self.root.bind("<KeyRelease-Alt_L>", self.on_key_release)
            self.root.bind("<Alt_R>", self.on_key_press)
            self.root.bind("<KeyRelease-Alt_R>", self.on_key_release)

            # 受信スレッド開始
            self.receive_thread = threading.Thread(target=self.receive_pcm_data, daemon=True)
            self.receive_thread.start()
            print(f"UDP受信開始: {PORT}")

        except Exception as e:
            self.status_label.config(text=f"起動エラー: {e}", fg="red")
            print(f"Error: {e}")

    def receive_pcm_data(self):
        while self.is_collecting_active:
            try:
                data, _ = self.socket.recvfrom(BUFFER_SIZE * 2)
                self.stream_buffer.append(data)
                if self.is_recording:
                    self.recorded_chunks.append(data)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"受信エラー: {e}")
                break

    def mac_audio_callback(self, in_data, frame_count, time_info, status):
        """ Macマイク入力用コールバック """
        if self.is_collecting_active:
            self.mac_stream_buffer.append(in_data)
            if self.is_recording:
                self.mac_recorded_chunks.append(in_data)
        return (None, pyaudio.paContinue)

    def on_key_press(self, event):
        if not self.is_recording and self.is_collecting_active:
            self.is_recording = True
            self.start_time = time.time()

            pre_roll = list(self.stream_buffer)[-5:] # 直近5パケット
            self.recorded_chunks = pre_roll
            pre_roll_mac = list(self.mac_stream_buffer)[-5:]
            self.mac_recorded_chunks = pre_roll_mac
            
            self.status_label.config(text="収集中...", fg="red")

    def on_key_release(self, event):
        if self.is_recording:
            self.is_recording = False
            self.actual_duration = time.time() - self.start_time
            self.status_label.config(text="保存中...", fg="orange")
            
            self.save_audio_file()
            self.recorded_chunks = []
            self.mac_recorded_chunks = []
            
            # delay後，待機状態
            self.root.after(2000, lambda: self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue"))

    def save_audio_file(self):

        full_data = b''.join(self.recorded_chunks)
        total_bytes = len(full_data)

        bytes_per_sec = SAMPLE_RATE * (16 / 8) * CHANNELS 
        duration = total_bytes / bytes_per_sec if bytes_per_sec > 0 else 0

        full_data_mac = b''.join(self.mac_recorded_chunks)

        # データ損失率の計算 (UDPなのでパケットロスがあり得る)
        loss_rate = 0
        if self.actual_duration > 0:
            loss_rate = max(0, (1 - (duration / self.actual_duration)) * 100)
            loss_rate = max(0.0, loss_rate)

        print(f"--------------------------------------------------")
        print(f"SAW Data Report")
        print(f"  - データ上の時間 : {duration:.3f} 秒")
        print(f"  - 実際の録音時間 : {self.actual_duration:.3f} 秒")
        print(f"  - 損失率     : {loss_rate:.1f} %")
        print(f"--------------------------------------------------")

        if loss_rate > LESS_THRESHOLD:
            self.status_label.config(text=f"保存中止: 損失率が高いです. やり直してください ({loss_rate:.1f}%)", fg="red")
            print(f"保存中止: 損失率が高いです ({loss_rate:.1f}%)")
        
        # Save File
        save_dir = f"../data_collection/data/audio"
        os.makedirs(save_dir, exist_ok=True)

        suffix_pat = re.compile(r".*_(\d+)\.wav$", re.IGNORECASE)
        max_idx = 0
        for entry in os.scandir(save_dir):
            if not entry.is_file():
                continue
            m = suffix_pat.match(entry.name)
            if not m:
                continue
            try:
                max_idx = max(max_idx, int(m.group(1)))
            except ValueError:
                pass
        
        filename_saw = os.path.join(save_dir, f"saw_{max_idx + 1}.wav")
        filename_mac = os.path.join(save_dir, f"mac_{max_idx + 1}.wav")

        try:
            with wave.open(filename_saw, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(FORMAT))
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(full_data)

            with wave.open(filename_mac, 'wb') as wf:
                wf.setnchannels(MAC_CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(MAC_FORMAT))
                wf.setframerate(MAC_SAMPLE_RATE)
                wf.writeframes(full_data_mac)
            
            self.status_label.config(text=f"保存完了: {os.path.basename(filename_saw)}, {os.path.basename(filename_mac)}", fg="green")
            print(f"ファイル保存: saw{filename_saw}, mac{filename_mac}")
        except Exception as e:
            self.status_label.config(text=f"保存エラー: {e}", fg="red")
            print(f"保存失敗: {e}")

    def reset_app(self):
        """状態をリセットして再接続可能にする"""
        self.is_collecting_active = False
        self.is_recording = False
        
        # ソケットを閉じる
        if self.socket:
            self.socket.close()
            self.socket = None
        
        # mac streamを閉じる
        if self.mac_stream:
            if self.mac_stream.is_active():
                self.mac_stream.stop_stream()
            self.mac_stream.close()
            self.mac_stream = None
        
        # スレッド終了待ち
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
            
        self.start_button.config(state=tk.NORMAL)
        self.root.unbind("<Alt_L>")
        self.root.unbind("<KeyRelease-Alt_L>")
        self.root.unbind("<Alt_R>")
        self.root.unbind("<KeyRelease-Alt_R>")
        
        self.label_counts = {}
        self.status_label.config(text="リセット完了: 「収集スタート」を押してください", fg="black")
        print("アプリをリセットしました")

    def quit_app(self):
        self.is_collecting_active = False
        self.is_recording = False
        
        if self.socket:
            self.socket.close()
            
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1.0)
            
        self.p.terminate()
        self.root.destroy()
        print("終了")

def visualize_audio_data(saw_data, mac_data):

    with wave.open(saw_data, 'rb') as wf:
        saw_bytes = wf.readframes(wf.getnframes())
    with wave.open(mac_data, 'rb') as wf:
        mac_bytes = wf.readframes(wf.getnframes())

    if len(saw_bytes) == 0 and len(mac_bytes) == 0:
        print("visualize_audio_data: empty input")
        return

    # int16 PCM -> numpy配列
    saw = np.frombuffer(saw_bytes, dtype=np.int16) if len(saw_bytes) else np.array([], dtype=np.int16)
    mac = np.frombuffer(mac_bytes, dtype=np.int16) if len(mac_bytes) else np.array([], dtype=np.int16)

    # 正規化（表示用）
    def _norm(x: np.ndarray) -> np.ndarray:
        if x.size == 0:
            return x.astype(np.float32)
        return (x.astype(np.float32) / 32768.0)

    saw_f = _norm(saw)
    mac_f = _norm(mac)

    t_saw = np.arange(saw_f.size) / float(SAMPLE_RATE) if saw_f.size else np.array([], dtype=np.float32)
    t_mac = np.arange(mac_f.size) / float(MAC_SAMPLE_RATE) if mac_f.size else np.array([], dtype=np.float32)

    max_t = 0.0
    if t_saw.size:
        max_t = max(max_t, float(t_saw[-1]))
    if t_mac.size:
        max_t = max(max_t, float(t_mac[-1]))

    fig, axes = plt.subplots(
        2, 1, sharex=True, figsize=(7, 4), constrained_layout=True
    )

    # 上段: SAW (UDP)
    ax0 = axes[0]
    if saw_f.size:
        ax0.plot(t_saw, saw_f, linewidth=0.8, color="#1f77b4")
    ax0.set_title("VPU")
    ax0.set_ylabel("Amplitude")
    ax0.grid(True, alpha=0.25)

    # 下段: Mac mic
    ax1 = axes[1]
    if mac_f.size:
        ax1.plot(t_mac, mac_f, linewidth=0.8, color="#9467bd")
    ax1.set_title("Microphone")
    ax1.set_xlabel("Time (s)")
    ax1.set_ylabel("Amplitude")
    ax1.grid(True, alpha=0.25)

    if max_t > 0:
        ax1.set_xlim(0, max_t)

    plt.show()


if __name__ == "__main__":
    # root = tk.Tk()
    # app = AudioDataCollector(root)
    # root.mainloop()

    saw_dir="../data_collection/data/audio/saw_4.wav"
    mac_dir ="../data_collection/data/audio/mac_4.wav"

    visualize_audio_data(saw_dir, mac_dir)

    