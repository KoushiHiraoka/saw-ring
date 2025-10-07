import streamlit as st
import numpy as np
import socket
import pickle
import time
import pandas as pd
from utils import extract_cmfcc 

# --- 基本設定 ---
ESP_IP = "192.168.4.1"
PORT = 8000
BUFFER_SIZE = 2048  # 一度に受信するバッファサイズ
DTYPE = np.int16

SAMPLE_RATE = 24000 # 学習時のサンプリングレート
DURATION = 1.0      # 予測に使う音声データの秒数
SAMPLES_PER_PREDICTION = int(SAMPLE_RATE * DURATION) # 予測に必要なサンプル数
BYTES_PER_SAMPLE = np.dtype(DTYPE).itemsize
BYTES_PER_PREDICTION = SAMPLES_PER_PREDICTION * BYTES_PER_SAMPLE

# --- ラベル設定 ---
CLASS_NAMES = ["机", "非接触", "皮膚", "木材"]

# --- StreamlitのUI設定 ---
st.set_page_config(layout="wide")
st.title("Real-time Texture Recognition with SAW Ring")
st.markdown("表面弾性波 (SAW) をセンシングして、リアルタイムでテクスチャ認識を行います")

# --- モデルのロード ---
# @st.cache_resource を使うことで、モデルのロードを初回のみに限定
@st.cache_resource
def load_model(model_path="SVM_model.pkl"):
    try:
        with open(model_path, "rb") as f:
            model = pickle.load(f)
        return model
    except FileNotFoundError:
        st.error(f"モデルファイルが見つかりません: {model_path}")
        st.stop()

model = load_model()

# --- セッションステートの初期化 ---
if 'is_running' not in st.session_state:
    st.session_state.is_running = False
    st.session_state.tcp_client = None
    st.session_state.data_buffer = b''
    st.session_state.last_prediction = "非接触"

# --- UIレイアウト ---
col1, col2 = st.columns(2)
with col1:
    start_button = st.button("接続して認識開始", type="primary", use_container_width=True)
with col2:
    stop_button = st.button("停止して切断", use_container_width=True)

status_placeholder = st.empty()
st.divider()

col_pred, col_chart = st.columns([1, 2])
with col_pred:
    prediction_placeholder = st.empty()
with col_chart:
    chart_placeholder = st.empty()


# --- ボタンのロジック ---
if start_button and not st.session_state.is_running:
    st.session_state.is_running = True
    st.session_state.last_prediction = "受信待機中..."
    try:
        status_placeholder.info(f"ESP ({ESP_IP}:{PORT}) に接続中...")
        client = socket.create_connection((ESP_IP, PORT), timeout=5)
        st.session_state.tcp_client = client
        status_placeholder.success("接続に成功しました。データ受信待機中...")
    except Exception as e:
        status_placeholder.error(f"接続に失敗しました: {e}")
        st.session_state.is_running = False

if stop_button and st.session_state.is_running:
    st.session_state.is_running = False
    if st.session_state.tcp_client:
        st.session_state.tcp_client.close()
    st.session_state.tcp_client = None
    status_placeholder.warning("接続が切断されました。")
    time.sleep(1) # ユーザーがメッセージを読めるように少し待つ
    st.rerun() # 状態をリセットして再描画

prediction_placeholder.metric("予測されたテクスチャ", st.session_state.last_prediction)

# --- メインループ ---
if st.session_state.is_running and st.session_state.tcp_client:
    prediction_placeholder.metric("予測されたテクスチャ", st.session_state.last_prediction)
    try:
        # データを受信してバッファに追加
        raw_data = st.session_state.tcp_client.recv(BUFFER_SIZE)
        if not raw_data:
            status_placeholder.error("接続が失われました。")
            st.session_state.is_running = False
        
        st.session_state.data_buffer += raw_data

        # バッファに予測に必要なデータ量が溜まったかチェック
        if len(st.session_state.data_buffer) >= BYTES_PER_PREDICTION:
            # 必要なデータ量を切り出す
            data_to_process = st.session_state.data_buffer[:BYTES_PER_PREDICTION]
            # バッファから処理した分を削除
            st.session_state.data_buffer = st.session_state.data_buffer[BYTES_PER_PREDICTION:]

            # データをNumpy配列に変換
            pcm_data = np.frombuffer(data_to_process, dtype=DTYPE)
            # 正規化 (-1.0 ~ 1.0)
            normalized_data = pcm_data / 32768.0

            # --- 特徴量抽出 ---
            features = extract_cmfcc(normalized_data, SAMPLE_RATE)

            # --- 予測 ---
            # SVMモデルは (n_samples, n_features) の2次元配列を期待するため、reshapeする
            features_reshaped = features.reshape(1, -1)
            prediction_idx = model.predict(features_reshaped)
            predicted_label = CLASS_NAMES[prediction_idx[0]]

            st.session_state.last_prediction = predicted_label


    except socket.timeout:
        # タイムアウトは正常なケースなので何もしない
        pass
    except Exception as e:
        status_placeholder.error(f"❌ データ受信中にエラーが発生しました: {e}")
        st.session_state.is_running = False

    # ループを継続するために再実行
    time.sleep(0.01) # CPU負荷を抑える
    st.rerun()

else:
    # 初期状態のUI
    prediction_placeholder.info("認識結果はここに表示されます")
    chart_placeholder.info("受信した波形はここに表示されます")