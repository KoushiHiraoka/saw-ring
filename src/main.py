import dearpygui.dearpygui as dpg
import matplotlib.pyplot as plt
import numpy as np
import traceback
import time
from collections import deque

from config import *
from udp import UDPListener
from signal_process import DSPProcessor
from surface_recognition.inference import InferenceEngine  

waveform_data = np.zeros(WAVE_WINDOW_SIZE, dtype=np.float32)
spectro_saw = np.zeros((N_MELS, SPECTRO_WIDTH), dtype=np.float32)
x_indices_wave_sec = np.arange(WAVE_WINDOW_SIZE) / SAMPLE_RATE

colormap = plt.get_cmap('viridis')
last_inference_time = 0.0
SCALE_FFT = 4.0

TH_HIGH = 0.6 # イベント開始
TH_LOW = 0.5 # イベント終了
N_TRIGGER_FRAMES = 2

listener = UDPListener()
dsp = DSPProcessor()
inference_engine = InferenceEngine()
class EventState:
    IDLE = "IDLE"
    TRIGGERED = "TRIGGERED"

current_state = EventState.IDLE
trigger_counter = 0
miss_counter = 0
last_triggered_label = None
prediction_history = deque(maxlen=10)
display_label = "---"  # GUI表示用のラベル
display_confidence = 0.0  # GUI表示用の確信度  

def setup_gui():
    dpg.create_context()

    with dpg.font_registry():
        font = dpg.add_font("/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc", 20)
        dpg.add_font_range_hint(dpg.mvFontRangeHint_Japanese, parent=font)

    dpg.create_viewport(title='SAW-RING DATA VISUALIZATION', width=1200, height=800)

    dpg.set_global_font_scale(1) # 全体のサイズ変更(フォント含む)
    dpg.bind_font(font) 
    
    with dpg.window(tag="Primary Window"):
        # Header
        dpg.add_text("SAW DATA VISUALIZATION", color=(0, 255, 255))
        dpg.add_separator()
        
        with dpg.group(horizontal=True):
            dpg.add_button(label="Start", callback=listener.start, width=100)
            dpg.add_button(label="Stop", callback=listener.stop, width=100)
            # dpg.add_text("UDP Status: Idle", tag="status_text")

        dpg.add_spacer(height=10)

        # Prediction Table
        with dpg.table(header_row=True, borders_innerH=True, borders_outerH=True,
                       borders_innerV=True, borders_outerV=True):
            dpg.add_table_column(label="Predicted Surface")
            dpg.add_table_column(label="Confidence")
            
            with dpg.table_row():
                dpg.add_text("---", tag="predicted_label", color=(255, 255, 0))
                dpg.add_text("0.00%", tag="confidence_label", color=(255, 100, 0))
        # ------------------------

        dpg.add_spacer(height=10)

        with dpg.texture_registry(show=False):
            # 初期値 (黒画像)
            dummy_data = np.zeros(SPECTRO_WIDTH * N_MELS * 4, dtype=np.float32)
            dpg.add_dynamic_texture(width=SPECTRO_WIDTH, height=N_MELS, default_value=dummy_data.tolist(), tag="spectro_saw")

        # Layout Table
        with dpg.table(header_row=True, borders_innerH=True, borders_outerH=True, 
                       borders_innerV=True, borders_outerV=True, resizable=True):
            
            dpg.add_table_column(label="Sensor Data")
            with dpg.table_row():
                # Waveform
                with dpg.plot(label="Time Series", height=250, width=-1, no_menus=True):
                    dpg.add_plot_legend()
                    dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="x_axis_wave")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Amp", tag="y_axis_wave")
                    dpg.set_axis_limits("y_axis_wave", -1.1, 1.1)
                    
                    dpg.add_line_series(x_indices_wave_sec, waveform_data, 
                                        label="Raw", parent="y_axis_wave", tag="wave_series")
                    
            with dpg.table_row():
                # FFT
                with dpg.plot(label="Frequency", height=250, width=-1, no_menus=True):
                    dpg.add_plot_axis(dpg.mvXAxis, label="kHz", tag="x_axis_fft")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Magnitude", tag="y_axis_fft")
                    dpg.set_axis_limits("y_axis_fft", 0, 1)
                    dpg.set_axis_limits("x_axis_fft", 0, MAX_FREQ_DISP / 1000.0)
                    
                    dpg.add_line_series([], [], parent="y_axis_fft", tag="fft_series")

            with dpg.table_row():
                # Spectrogram
                with dpg.plot(label="Time-Freq", height=250, width=-1, no_menus=True):
                    dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="x_axis_spec", no_tick_labels=True)
                    dpg.add_plot_axis(dpg.mvYAxis, label="Frequency (kHz)", tag="y_axis_spec")
                    max_freq = (SAMPLE_RATE / 2) / 1000.0
                    dpg.add_image_series("spectro_saw", 
                                         [0, 0], 
                                         [SPECTRO_WIDTH, max_freq], 
                                         parent="y_axis_spec",
                                         tag="spectro_series")
            

                

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)

