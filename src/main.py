# main.py
import dearpygui.dearpygui as dpg
import matplotlib.pyplot as plt
import numpy as np
import traceback

from config import *
from udp import UDPListener
from signal_process import DSPProcessor

waveform_data = np.zeros(WAVE_WINDOW_SIZE, dtype=np.float32)
spectro_saw = np.zeros((N_MELS, SPECTRO_WIDTH), dtype=np.float32)
x_indices_wave_sec = np.arange(WAVE_WINDOW_SIZE) / SAMPLE_RATE

colormap = plt.get_cmap('viridis')
SCALE_FFT = 4.0

listener = UDPListener()
dsp = DSPProcessor()

def setup_gui():
    dpg.create_context()
    dpg.create_viewport(title='SAW-RING DATA VISUALIZATION', width=1200, height=800)
    
    with dpg.window(tag="Primary Window"):
        # --- Header ---
        dpg.add_text("SAW DATA VISUALIZATION", color=(0, 255, 255))
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
                dpg.set_value("wave_series", [x_indices_wave_sec, waveform_data])

            # 2. Update Spectrogram
            mel_cols = dsp.process_spectrogram_column(new_data)
            if mel_cols is not None:
                num_new = mel_cols.shape[1]
                if num_new > SPECTRO_WIDTH:
                    mel_cols = mel_cols[:, -SPECTRO_WIDTH:]
                    num_new = SPECTRO_WIDTH

                # データシフト
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