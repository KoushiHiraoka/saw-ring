import streamlit as st
import numpy as np
import socket
import struct
import matplotlib.pyplot as plt
import time
import pandas as pd
import pyaudio

# --- TCP設定 ---
ESP_IP = "192.168.4.1"  # ESP32のIPアドレス
PORT = 8000             # ポート番号
BUFFER_SIZE = 1024      # 一度に読み込むデータサイズ
SAMPLE_RATE = 24000     # サンプリングレート
FORMAT = pyaudio.paInt16 # PCMデータのフォーマット
num_samples = BUFFER_SIZE // 2
unpack_format = f'<{num_samples}h'  # フォーマット文字

# --- Streamlit設定 ---
st.title("リアルタイムPCM音声波形可視化")
st.sidebar.header("設定")
refresh_rate = st.sidebar.slider("更新間隔 (ms)", 10, 500, 100)

# --- TCP接続 ---
try:
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((ESP_IP, PORT))
    st.sidebar.success(f"接続成功: {ESP_IP}:{PORT}")
except Exception as e:
    st.sidebar.error(f"接続失敗: {e}")
    st.stop()

# --- 波形描画用のプロット ---
fig, ax = plt.subplots()
x = np.linspace(0, BUFFER_SIZE / SAMPLE_RATE, num_samples)
y = np.zeros(BUFFER_SIZE // 2)
line, = ax.plot(x, y)
ax.set_ylim(-100, 100)
ax.set_xlim(0, BUFFER_SIZE / SAMPLE_RATE)
ax.set_xlabel("Time (s)")
ax.set_ylabel("Amplitude")
ax.set_title("PCM Waveform")

# Streamlitの描画領域を作成
plot_placeholder = st.empty()

# --- データ取得と可視化 ---
buffer = b''
def update_waveform():
    global buffer
    try:
        # TCPデータを受信
        raw_data = client.recv(BUFFER_SIZE)
        if not raw_data:
            st.error("データ受信エラー: 接続が切断されました。")
            return

        # バッファにデータを追加
        buffer += raw_data

        # 必要なサイズに達した場合のみ処理を行う
        if len(buffer) >= BUFFER_SIZE:
            # 必要なサイズ分を切り出し
            data_to_process = buffer[:BUFFER_SIZE]
            buffer = buffer[BUFFER_SIZE:]  # 残りのデータをバッファに保持

            # PCMデータをデコード
            pcm_data = np.array(struct.unpack(unpack_format, data_to_process))

            # 波形を更新
            line.set_ydata(pcm_data)

            # Streamlitの描画領域を更新
            with plot_placeholder.container():
                st.pyplot(fig)

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")

# --- メインループ ---
st.sidebar.button("開始", on_click=lambda: st.session_state.update({"running": True}))
st.sidebar.button("停止", on_click=lambda: st.session_state.update({"running": False}))

if "running" not in st.session_state:
    st.session_state["running"] = False

while st.session_state["running"]:
    update_waveform()
    time.sleep(refresh_rate / 1000)

client.close()