def check_event_trigger(label, confidence):
    """状態遷移ロジック: イベントの開始・終了を判定"""
    global current_state, trigger_counter, miss_counter, last_triggered_label, display_label, display_confidence
    
    event_started = False
    event_ended = False
    
    if current_state == EventState.IDLE:
        # IDLE状態: 高確信度が連続したらTRIGGERED
        if confidence >= TH_HIGH and label != "None":
            if last_triggered_label == label:
                trigger_counter += 1
            else:
                trigger_counter = 1
                last_triggered_label = label
            
            if trigger_counter >= N_TRIGGER_FRAMES:
                current_state = EventState.TRIGGERED
                event_started = True
                display_label = label  # 表示ラベルを固定
                display_confidence = confidence
                print(f"[EVENT START] {label} (conf: {confidence:.2f})")
        else:
            trigger_counter = 0
            last_triggered_label = None
            # IDLE状態では常に更新
            display_label = label
            display_confidence = confidence
            
    elif current_state == EventState.TRIGGERED:
        # TRIGGERED状態: 確信度が低下したらIDLEに戻る
        if confidence < TH_LOW or label != last_triggered_label:
            miss_counter += 1
        else:
            miss_counter = 0

        if miss_counter >= N_TRIGGER_FRAMES:
            current_state = EventState.IDLE
            event_ended = True
            print(f"[EVENT END] {last_triggered_label}")
            trigger_counter = 0
            miss_counter = 0
            last_triggered_label = None
            # イベント終了時に現在の予測で更新
            display_label = label
            display_confidence = confidence
        # TRIGGERED中は display_label を更新しない（固定表示）
    
    return event_started, event_ended


def update_loop():
    global waveform_data, spectro_saw, last_inference_time, current_state
    

    try :
        new_data = listener.get_data()
        

        if new_data is not None:
            # dpg.set_value("status_text", "UDP Status: Receiving...")
            # 1. Update Waveform
            chunk_len = len(new_data)
            if chunk_len > 0:
                waveform_data = np.roll(waveform_data, -chunk_len)
                waveform_data[-chunk_len:] = new_data
                dpg.set_value("wave_series", [x_indices_wave_sec, waveform_data])

            # 2. Update Spectrogram
            mel_cols = dsp.process_spectrogram_column(new_data)
            if mel_cols is not None:
                num_new = mel_cols.shape[1]
                if num_new > SPECTRO_WIDTH:
                    mel_cols = mel_cols[:, -SPECTRO_WIDTH:]
                    num_new = SPECTRO_WIDTH

                spectro_saw = np.roll(spectro_saw, -num_new, axis=1)
                spectro_saw[:, -num_new:] = mel_cols
                flipped_saw = spectro_saw[::-1, :]
                flat_data = flipped_saw.flatten()

                rgba_mapped = colormap(flat_data)
                texture_rgba = rgba_mapped.flatten().astype(np.float32)
                
                dpg.set_value("spectro_saw", texture_rgba.tolist())
                
            # 3. Update FFT
            freqs, mags = dsp.compute_fft(new_data)
            mags = np.nan_to_num(mags, nan=0.0, posinf=0.0, neginf=0.0)
            mask = (freqs > 0) & (freqs <= MAX_FREQ_DISP)

            freqs_khz = freqs[mask] / 1000.0 
            filtered_mags = mags[mask] / SCALE_FFT
            
            dpg.set_value("fft_series", [freqs_khz, filtered_mags])

            # 4. Inference
            current_time = time.time()
            if current_time - last_inference_time > INFERENCE_INTERVAL:
                label, conf = inference_engine.predict(waveform_data)
                prediction_history.append((label, conf))
                check_event_trigger(label, conf)
                
                if display_label == "None":
                    dpg.set_value("predicted_label", "別の場所に触れています")
                else:
                    dpg.set_value("predicted_label", display_label)
                dpg.set_value("confidence_label", f"{display_confidence * 100:.1f}%")
                
                # 確信度に応じて色を変える
                if display_confidence > 0.8:
                    dpg.configure_item("predicted_label", color=(0, 255, 0)) # 高信頼度: 緑
                else:
                    dpg.configure_item("predicted_label", color=(255, 255, 0)) # 低信頼度: 黄
                
                last_inference_time = current_time
                
        # else:
        #     if listener.running:
        #         dpg.set_value("status_text", "UDP Status: Waiting for data...")
    except Exception as e:
        err_msg = f"Update Error: {str(e)}"
        print(err_msg)
        traceback.print_exc()

if __name__ == "__main__":
    setup_gui()
    while dpg.is_dearpygui_running():
        update_loop()
        dpg.render_dearpygui_frame()

    listener.stop()
    dpg.destroy_context()