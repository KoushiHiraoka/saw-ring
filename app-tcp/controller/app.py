import numpy as np
import torch
import torch.nn as nn
import pyautogui
import time
from collections import deque
from utils import *
import socket
import threading
from queue import Queue
import torch.nn.functional as F
import os
import sys
import queue

# TCP設定
ESP_IP = "saw-ring.local" 
PORT = 8000
BUFFER_SIZE = 1024 * 2
DTYPE = np.int16

#　推論設定
MODEL_PATH = "cnn_weights.pth" 
SR = 24000
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 128
FIXED_WIDTH = 188
SAMPLE_SIZE_FOR_INFERENCE = int(SR * 2)
INFERENCE_INTERVAL = 0.35  # 350msごとに推論
CONFIDENCE_THRESHOLD = 0.85
COOLDOWN_TIME = 1.5




KEY_MAPPING = {
    LABELS[4]: 'k',       # Tap -> 再生/一時停止
    LABELS[3]: 'l',       # Swipe -> 10秒スキップ
    LABELS[0]: 'j',       # DoubleTap -> 10秒戻る
    LABELS[1]: 'f'        # NailTap -> フルスクリーン
}

class TCPListener(threading.Thread):
    def __init__(self, data_queue):
        super().__init__()
        self.data_queue = data_queue
        self._is_running = True
        self.client = None

    def run(self):
        """TCP接続とデータ受信ループ"""
        buffer = b''
        try:
            print(f"[TCP] 接続中... {ESP_IP}:{PORT}")
            self.client = socket.create_connection((ESP_IP, PORT), timeout=5)
            self.client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            print("[TCP] 接続成功。データ受信開始。")
        except Exception as e:
            print(f"[ERROR] 接続失敗: {e}")
            return

        while self._is_running:
            try:
                raw_data = self.client.recv(BUFFER_SIZE)
                if not raw_data:
                    print("[TCP] 接続が切断されました。")
                    break
                
                buffer += raw_data
                
                # BUFFER_SIZEごとに切り出して処理（ユーザーコードのロジックを流用）
                while len(buffer) >= BUFFER_SIZE:
                    data_to_process = buffer[:BUFFER_SIZE]
                    buffer = buffer[BUFFER_SIZE:]
                    
                    pcm_data = np.frombuffer(data_to_process, dtype=DTYPE)
                    
                    if pcm_data.size > 0:
                        # -1.0 ~ 1.0 に正規化し、Queueに格納
                        normalized_data = pcm_data / 32768.0
                        self.data_queue.put(normalized_data)

            except socket.timeout:
                continue
            except Exception as e:
                if self._is_running:
                     print(f"[ERROR] 受信エラー: {e}")
                break
            
        if self.client:
            self.client.close()
        print("[TCP] データ受信スレッドを終了しました。")

    def stop(self):
        self._is_running = False
        if self.client:
            # 接続を切断してrecvを強制終了
            try:
                self.client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

