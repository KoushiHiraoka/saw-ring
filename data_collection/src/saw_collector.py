import tkinter as tk
from tkinter import messagebox
import pyaudio
import wave
import threading
import os

# --- 音声録音の基本設定 ---
FORMAT = pyaudio.paInt16  # 16ビットPCM
CHANNELS = 1             # モノラル
RATE = 44100             # サンプリングレート
CHUNK = 1024             # 一度に読み込むデータサイズ

class AudioDataCollector:
    def __init__(self, root):
        self.root = root
        self.root.title("音声データ収集")
        # ウィンドウサイズの設定
        width, height = 1000, 600
        dx, dy = self.centering_window(width, height)
        self.root.geometry(f"{width}x{height}+{dx}+{dy}")

        # --- 状態管理用の変数 ---
        self.is_collecting_active = False # 「収集スタート」が押されたか
        self.is_recording = False         # スペースキーが押されているか
        self.audio_frames = []            # 録音データを一時保存するバッファ
        self.label_counts = {}            # ラベルごとのファイル数を記録する辞書

        # --- GUIウィジェットの作成 ---
        # ラベル入力
        tk.Label(root, text="ジェスチャーのラベル:", font=("Helvetica", 12)).pack(pady=(10,0))
        self.label_entry = tk.Entry(root, font=("Helvetica", 12), width=30)
        self.label_entry.pack(pady=5)
        self.label_entry.insert(0, "default_gesture")

        # ボタン
        self.start_button = tk.Button(root, text="収集スタート", font=("Helvetica", 12), command=self.start_collection)
        self.start_button.pack(pady=10)

        self.quit_button = tk.Button(root, text="終了", font=("Helvetica", 12), command=self.quit_app)
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


    def start_collection(self):
        if not self.is_collecting_active:
            # オーディオストリームを開始
            self.stream = self.p.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                      input=True, frames_per_buffer=CHUNK)
            self.is_collecting_active = True
            self.start_button.config(state=tk.DISABLED)
            self.status_label.config(text="待機中: スペースキーを押して録音開始", fg="blue")
            # キーイベントの受付を開始
            self.root.bind("<KeyPress-space>", self.on_key_press)
            self.root.bind("<KeyRelease-space>", self.on_key_release)
            print("収集プロセスを開始しました。")

    def on_key_press(self, event):
        if not self.is_recording:
            self.is_recording = True
            self.audio_frames = [] # バッファをリセット
            self.status_label.config(text="収集中...", fg="red")
            # 録音を別スレッドで実行してGUIが固まるのを防ぐ
            self.recording_thread = threading.Thread(target=self.record_audio)
            self.recording_thread.start()
            print("録音開始！")

    def on_key_release(self, event):
        if self.is_recording:
            self.is_recording = False # 録音スレッドに停止を知らせる
            print("録音停止！")
            self.status_label.config(text="待機中: スペースキーを押して録音開始", fg="blue")
            # ファイル保存は録音スレッドが終了してから行われる

    def record_audio(self):
        while self.is_recording:
            data = self.stream.read(CHUNK)
            self.audio_frames.append(data)
        # 録音が終了したら、メインスレッドでファイル保存を呼び出す
        self.root.after(0, self.save_audio_file)

    def save_audio_file(self):
        label = self.label_entry.get().strip()
        if not label:
            label = "unknown"
            
        # ラベルのカウンターを更新
        count = self.label_counts.get(label, 0) + 1
        self.label_counts[label] = count
        
        filename = f"{label}_{count}.wav"
        
        # WAVファイルとして保存
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self.p.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b''.join(self.audio_frames))
        
        self.status_label.config(text=f"保存完了: {filename}", fg="green")
        print(f"ファイル {filename} を保存しました。")

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
