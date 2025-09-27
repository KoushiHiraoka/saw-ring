import numpy as np
import librosa


SR = 44100
N_MELS = 128
FMIN = 0
FMAX = 24000
N_MFCC = 128
SILENCE_THRESH_DB = 30
N_SAMPLES = 300
N_CLASSES = 3
DURATION = 1.0


# -------------------------------------------------------------------
# 特徴量抽出 (cMFCC)
# -------------------------------------------------------------------
def extract_cmfcc(audio_segment, sr):
    trimmed_audio, _ = librosa.effects.trim(audio_segment, top_db=SILENCE_THRESH_DB)
    if len(trimmed_audio) == 0: return np.zeros(N_MFCC)
    mfccs = librosa.feature.mfcc(y=trimmed_audio, sr=sr, n_mfcc=N_MFCC, n_mels=N_MELS, fmin=FMIN, fmax=FMAX)
    return np.mean(mfccs, axis=1)


