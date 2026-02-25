import tkinter as tk
import pyaudio
import wave
import threading
import os
import socket
import time
from collections import deque

# config
FORMAT = pyaudio.paInt16
CHANNELS = 1             
SAMPLE_RATE = 24000       
BUFFER_SIZE = 1024        
# UDP config
# デバイスごとのポート番号 (arduino/udp/udp.ino の udpPort と合わせる):
#   saw-ring-1: 8000
#   saw-ring-2: 8800
#   saw-ring-3: 8880
#   saw-ring-4: 8888
UDP_IP = "0.0.0.0"
PORT = 8880

class AudioDataCollector:
    def __init__(self, root):
        self.root = root
        self.root.title("SAWデータ収集アプリ (UDP)")
        # ウィンドウサイズの設定
        width, height = 1000, 600
        dx, dy = self.centering_window(width, height)
        self.root.geometry(f"{width}x{height}+{dx}+{dy}")

        # --- 状態管理用の変数 ---
        self.is_collecting_active = False # 「収集スタート」が押されたか
        self.is_recording = False         # Optionキーが押されているか
        self.socket = None
        self.receive_thread = None

        self.recorded_chunks = []
        self.stream_buffer = deque(maxlen=200)
        self.label_counts = {}            # ラベルごとのファイル数を記録する辞書
        self.start_time = 0               # 録音開始時刻
        self.actual_duration = 0          # 実際の録音時間

        # --- GUIウィジェットの作成 ---
        self.texture_entry = self.entry_pair(root, "Texture", pady=(50, 10), insert="test_tex")
        self.label_entry = self.entry_pair(root, "Gesture", pady=(0, 10), insert="swipe")
        self.person_entry = self.entry_pair(root, "Person", pady=(0, 10), insert="person_1")
        self.index_entry = self.entry_pair(root, "Index", pady=(0, 10), insert="1")

        # ボタン
        self.start_button = tk.Button(root, text="収集スタート", font=("Helvetica", 14), command=self.start_collection)
        self.start_button.pack(pady=20)

        self.reset_button = tk.Button(root, text="リセット", font=("Helvetica", 14), command=self.reset_app)
        self.reset_button.pack(pady=5)

        self.quit_button = tk.Button(root, text="終了", font=("Helvetica", 14), command=self.quit_app)
        self.quit_button.pack(pady=5)
        
        # ステータス表示
        self.status_label = tk.Label(root, text="「収集スタート」を押してください", font=("Helvetica", 14))
        self.status_label.pack(pady=20)

        # --- PyAudioの初期化 ---
        self.p = pyaudio.PyAudio()
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)

    def centering_window(self, width, height):
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        dx = screen_width // 2 - width // 2
        dy = screen_height // 2 - height // 2
        return dx, dy
    
    def entry_pair(self, parent, label_text, entry_width=30, font=("Helvetica", 18), pady=(10, 0), insert=""):
        frame = tk.Frame(parent)
        frame.pack(pady=pady)
        label = tk.Label(frame, text=label_text, font=font)
        label.pack(side=tk.LEFT)
        entry = tk.Entry(frame, font=font, width=entry_width)
        if insert:
            entry.insert(0, insert)
        entry.pack(side=tk.LEFT, padx=10)
        return entry 

    def start_collection(self):
        if self.is_collecting_active:
            return
        
        try:
            # UDPソケットの作成とバインド
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024 * 4)
            self.socket.bind((UDP_IP, PORT))
            self.socket.settimeout(1.0) # タイムアウト設定（終了判定用）
            
            self.is_collecting_active = True
            self.start_button.config(state=tk.DISABLED)
            self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue")
            
            # キーバインド
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
        """常にデータを受信し続け、録音フラグがTrueの時だけバッファに溜める"""
        print("受信ループ開始")
        while self.is_collecting_active:
            try:
                data, addr = self.socket.recvfrom(BUFFER_SIZE * 2)
                self.stream_buffer.append(data)
                if self.is_recording:
                    self.recorded_chunks.append(data)
            except socket.timeout:
                continue # タイムアウトは無視してループ継続
            except Exception as e:
                print(f"受信エラー: {e}")
                break
        print("受信ループ終了")

    def on_key_press(self, event):
        if not self.is_recording and self.is_collecting_active:
            self.is_recording = True
            self.start_time = time.time()
            pre_roll = list(self.stream_buffer)[-5:] # 直近5パケット程度
            self.recorded_chunks = pre_roll
            self.status_label.config(text="収集中...", fg="red")
            # print("録音開始")

    def on_key_release(self, event):
        if self.is_recording:
            self.is_recording = False
            self.actual_duration = time.time() - self.start_time
            # print("録音停止")
            self.status_label.config(text="保存中...", fg="orange")
            
            # 保存処理へ
            self.save_audio_file()
            
            # 少し待ってからステータスを戻す
            self.root.after(800, lambda: self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue"))

    def save_audio_file(self):
        LESS_THRESHOLD = 10.0

        label = self.label_entry.get().strip() or "test"
        person = self.person_entry.get().strip() 
        texture = self.texture_entry.get().strip() or "test"

        try:
            initial_count = int(self.index_entry.get().strip()) - 1
        except ValueError:
            initial_count = 0

        current_count = self.label_counts.get(label, initial_count) + 1
        full_data = b''.join(self.recorded_chunks)

        total_bytes = len(full_data)
        bytes_per_sec = SAMPLE_RATE * (16 / 8) * CHANNELS 
        duration = total_bytes / bytes_per_sec if bytes_per_sec > 0 else 0

        # データ損失率の計算 (UDPなのでパケットロスがあり得る)
        loss_rate = 0
        if self.actual_duration > 0:
            loss_rate = max(0, (1 - (duration / self.actual_duration)) * 100)
            loss_rate = max(0.0, loss_rate)

        print(f"--------------------------------------------------")
        print(f"SAW-Ring Report")
        print(f"  - データ上の時間 : {duration:.3f} 秒")
        print(f"  - 実際の録音時間 : {self.actual_duration:.3f} 秒")
        print(f"  - 損失率     : {loss_rate:.1f} %")
        print(f"--------------------------------------------------")

        if loss_rate > LESS_THRESHOLD:
            self.status_label.config(text=f"保存中止: 損失率が高いです. やり直してください ({loss_rate:.1f}%)", fg="red")
            print(f"保存中止: 損失率が高いです ({loss_rate:.1f}%)")
            return
        else:
            self.label_counts[label] = current_count
            
        # ディレクトリ構成: data/texture/person_X/label_N.wav
        if not person:
            save_dir = f"../data/experiment/{texture}"
        else:
            save_dir = f"../data/experiment/{texture}/person_{person}"
        os.makedirs(save_dir, exist_ok=True)
        
        filename = os.path.join(save_dir, f"{label}_{current_count}.wav")

        
        try:
            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(CHANNELS)
                wf.setsampwidth(self.p.get_sample_size(FORMAT))
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(full_data)
            
            self.status_label.config(text=f"保存完了: {os.path.basename(filename)}", fg="green")
            print(f"ファイル保存: {filename}")
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

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioDataCollector(root)
    root.mainloop()