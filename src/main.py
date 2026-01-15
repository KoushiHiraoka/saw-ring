# main.py
import dearpygui.dearpygui as dpg
import numpy as np
from config import *
from udp import UDPListener
from signal_process import DSPProcessor
import traceback

# --- Global State ---
waveform_data = np.zeros(WAVE_WINDOW_SIZE, dtype=np.float32)
# HeatSeries用のデータは1次元配列として管理
spectro_saw = np.zeros((N_MELS, SPECTRO_WIDTH), dtype=np.float32)
data_list = spectro_saw.tolist()
x_indices_wave = np.arange(WAVE_WINDOW_SIZE)

listener = UDPListener()
dsp = DSPProcessor()

def setup_gui():
    dpg.create_context()
    dpg.create_viewport(title='SAW-RING DATA VISUALIZATION', width=1200, height=800)
    
    with dpg.window(tag="Primary Window"):
        # --- Header ---
        dpg.add_text("SAW-RING DATA VISUALIZATION", color=(0, 255, 255))
        dpg.add_separator()
        
        with dpg.group(horizontal=True):
            dpg.add_button(label="Start", callback=listener.start, width=100)
            dpg.add_button(label="Stop", callback=listener.stop, width=100)
            dpg.add_text("UDP Status: Idle", tag="status_text")

        dpg.add_spacer(height=10)

        with dpg.texture_registry(show=False):
            # 初期値として真っ黒な画像データを作成 (R,G,B,A) * 画素数
            dummy_data = np.zeros(SPECTRO_WIDTH * N_MELS * 4, dtype=np.float32)
            dpg.add_dynamic_texture(width=SPECTRO_WIDTH, height=N_MELS, default_value=dummy_data.tolist(), tag="spectro_saw")

        # --- Layout Table ---
        with dpg.table(header_row=True, borders_innerH=True, borders_outerH=True, 
                       borders_innerV=True, borders_outerV=True, resizable=True):
            
            dpg.add_table_column(label="Raw Waveform")
            dpg.add_table_column(label="Frequency Dist")
            dpg.add_table_column(label="Spectrogram")
            

            with dpg.table_row():
                # Waveform
                with dpg.plot(label="Time Series", height=400, width=-1, no_menus=True):
                    dpg.add_plot_legend()
                    dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="x_axis_wave")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Amp", tag="y_axis_wave")
                    dpg.set_axis_limits("y_axis_wave", -1.1, 1.1)
                    
                    dpg.add_line_series(x_indices_wave, waveform_data, 
                                        label="Raw", parent="y_axis_wave", tag="wave_series")
                # FFT
                with dpg.plot(label="Frequency", height=400, width=-1, no_menus=True):
                    dpg.add_plot_axis(dpg.mvXAxis, label="Hz", tag="x_axis_fft")
                    dpg.add_plot_axis(dpg.mvYAxis, label="Mag", tag="y_axis_fft")
                    dpg.set_axis_limits("y_axis_fft", 0, 100)
                    dpg.set_axis_limits("x_axis_fft", 0, MAX_FREQ_DISP)
                    
                    # dpg.add_bar_series([], [], weight=1, parent="y_axis_fft", tag="fft_series")
                    dpg.add_line_series([], [], parent="y_axis_fft", tag="fft_series")

                
                # Spectrogram
                with dpg.plot(label="Time-Freq", height=400, width=-1, no_menus=True):
                    dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="x_axis_spec", no_tick_labels=True)
                    dpg.add_plot_axis(dpg.mvYAxis, label="Mel Bin", tag="y_axis_spec")
                    dpg.add_image_series("spectro_saw", 
                                         [0, 0], 
                                         [SPECTRO_WIDTH, N_MELS], 
                                         parent="y_axis_spec",
                                         tag="spectro_series")

                

    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("Primary Window", True)

def update_loop():
    global waveform_data, spectro_saw
    
    try :
        new_data = listener.get_data()
        
        if new_data is not None:
            dpg.set_value("status_text", "UDP Status: Receiving...")
        
            # 1. Update Waveform
            chunk_len = len(new_data)
            if chunk_len > 0:
                waveform_data = np.roll(waveform_data, -chunk_len)
                waveform_data[-chunk_len:] = new_data
                dpg.set_value("wave_series", [x_indices_wave, waveform_data])

            # 2. Update Spectrogram (HOP_LENGTHごとに複数列)
            mel_cols = dsp.process_spectrogram_column(new_data)
            if mel_cols is not None:
                num_new = mel_cols.shape[1]
                if num_new > SPECTRO_WIDTH:
                    mel_cols = mel_cols[:, -SPECTRO_WIDTH:]
                    num_new = SPECTRO_WIDTH

                # データシフト
                spectro_saw = np.roll(spectro_saw, -num_new, axis=1)
                spectro_saw[:, -num_new:] = mel_cols

                # ★解説ポイント3: 色データの作成 (RGBA変換)
                # 1次元配列にする (画素数 = width * height)
                flat_data = spectro_saw.flatten()
                
                # 画素数 * 4 (RGBA) の配列を用意
                texture_rgba = np.ones(len(flat_data) * 4, dtype=np.float32)
                
                # R(赤), G(緑), B(青) チャンネルに値を代入
                # ここで色を調整できます (今は単純な青っぽいグラデーション)
                texture_rgba[0::4] = flat_data          # R
                texture_rgba[1::4] = flat_data          # G
                texture_rgba[2::4] = flat_data * 0.5 + 0.5 # B (青みを足す)
                # texture_rgba[3::4] は A(透明度)。初期値1.0のままでOK
                
                # ★解説ポイント4: テクスチャの更新
                dpg.set_value("spectro_saw", texture_rgba.tolist())
                
            # 3. Update FFT
            freqs, mags = dsp.compute_fft(new_data)
            mags = np.nan_to_num(mags, nan=0.0, posinf=0.0, neginf=0.0)
            mask = freqs <= MAX_FREQ_DISP
            dpg.set_value("fft_series", [freqs[mask], mags[mask]])
                
        else:
            if listener.running:
                dpg.set_value("status_text", "UDP Status: Waiting for data...")
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