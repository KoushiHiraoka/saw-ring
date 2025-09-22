import streamlit as st
import numpy as np
import socket
import struct
import matplotlib.pyplot as plt
import time
import pandas as pd
import pyaudio
import asyncio

# --- TCP設定 ---
ESP_IP = "192.168.4.1"  # ESP32のIPアドレス
PORT = 8000             # ポート番号
BUFFER_SIZE = 1024      # 一度に読み込むデータサイズ
SAMPLE_RATE = 24000     # サンプリングレート
FORMAT = pyaudio.paInt16 # PCMデータのフォーマット
num_samples = BUFFER_SIZE // 2
unpack_format = f'<{num_samples}h'  # フォーマット文字

# --- Streamlit設定 ---
st.set_page_config(layout="wide")
st.title("リアルタイムSAW波形可視化")
refresh_rate = 100

# --- 状態管理 (Session State) ---
if "client" not in st.session_state:
    st.session_state["client"] = None

# --- TCP接続 ---
if st.session_state.client is None:
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect((ESP_IP, PORT))
        st.session_state.client = client
        st.sidebar.success(f"接続成功: {ESP_IP}:{PORT}")
    except Exception as e:
        st.sidebar.error(f"接続失敗: {e}")
        st.stop()

# --- 波形描画用のプロット ---
fig, ax = plt.subplots()
x = np.linspace(0, BUFFER_SIZE / SAMPLE_RATE, num_samples)
y = np.zeros(BUFFER_SIZE // 2)
line, = ax.plot(x, y)
ax.set_ylim(-15000, 15000)
# ax.set_xlim(0, BUFFER_SIZE / SAMPLE_RATE)
ax.set_xlim(0, x[-1])
ax.set_xlabel("Time (s)")
ax.set_ylabel("Amplitude")
ax.set_title("PCM Waveform")

# Streamlitの描画領域を作成
plot_placeholder = st.empty()

# --- 非同期処理のメイン関数 ---
async def main():
    client = st.session_state.client
    buffer = b''

    # 接続が続く限り、無限にループ
    while True:
        try:
            loop = asyncio.get_event_loop()
            # client.recvはブロッキング処理なので、別スレッドで実行
            raw_data = await loop.run_in_executor(None, client.recv, BUFFER_SIZE)
            
            if not raw_data:
                st.error("接続が相手方から切断されました。")
                break # ループを抜ける

            buffer += raw_data

            if len(buffer) >= BUFFER_SIZE:
                data_to_process = buffer[:BUFFER_SIZE]
                buffer = buffer[BUFFER_SIZE:]
                pcm_data = np.frombuffer(data_to_process, dtype=np.int16)

                # データがなければスキップ
                if pcm_data.size == 0:
                    continue

                # ループの中でデータを更新
                pcm_data_df = pd.DataFrame(pcm_data) # データフレームに変換
                plot_placeholder.line_chart(pcm_data_df)

        except (ConnectionResetError, BrokenPipeError) as e:
            st.error(f"接続がリセットされました: {e}")
            break # ループを抜ける
        except Exception as e:
            st.error(f"予期せぬエラーが発生しました: {e}")
            break # ループを抜ける
            
        # 非同期で待機
        await asyncio.sleep(refresh_rate / 1000)

    # --- ループ終了後の後処理 ---
    st.info("描画を停止しました。")
    if st.session_state.client:
        st.session_state.client.close()
        st.session_state.client = None



# --- スクリプトの実行 ---
# 接続が確立されていれば、非同期のメイン関数を実行
if st.session_state.client:
    try:
        asyncio.run(main())
    except Exception as e:
        st.error(f"asyncioの実行中にエラーが発生しました: {e}")


# # --- データ取得と可視化 ---
# buffer = b''
# def update_waveform():
#     global buffer
#     try:
#         # TCPデータを受信
#         raw_data = client.recv(BUFFER_SIZE)
#         if not raw_data:
#             st.error("データ受信エラー: 接続が切断されました。")
#             return

#         # バッファにデータを追加
#         buffer += raw_data

#         # 必要なサイズに達した場合のみ処理を行う
#         if len(buffer) >= BUFFER_SIZE:
#             # 必要なサイズ分を切り出し
#             data_to_process = buffer[:BUFFER_SIZE]
#             buffer = buffer[BUFFER_SIZE:]  # 残りのデータをバッファに保持

#             # PCMデータをデコード
#             pcm_data = np.array(struct.unpack(unpack_format, data_to_process))

#             # 波形を更新
#             line.set_ydata(pcm_data)

#             # Streamlitの描画領域を更新
#             plot_placeholder.pyplot(fig)


#     except Exception as e:
#         st.error(f"エラーが発生しました: {e}")
#         raise

# # --- メインループ ---
# st.sidebar.button("開始", on_click=lambda: st.session_state.update({"running": True}))
# st.sidebar.button("停止", on_click=lambda: st.session_state.update({"running": False}))

# if "running" not in st.session_state:
#     st.session_state["running"] = False

# while st.session_state["running"]:
#     update_waveform()
#     time.sleep(refresh_rate / 1000)

# client.close()