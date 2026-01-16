import numpy as np
import librosa
from config import *

class DSPProcessor:
    def __init__(self):
        self.audio_buffer = np.zeros(N_FFT, dtype=np.float32)
        self.mel_basis = librosa.filters.mel(
            sr=SAMPLE_RATE, n_fft=N_FFT, n_mels=N_MELS
        )
        self._residual = np.zeros(0, dtype=np.float32)

    def process_spectrogram_column(self, new_audio_chunk):
        if new_audio_chunk is None or len(new_audio_chunk) == 0:
            return None
        self._residual = np.concatenate([self._residual, new_audio_chunk])

        cols = []
        while len(self._residual) >= HOP_LENGTH:
            hop_chunk = self._residual[:HOP_LENGTH]
            self._residual = self._residual[HOP_LENGTH:]

            self.audio_buffer = np.roll(self.audio_buffer, -HOP_LENGTH)
            self.audio_buffer[-HOP_LENGTH:] = hop_chunk

            windowed = self.audio_buffer * np.hanning(N_FFT)
            magnitude = np.abs(np.fft.rfft(windowed))
        
            mel_spec = np.dot(self.mel_basis, magnitude)
        
            mel_db = librosa.power_to_db(mel_spec, ref=1.0)
        
            mel_norm = (mel_db + 80) / 80
            mel_norm = np.clip(mel_norm, 0, 1)
        
            cols.append(mel_norm)
        
        if not cols:
            return None
        
        return np.stack(cols, axis=1)

    def compute_fft(self, audio_chunk):
        """周波数分布を計算"""
        if len(audio_chunk) < FFT_SIZE:
            padded = np.zeros(FFT_SIZE)
            padded[:len(audio_chunk)] = audio_chunk
            audio_chunk = padded
        else:
            audio_chunk = audio_chunk[-FFT_SIZE:]

        # FFT計算
        magnitude = np.abs(np.fft.rfft(audio_chunk * np.hanning(len(audio_chunk))))
        freqs = np.fft.rfftfreq(len(audio_chunk), 1/SAMPLE_RATE)
        
        return freqs, magnitude