def main_inference_engine():
    # --- 初期設定 ---
    data_queue = queue.Queue()
    
    # モデルロード
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[ML] Using device: {device}")
    
    # 最後のFC層の入力チャンネル数は64を想定
    model = SimpleCNN(num_classes=len(LABELS)).to(device) 
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    model.eval()

    # リングバッファ（2.5秒分の音声サンプルを溜める）
    global_buffer = deque(np.zeros(SAMPLE_SIZE_FOR_INFERENCE, dtype=np.float32), maxlen=SAMPLE_SIZE_FOR_INFERENCE)
    
    # リスナースレッド起動
    listener = TCPListener(data_queue)
    listener.start()
    
    last_inference_time = 0
    last_action_time = 0

    print(f"\n=== Real-time Inference Engine Started (Interval: {INFERENCE_INTERVAL}s) ===")
    print("Listening for gestures...")
    
    try:
        while True:
            # Queueから新しいデータをすべて取り出し、グローバルバッファに追加
            while not data_queue.empty():
                new_chunk = data_queue.get()
                global_buffer.extend(new_chunk)

            current_time = time.time()
            
            # --- 判定サイクルチェック ---
            if current_time - last_inference_time < INFERENCE_INTERVAL:
                time.sleep(0.01)
                continue

            last_inference_time = current_time

            # --- クールダウンチェック ---
            if current_time - last_action_time < COOLDOWN_TIME:
                print(f"[INFO] Cooldown... Remaining: {COOLDOWN_TIME - (current_time - last_action_time):.1f}s", end='\r')
                continue

            # --- 推論実行 ---
            
            # 1. バッファ全体を抽出（2.5秒）
            y_samples = np.array(global_buffer)
            input_tensor = extract_pcen(y_samples).to(device)
            
            # 2. 推論
            with torch.no_grad():
                outputs = model(input_tensor)
                probs = F.softmax(outputs, dim=1).squeeze().cpu().numpy()
                
            label_idx = np.argmax(probs)
            confidence = probs[label_idx]
            label_name = LABELS[label_idx]

            # 3. アクション判定と実行
            if confidence > CONFIDENCE_THRESHOLD and label_name != LABELS[0]:
                key = KEY_MAPPING.get(label_name)
                
                if key:
                    pyautogui.press(key)
                    last_action_time = current_time
                    print(f"\n[ACTION] {label_name} ({confidence:.2f}) -> Key: '{key}'")
            else:
                # ノイズ判定をリアルタイムで表示 (上書き)
                print(f"[INFO] Current: {label_name} ({confidence:.2f})", end='\r')
                
    except KeyboardInterrupt:
        print("\n[SYSTEM] ユーザーによって停止されました。")
    finally:
        listener.stop()
        listener.join()

if __name__ == '__main__':
    # モデルの重みファイルが存在するか確認
    if not os.path.exists(MODEL_PATH):
        print(f"[FATAL] モデルファイルが見つかりません: {MODEL_PATH}")
        sys.exit(1)
        
    import os # ここでosをインポート (pyqtの後に書くと上書きされないため)
    main_inference_engine()


# class GestureController:
#     def __init__(self, model_path):
#         self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
#         print(f"Loading model from {model_path}...")
        
#         # モデルロード
#         self.model = SimpleCNN(num_classes=len(LABELS)).to(self.device)
#         self.model.load_state_dict(torch.load(model_path, map_location=self.device))
#         self.model.eval()
        
#         # リングバッファ
#         buffer_len = int(SR * 2.5) 
#         self.audio_buffer = deque(maxlen=buffer_len)
#         self.audio_buffer.extend(np.zeros(buffer_len))
        
#         self.last_action_time = 0

#     def callback(self, indata, frames, time_info, status):
#         # マイクからの入力をバッファに追加
#         # indataは (frames, channels) なので channel 0 を取る
#         self.audio_buffer.extend(indata[:, 0])

#     def run(self):
#         print("\n=== Real-time Gesture Control Started ===")

#         # マイク入力ストリーム開始
#         with sd.InputStream(callback=self.callback, channels=1, samplerate=SR):
#             while True:
#                 time.sleep(INFERENCE_INTERVAL)
                
#                 # クールダウン中ならスキップ
#                 if time.time() - self.last_action_time < COOLDOWN_TIME:
#                     continue

#                 # 推論実行
#                 input_tensor = extract_pcen(list(self.audio_buffer)).to(self.device)
                
#                 with torch.no_grad():
#                     outputs = self.model(input_tensor)
#                     probs = torch.nn.functional.softmax(outputs, dim=1)
#                     conf, predicted = torch.max(probs, 1)
                    
#                 label_idx = predicted.item()
#                 confidence = conf.item()
#                 label_name = LABELS[label_idx]

#                 # ログ表示 (デバッグ用: ノイズ以外を表示)
#                 if label_name != 'Noise' and confidence > 0.5:
#                     print(f"Detected: {label_name} ({confidence:.2f})")

#                 # アクション判定
#                 if confidence > CONFIDENCE_THRESHOLD:
#                     if label_name == 'Noise':
#                         continue # ノイズなら無視
                        
#                     # アクション実行
#                     key = KEY_MAPPING.get(label_name)
#                     if key:
#                         print(f" >>> ACTION: {label_name} -> Pressing '{key}'")
#                         pyautogui.press(key)
#                         self.last_action_time = time.time()

