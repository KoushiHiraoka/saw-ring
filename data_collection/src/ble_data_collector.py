import tkinter as tk
from tkinter import messagebox
import pyaudio
import wave
import threading
import os
import socket
import time
import asyncio
from bleak import BleakScanner, BleakClient

# --- 音声録音の基本設定 ---
FORMAT = pyaudio.paInt16  # 16ビットPCM
CHANNELS = 1              # モノラル
SAMPLE_RATE = 16000       # サンプリングレート
BUFFER_SIZE = 1024        # 一度に読み込むデータサイズ

# --- BLE設定 ---
DEVICE_NAME = "SAW-Ring"
CHARACTERISTIC_UUID = "13b73498-101b-4f22-aa2b-a72c6710e54f"

class AudioDataCollector:
    def __init__(self, root):
        self.root = root
        self.root.title("SAWデータ収集アプリ (BLE版)")
        
        # ウィンドウサイズの設定
        width, height = 1000, 600
        dx, dy = self.centering_window(width, height)
        self.root.geometry(f"{width}x{height}+{dx}+{dy}")

        # --- 状態管理用の変数 ---
        self.is_collecting_active = False # 「収集スタート」が押されたか（BLE接続試行開始）
        self.is_ble_connected = False     # BLE接続が完了しているか
        self.is_recording = False         # Optionキーが押されているか
        self.audio_buffer = bytearray()   # 録音データを一時保存するバッファ
        self.label_counts = {}            # ラベルごとのファイル数を記録する辞書

        # --- GUIウィジェットの作成 ---
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
        self.status_label = tk.Label(root, text="「収集スタート」を押してBLE接続してください", font=("Helvetica", 14))
        self.status_label.pack(pady=20)

        # --- PyAudioの初期化（ファイル保存時のパラメータ取得用） ---
        self.p = pyaudio.PyAudio()
        
        # --- BLEループ制御用 ---
        self.loop = asyncio.new_event_loop()
        self.ble_thread = None
        self.stop_event = asyncio.Event()

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
        if not insert == '':
            entry.insert(0, insert)
        entry.pack(side=tk.LEFT, padx=10)
        return entry 

    # --- BLE関連のロジック ---

    def start_collection(self):
        """BLE接続スレッドを開始する"""
        if not self.is_collecting_active:
            self.is_collecting_active = True
            self.start_button.config(state=tk.DISABLED)
            self.status_label.config(text="BLEデバイスを検索中...", fg="orange")
            
            # BLE通信を別スレッドで開始
            self.ble_thread = threading.Thread(target=self.run_ble_loop, daemon=True)
            self.ble_thread.start()

            # キーバインド設定
            self.root.bind("<Alt_L>", self.on_key_press) # 左Optionキーで録音開始
            self.root.bind("<KeyRelease-Alt_L>", self.on_key_release) # 停止
            self.root.bind("<Alt_R>", self.on_key_press) # 右Optionキーで録音開始
            self.root.bind("<KeyRelease-Alt_R>", self.on_key_release) # 停止

    def run_ble_loop(self):
        """非同期ループをスレッド内で回す"""
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.ble_main())

    async def ble_main(self):
        """BLEのメイン処理（検索・接続・Notify待機）"""
        print("BLEスキャン開始...")
        devices = await BleakScanner.discover(timeout=5.0)
        device = None
        for d in devices:
            if d.name == DEVICE_NAME:
                device = d
                break
        
        if device is None:
            print(f"{DEVICE_NAME} が見つかりませんでした。")
            # (以下変更なし...)

        print(f"接続中: {device.name}")
        self.root.after(0, lambda: self.status_label.config(text=f"接続中: {device.name}...", fg="orange"))

        disconnected_event = asyncio.Event()

        def disconnect_callback(client):
            print("BLE切断されました")
            disconnected_event.set()
            self.is_ble_connected = False
            self.root.after(0, lambda: self.status_label.config(text="BLE切断: 再接続待ち...", fg="red"))

        try:
            async with BleakClient(device, disconnected_callback=disconnect_callback) as client:
                print(f"接続完了: {client.is_connected}")
                self.is_ble_connected = True
                self.root.after(0, lambda: self.status_label.config(text="接続完了: Optionキーで録音", fg="blue"))

                # Notify開始
                await client.start_notify(CHARACTERISTIC_UUID, self.notification_handler)

                # アプリ終了シグナルか、切断があるまで待機
                while not self.stop_event.is_set() and client.is_connected:
                    await asyncio.sleep(0.1)

                # 終了処理
                if client.is_connected:
                    await client.stop_notify(CHARACTERISTIC_UUID)
        except Exception as e:
            print(f"BLE Error: {e}")
            self.root.after(0, lambda: self.status_label.config(text=f"エラー: {e}", fg="red"))
            self.is_collecting_active = False

    def notification_handler(self, sender, data):
        """BLEからのデータ受信コールバック（常時呼ばれる）"""
        # 録音中フラグが立っている時だけバッファに追加
        if self.is_recording:
            self.audio_buffer.extend(data)

    # --- キーイベント処理 ---

    def on_key_press(self, event):
        # BLE未接続なら何もしない
        if not self.is_ble_connected:
            return

        if not self.is_recording:
            self.is_recording = True
            self.audio_buffer = bytearray() # バッファをリセット
            self.start_time = time.time()
            self.status_label.config(text="収集中... (BLE Receiving)", fg="red")
            print("録音開始 (Buffer Clear)")

    def on_key_release(self, event):
        # BLE未接続なら何もしない
        if not self.is_ble_connected:
            return

        if self.is_recording:
            self.is_recording = False
            self.stop_time = time.time()
            self.actual_duration = self.stop_time - self.start_time
            print(f"録音停止。受信サイズ: {len(self.audio_buffer)} bytes")
            
            self.status_label.config(text="待機中: Optionキーを押して録音開始", fg="blue")
            
            # ファイル保存
            self.save_audio_file()

    def save_audio_file(self):
        label = self.label_entry.get().strip()
        person = self.person_entry.get().strip()
        texture = self.texture_entry.get().strip()
        if not label:
            label = "unknown"
        
        # Index管理
        try:
            initial_count = int(self.index_entry.get().strip()) - 1
        except ValueError:
            initial_count = 0

        count = self.label_counts.get(label, initial_count) + 1
        self.label_counts[label] = count
        
        # 保存先パス作成
        if not person:
            save_dir = f"../data/experiment/{texture}"
        else:
            save_dir = f"../data/experiment/{texture}/{person}"
        os.makedirs(save_dir, exist_ok=True)
        
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
        
        # WAV保存
        if len(self.audio_buffer) > 0:
            try:
                with wave.open(filename, 'wb') as wf:
                    wf.setnchannels(CHANNELS)
                    # PyAudioからサンプルサイズ(バイト数)を取得
                    wf.setsampwidth(self.p.get_sample_size(FORMAT))
                    wf.setframerate(SAMPLE_RATE)
                    wf.writeframes(self.audio_buffer)
                
                self.status_label.config(text=f"保存完了: {filename} ({len(self.audio_buffer)} bytes)", fg="green")
                print(f"ファイル {filename} を保存しました。")
            except Exception as e:
                print(f"保存エラー: {e}")
                self.status_label.config(text="保存エラー", fg="red")
        else:
            print("データが空のため保存しませんでした。")
            self.status_label.config(text="データなし (Skip)", fg="orange")

    def reset_app(self):
        # (既存のリセットロジックを維持しつつ、BLEは再接続しないように制御)
        self.previous_texture = self.texture_entry.get()
        if not self.previous_texture: self.previous_texture = "skin"
        self.previous_label = self.label_entry.get()
        if not self.previous_label: self.previous_label = "swipe"

        # Entryクリア
        self.texture_entry.delete(0, tk.END)
        self.texture_entry.insert(0, self.previous_texture)
        self.label_entry.delete(0, tk.END)
        self.label_entry.insert(0, self.previous_label)
        
        # カウンター等はリセットするが、BLE接続は維持する設計
        self.label_counts = {}
        self.status_label.config(text="リセット完了 (接続は維持されています)", fg="black")
        print("アプリがリセットされました（内部変数はクリア）。")

    def quit_app(self):
        # 非同期ループを停止させる
        self.stop_event.set()
        
        # PyAudio終了
        self.p.terminate()
        
        self.root.destroy()
        print("アプリケーションを終了します。")

if __name__ == "__main__":
    root = tk.Tk()
    app = AudioDataCollector(root)
    root.mainloop()