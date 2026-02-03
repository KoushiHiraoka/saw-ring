import torch
import torch.nn as nn
import torchvision.models as models
import librosa
import numpy as np

def extract_pcen(audio, sr=24000, n_mels=128, n_fft=1024, hop_length=256, fixed_width=188):
    # fixed width: 出力するスペクトログラムの時間軸の長さ (基本188(2s))
    y = audio
    y = y - np.mean(y)  # DCオフセット除去

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
        time_constant=0.3,
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
        pcen = pcen[:, :fixed_width]


    return pcen

def ResNet18(num_classes):
    model = models.resnet18(weights=None)
    model.conv1 = nn.Conv2d(in_channels=1, out_channels=64, 
                            kernel_size=7, stride=2, padding=3, bias=False)
    model.fc = nn.Linear(model.fc.in_features, num_classes)
    
    return model
