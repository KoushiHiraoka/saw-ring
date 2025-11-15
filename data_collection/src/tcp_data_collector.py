import tkinter as tk
from tkinter import messagebox
import pyaudio
import wave
import threading
import os
import socket
import time
import numpy as np

# --- 音声録音の基本設定 ---
FORMAT = pyaudio.paInt16  # 16ビットPCM
CHANNELS = 1              # モノラル
SAMPLE_RATE = 24000       # サンプリングレート
BUFFER_SIZE = 1024        # 一度に読み込むデータサイズ

# --- UDP設定 ---
ESP_IP = "saw-ring.local"  # ESP32のIPアドレス
PORT = 8000         # ポート番号
DTYPE = np.int16
NUM_SAMPLES = BUFFER_SIZE // np.dtype(DTYPE).itemsize
num_samples = BUFFER_SIZE // np.dtype(DTYPE).itemsize
unpack_format = f'<{num_samples}h'


class AudioDataCollector:
    def __init__(self, root):
        self.root = root
        self.root.title("SAWデータ収集アプリ")
        # ウィンドウサイズの設定
        width, height = 1000, 600
        dx, dy = self.centering_window(width, height)
        self.root.geometry(f"{width}x{height}+{dx}+{dy}")

        # --- 状態管理用の変数 ---
        self.is_collecting_active = False # 「収集スタート」が押されたか
        self.is_recording = False         # Optionキーが押されているか
        self.audio_frames = []            # 録音データを一時保存するバッファ
        self.label_counts = {}            # ラベルごとのファイル数を記録する辞書

        # --- GUIウィジェットの作成 ---
        # ラベル入力
        self.texture_entry = self.entry_pair(root, "Texture", pady=(100, 10), insert="")
        self.label_entry = self.entry_pair(root, "Gesture", pady=(0, 10), insert="")
        self.person_entry = self.entry_pair(root, "Person", pady=(0, 10), insert="")
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
        self.stream = None
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app) # ウィンドウのxボタンで終了

    def centering_window(self, width, height):
        # ウィンドウを画面の中央に配置
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        dx = screen_width // 2 - width // 2
        dy = screen_height // 2 - height // 2
        
        return dx, dy
    
    def entry_pair(self, parent, label_text, entry_width=30, font=("Helvetica", 18), pady=(10, 0), insert=""):
        frame = tk.Frame(parent)
        frame.pack(pady=pady)

        # ラベルが右側
        label = tk.Label(frame, text=label_text, font=font)
        label.pack(side=tk.LEFT)

        # エントリが左側
        entry = tk.Entry(frame, font=font, width=entry_width)
        if not insert == '':
            entry.insert(0, insert)
        entry.pack(side=tk.LEFT, padx=10)

        return entry 

    def start_collection(self):
        if self.is_collecting_active:
            return
        
        self.start_button.config(state=tk.DISABLED)
        self.status_label.config(text=f"{ESP_IP} に接続中...", fg="orange")

        connect_thread = threading.Thread(target=self._connect_tcp, daemon=True)
        connect_thread.start()


            # # オーディオストリームを開始
            # self.stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=SAMPLE_RATE,
            #                           input=True, frames_per_buffer=BUFFER_SIZE)
            # self.is_collecting_active = True
            # self.start_button.config(state=tk.DISABLED)
            # self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue")
            # # キーイベントの受付を開始
            # self.root.bind("<Alt_L>", self.on_key_press)  # 左Optionキーで録音開始
            # self.root.bind("<KeyRelease-Alt_L>", self.on_key_release)  # 左Optionキーで録音停止
            # self.root.bind("<Alt_R>", self.on_key_press)  # 右Optionキーで録音開始
            # self.root.bind("<KeyRelease-Alt_R>", self.on_key_release)  # 右Optionキーで録音停止
            # print("収集プロセスを開始しました。")

    def _connect_tcp(self):
        """TCP接続を実行するスレッド関数"""
        try:
            self.client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client.connect((ESP_IP, PORT))
            self.client.settimeout(3.0) # タイムアウト設定
            print(f"Connected to {ESP_IP}:{PORT}")

            # 接続成功時のUI更新 (メインスレッドで実行)
            self.root.after(0, self._on_connection_success)
            
        except Exception as e:
            print(f"接続エラー: {e}")
            self.root.after(0, self.start_button.config, {"state": tk.NORMAL})
            self.root.after(0, self.status_label.config, {"text": f"接続失敗: {e}", "fg": "red"})

    def _on_connection_success(self):
        """接続成功時にUIを更新し、キーバインドを有効化"""
        self.is_collecting_active = True
        self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue")
        # キーイベントの受付を開始
        self.root.bind("<Alt_L>", self.on_key_press)
        self.root.bind("<KeyRelease-Alt_L>", self.on_key_release)
        self.root.bind("<Alt_R>", self.on_key_press)
        self.root.bind("<KeyRelease-Alt_R>", self.on_key_release)
        print("収集プロセスを開始しました。")

    def receive_pcm_data(self):
        self.buffer = b'' # 受信バッファをクリア

        while self.is_recording:
            try:
                # TCPデータを受信
                raw_data = self.client.recv(BUFFER_SIZE)
                if not raw_data:
                    # 接続が正常に閉じられた
                    print("TCP接続が閉じられました。")
                    self.is_recording = False
                    self.root.after(0, self.status_label.config, {"text": "接続が閉じられました。", "fg": "red"})
                    break
                
                # バッファにデータを追加
                self.buffer += raw_data
                
            except socket.timeout:
                print("ソケットタイムアウト")
                continue # タイムアウトは無視してループを続ける
            except Exception as e:
                if self.is_recording: # ユーザーが停止した場合以外のエラー
                    print(f"受信エラー: {e}")
                    self.root.after(0, self.status_label.config, {"text": "接続エラー発生。", "fg": "red"})
                break
        print("受信スレッド終了。")

    def reconnect(self):
        global client
        while self.is_recording:
            try:
                print("再接続を試みています...")
                self.status_label.config(text="通信が切断されました。再接続中・・・", fg="red")
                client.close()  # 古いソケットを閉じる
                client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                time.sleep(1)  # 再接続前に少し待機
                client.connect((ESP_IP, PORT))  # 再接続
                print(f"再接続成功: {ESP_IP}:{PORT}")
                self.status_label.config(text="再接続成功", fg="green")
                break
            except Exception as e:
                print(f"再接続失敗: {e}")
                time.sleep(2)  # 再接続失敗時に待機

    def on_key_press(self, event):
        if not self.is_recording:
            self.is_recording = True
            self.buffer = b''  # UDPバッファをリセット
            self.status_label.config(text="収集中...", fg="red")

            self.start_time = time.time() 

            # UDPデータ受信スレッドを開始
            self.recording_thread = threading.Thread(target=self.receive_pcm_data)
            self.recording_thread.start()
            print("録音開始！")

    def on_key_release(self, event):
        if self.is_recording:
            self.is_recording = False # 録音スレッドに停止を知らせる
            print("録音停止！")
            self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue")

            self.actual_duration = time.time() - self.start_time

            # スレッドの終了を待機
            if self.recording_thread.is_alive():
                self.recording_thread.join()

            # ファイル保存
            self.save_audio_file()

            time.sleep(0.5)

    # def record_audio(self):
    #     while self.is_recording:
    #         data = self.stream.read(BUFFER_SIZE)
    #         self.audio_frames.append(data)
    #     # 録音が終了したら、メインスレッドでファイル保存を呼び出す
    #     self.root.after(0, self.save_audio_file)

    def save_audio_file(self):
        label = self.label_entry.get().strip()
        person = self.person_entry.get().strip()
        texture = self.texture_entry.get().strip()
        if not label:
            label = "unknown"
            print("ラベルが入力されていません")
        initial_count = int(self.index_entry.get().strip()) - 1
        # ラベルのカウンターを更新
        count = self.label_counts.get(label, initial_count) + 1
        self.label_counts[label] = count
        
        # 保存先ディレクトリを指定
        if not person:
            save_dir = f"../data/{texture}"
        else:
            save_dir = f"../data/{texture}/{person}"
        os.makedirs(save_dir, exist_ok=True)  # ディレクトリが存在しない場合は作成
        
        filename = os.path.join(save_dir, f"{label}_{count}.wav")

        total_bytes = len(self.audio_buffer)

        # 1秒あたりのバイト数 = サンプリングレート * (ビット数/8) * チャンネル数
        bytes_per_sec = SAMPLE_RATE * (16 / 8) * CHANNELS 
        duration = total_bytes / bytes_per_sec

        # パケットロス率の計算: (実時間 - データ時間) / 実時間
        if self.actual_duration > 0:
            loss_rate = (1 - (duration / self.actual_duration)) * 100
        else:
            loss_rate = 0

        print(f"--------------------------------------------------")
        print(f"【保存データ診断】")
        print(f"  - 受信データ総量 : {total_bytes} bytes")
        print(f"  - 1秒に必要な量  : {int(bytes_per_sec)} bytes")
        print(f"  - 録音時間 : {duration:.3f} 秒")
        print(f"  - 実際の録音時間       : {self.actual_duration:.3f} 秒")
        print(f"  - データ損失率(Loss)   : {loss_rate:.1f} %")
        print(f"--------------------------------------------------")
        
        # WAVファイルとして保存
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(self.buffer)
        
        if label == "unknown":
            self.status_label.config(text=f"ラベルが設定されていません", fg="red")
        else:
            self.status_label.config(text=f"保存完了: {filename}", fg="green")
        
        print(f"ファイル {filename} を保存しました。")

    def reset_app(self):
        self.previous_texture = self.texture_entry.get()
        if not self.previous_texture:
            self.previous_texture = "skin"
        self.previous_label = self.label_entry.get()
        if not self.previous_label:
            self.previous_label = "swipe"
        self.previous_person = self.person_entry.get()
        if not self.previous_person:
            self.previous_person = "person_0"

    
        # 入力フィールドをクリア
        self.texture_entry.delete(0, tk.END)
        self.texture_entry.insert(0, self.previous_texture)
        self.label_entry.delete(0, tk.END)
        self.label_entry.insert(0, self.previous_label)
        self.person_entry.delete(0, tk.END)
        self.person_entry.insert(0, "person_0")

        # 状態をリセット
        self.is_collecting_active = False
        self.is_recording = False
        self.audio_frames = []
        self.label_counts = {}

        # ステータスラベルを初期状態に戻す
        self.status_label.config(text="「収集スタート」を押してください", fg="black")

        # ボタンの状態をリセット
        self.start_button.config(state=tk.NORMAL)

        print("アプリがリセットされました。")


    def quit_app(self):
        if self.is_recording:
            self.is_recording = False # 念のため録音を停止
        
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.p.terminate()
        self.root.destroy()
        print("アプリケーションを終了しました。")

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioDataCollector(root)
    root.mainloop()