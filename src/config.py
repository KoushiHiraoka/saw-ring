import numpy as np

# UDP settings
UDP_IP = "0.0.0.0"
UDP_PORT = 8000
SOCKET_BUF_SIZE = 65536

# SAW settings
SAMPLE_RATE = 24000
BUFFER_SIZE = 1024       # 1回の受信パケットサイズ
DTYPE = np.int16         # 受信データの型
NORM_FACTOR = 32768.0    # 正規化係数

# Visualize settings
WAVE_WINDOW_SIZE = 48000
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 80              # 縦軸の解像度
SPECTRO_WIDTH = 200      # 横軸の時間ステップ数
FFT_SIZE = 1024          # FFTのウィンドウサイズ
MAX_FREQ_DISP = SAMPLE_RATE / 2     # 表示する最大周波数(Hz)

# Inference settings
MODEL_PATH = "./surface_recognition/resnet_best_model.pth" # pthファイルパス
NUM_CLASSES = 9                                 # クラス数
CLASS_LABELS = ["ダンボール", "布", "ガラス", "None", "紙", "プラスチック", "皮膚", "ステンレス", "木"]  # クラス名
INFERENCE_INTERVAL = 0.5