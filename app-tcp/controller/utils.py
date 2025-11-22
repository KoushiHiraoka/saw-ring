import librosa
import numpy as np
import torch
import torch.nn as nn

class SimpleCNN(nn.Module):
    def __init__(self, num_classes):
        super(SimpleCNN, self).__init__()
        
        # Input: (Batch, 1, 64, Time)
        # Layer 1
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels=1, out_channels=16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2) # (16, 32, Time/2)
        )
        
        # Layer 2
        self.conv2 = nn.Sequential(
            nn.Conv2d(in_channels=16, out_channels=32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2) # (32, 16, Time/4)
        )
        
        # Layer 3
        self.conv3 = nn.Sequential(
            nn.Conv2d(in_channels=32, out_channels=64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(kernel_size=2) # (64, 8, Time/8)
        )

        self.conv4 = nn.Sequential(
            nn.Conv2d(in_channels=64, out_channels=128, kernel_size=3, padding=1), # 64ch -> 128ch
            nn.BatchNorm2d(128),
            nn.ReLU(),
            nn.MaxPool2d(2)
        )
        
        # Global Average Pooling
        self.gap = nn.AdaptiveAvgPool2d((1, 1)) 
        
        # Fully Connected
        self.fc = nn.Linear(128, num_classes)
        
    def forward(self, x):
        x = self.conv1(x)
        x = self.conv2(x)
        x = self.conv3(x)
        x = self.conv4(x)
        x = self.gap(x)       # shape: (Batch, 64, 1, 1)
        x = x.view(x.size(0), -1) # shape: (Batch, 64)
        x = self.fc(x)
    
        return x

def extract_pcen(audio, sr=24000, n_mels=128, n_fft=1024, hop_length=256, fixed_width=188):
    # fixed width: 出力するスペクトログラムの時間軸の長さ (基本188(2s))
    y = audio

    if len(y) < n_fft:
        y = librosa.util.fix_length(y, size=n_fft)


    melspec = librosa.feature.melspectrogram(
        y=y, sr=sr, 
        n_fft=n_fft, 
        hop_length=hop_length, 
        n_mels=n_mels,
        power=1.0 # power=1.0 -> 振幅スペクトログラム
    )

    pcen = librosa.pcen(
        melspec * (2**20),
        sr=sr,
        hop_length=hop_length,
        time_constant=1.5,
        gain=0.98,
        bias=2,
        power=0.5
    )

    current_width = pcen.shape[1]

    if current_width < fixed_width:
        # 足りない場合は右側を0埋め (パディング)
        pad_width = fixed_width - current_width
        min_val = pcen.min() # その画像の背景レベルを取得
        pcen = np.pad(pcen, ((0, 0), (0, pad_width)), mode='constant', constant_values=min_val)
    else:
        # 長すぎる場合は先頭から固定長だけ切り出し (トリミング)
        pcen = pcen[:, -fixed_width:]

    tensor = torch.tensor(pcen, dtype=torch.float32).unsqueeze(0).unsqueeze(0)


    return tensor