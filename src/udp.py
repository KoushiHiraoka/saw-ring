import socket
import threading
import queue
import numpy as np
from config import *

class UDPListener:
    def __init__(self):
        self.data_queue = queue.Queue()
        self.running = False
        self.thread = None
        self.sock = None

    def start(self):
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind((UDP_IP, UDP_PORT))
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUF_SIZE)
        
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print(f"UDP Listener started on port {UDP_PORT}")

    def _listen_loop(self):
        while self.running:
            try:
                # 少し多めにバッファを取って読み出し
                data, _ = self.sock.recvfrom(BUFFER_SIZE * 4)
                if not data:
                    continue

                # バイナリ変換と正規化
                pcm_data = np.frombuffer(data, dtype=DTYPE)
                if pcm_data.size > 0:
                    normalized = pcm_data.astype(np.float32) / NORM_FACTOR
                    self.data_queue.put(normalized)

            except Exception as e:
                print(f"Receive Error: {e}")

    def get_data(self):
        """キューに溜まったデータを全て取り出して結合して返す"""
        data_list = []
        try:
            while True:
                data_list.append(self.data_queue.get_nowait())
        except queue.Empty:
            pass
        
        if not data_list:
            return None
        return np.concatenate(data_list)

    def stop(self):
        self.running = False
        if self.sock:
            self.sock.close()