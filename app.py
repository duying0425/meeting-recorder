import os
import sys
import time
import queue
import threading
import datetime
import webbrowser
import numpy as np
import soundfile as sf
import pyaudiowpatch as pyaudio
from flask import Flask, jsonify, request, send_from_directory, render_template

# Enforce UTF-8 stdout
sys.stdout.reconfigure(encoding='utf-8')

app = Flask(__name__, static_folder='static', template_folder='templates')

RECORDINGS_DIR = os.path.join(os.getcwd(), 'recordings')
os.makedirs(RECORDINGS_DIR, exist_ok=True)

# Recording State Variables
recording_active = False
recording_thread = None
silence_thread = None
stop_event = threading.Event()

# Dynamic Volume Multipliers (Adjustable in real-time)
current_mic_gain = 1.5
current_loopback_vol = 0.5

# Audio statistics for visualizer telemetry
latest_db_mic = -100.0
latest_db_loopback = -100.0
recording_start_time = None
current_filename = ""

# Audio configuration
SAMPLE_RATE = 48000
CHUNK_SIZE = 1024

# Queues for audio frames
mic_queue = queue.Queue()
loopback_queue = queue.Queue()

# Lock for shared states
state_lock = threading.Lock()

def calculate_db(audio_bytes, channels=1):
    """Calculate average decibel level from raw PCM 16-bit bytes."""
    if not audio_bytes:
        return -100.0
    try:
        data = np.frombuffer(audio_bytes, dtype=np.int16)
        if len(data) == 0:
            return -100.0
        # Calculate Root Mean Square
        rms = np.sqrt(np.mean(data.astype(np.float64) ** 2))
        if rms <= 0.1:
            return -100.0
        # Convert to dB relative to full scale (16-bit max is 32768)
        db = 20 * np.log10(rms / 32768.0)
        # Cap at -100 to 0 dB range
        return max(-100.0, min(0.0, db))
    except Exception:
        return -100.0

def mic_callback(in_data, frame_count, time_info, status):
    mic_queue.put(in_data)
    return (None, pyaudio.paContinue)

def loopback_callback(in_data, frame_count, time_info, status):
    loopback_queue.put(in_data)
    return (None, pyaudio.paContinue)

def play_silence_thread_func(p, speaker_index):
    """Play silence to keep WASAPI output device active."""
    try:
        stream = p.open(
            format=pyaudio.paInt16,
            channels=2,
            rate=SAMPLE_RATE,
            output=True,
            output_device_index=speaker_index,
            frames_per_buffer=CHUNK_SIZE
        )
        stream.start_stream()
        silent_chunk = b'\x00' * (CHUNK_SIZE * 2 * 2) # Stereo 16-bit
        while not stop_event.is_set():
            stream.write(silent_chunk)
            # Sleep slightly less than the buffer duration to prevent underruns
            time.sleep(0.01)
        stream.stop_stream()
        stream.close()
    except Exception as e:
        print(f"Error in silence player: {e}")

def recorder_loop(mic_index, loopback_index, filename):
    global latest_db_mic, latest_db_loopback, recording_active
    
    p = pyaudio.PyAudio()
    filepath = os.path.join(RECORDINGS_DIR, filename)
    
    try:
        # Get matching speakers for loopback to play silence
        loopback_info = p.get_device_info_by_index(loopback_index)
        speaker_index = p.get_default_output_device_info()['index']
        
        # Match loopback name to find appropriate output speakers if default fails
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev['maxOutputChannels'] > 0 and dev['name'] in loopback_info['name']:
                speaker_index = i
                break
                
        # Start silence thread
        global silence_thread
        silence_thread = threading.Thread(
            target=play_silence_thread_func, 
            args=(p, speaker_index), 
            daemon=True
        )
        silence_thread.start()
        time.sleep(0.2) # Wait for silence thread to warm up
        
        # Flush any garbage in queues
        while not mic_queue.empty(): mic_queue.get()
        while not loopback_queue.empty(): loopback_queue.get()
        
        # Open streams
        mic_stream = p.open(
            format=pyaudio.paInt16,
            channels=1, # Capture mono mic
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=mic_index,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=mic_callback
        )
        
        loopback_stream = p.open(
            format=pyaudio.paInt16,
            channels=2, # Capture stereo loopback
            rate=SAMPLE_RATE,
            input=True,
            input_device_index=loopback_index,
            frames_per_buffer=CHUNK_SIZE,
            stream_callback=loopback_callback
        )
        
        mic_stream.start_stream()
        loopback_stream.start_stream()
        
        print(f"Recording started. Output file: {filepath}")
        
        with sf.SoundFile(filepath, mode='w', samplerate=SAMPLE_RATE, channels=2, subtype='PCM_16') as file:
            while not stop_event.is_set():
                try:
                    # Get loopback and mic audio frames
                    loopback_bytes = loopback_queue.get(timeout=0.1)
                    mic_bytes = mic_queue.get(timeout=0.1)
                    
                    # Update real-time decibel telemetry
                    latest_db_loopback = calculate_db(loopback_bytes, channels=2)
                    latest_db_mic = calculate_db(mic_bytes, channels=1)
                    
                    # Convert to NumPy array
                    loopback_data = np.frombuffer(loopback_bytes, dtype=np.int16).reshape(-1, 2)
                    mic_data = np.frombuffer(mic_bytes, dtype=np.int16)
                    
                    # Align chunk sizes
                    min_len = min(len(loopback_data), len(mic_data))
                    if min_len == 0:
                        continue
                        
                    loopback_data = loopback_data[:min_len]
                    mic_data = mic_data[:min_len]
                    
                    # Normalize signals
                    loopback_float = loopback_data.astype(np.float32) / 32768.0
                    mic_float = mic_data.astype(np.float32) / 32768.0
                    
                    # Expand mono microphone to stereo channels
                    mic_stereo = np.column_stack((mic_float, mic_float))
                    
                    # Mix: use dynamic scale factors (updated in real-time)
                    g_loop = current_loopback_vol
                    g_mic = current_mic_gain
                    mixed_float = (loopback_float * g_loop) + (mic_stereo * g_mic)
                    mixed_float = np.clip(mixed_float, -1.0, 1.0)
                    
                    # Write to file
                    file.write(mixed_float)
                    
                except queue.Empty:
                    # Occurs when queue timeout expires
                    continue
                    
        # Stop streams
        mic_stream.stop_stream()
        mic_stream.close()
        loopback_stream.stop_stream()
        loopback_stream.close()
        
        # Wait for the silence output thread to finish using PortAudio
        if silence_thread:
            silence_thread.join(timeout=3.0)
        
    except Exception as e:
        print(f"Exception in recording loop: {e}")
    finally:
        latest_db_mic = -100.0
        latest_db_loopback = -100.0
        p.terminate()
        with state_lock:
            recording_active = False
        print("Recording thread terminated.")

# API ROUTES

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/devices', methods=['GET'])
def get_devices():
    p = pyaudio.PyAudio()
    microphones = []
    loopbacks = []
    
    # Track default devices
    default_input_idx = -1
    default_output_idx = -1
    default_mic_name = ""
    try:
        default_input_idx = p.get_default_input_device_info()['index']
        default_mic_name = p.get_default_input_device_info()['name']
        default_output_idx = p.get_default_output_device_info()['index']
    except Exception:
        pass
        
    for i in range(p.get_device_count()):
        try:
            dev = p.get_device_info_by_index(i)
            api_name = p.get_host_api_info_by_index(dev['hostApi'])['name']
            
            # Loopback devices (always WASAPI)
            if api_name == 'Windows WASAPI' and "loopback" in dev['name'].lower():
                # Clean name: remove "[Loopback]" for aesthetic purposes
                display_name = dev['name'].replace("[Loopback]", "").strip()
                loopbacks.append({
                    'index': dev['index'],
                    'name': display_name,
                    'is_default': default_output_idx != -1 and p.get_device_info_by_index(default_output_idx)['name'] in dev['name']
                })
            # Microphone devices (input, not loopback)
            elif dev['maxInputChannels'] > 0 and "loopback" not in dev['name'].lower():
                microphones.append({
                    'index': dev['index'],
                    'name': dev['name'],
                    'host_api': api_name,
                    'is_default': dev['index'] == default_input_idx
                })
        except Exception:
            continue
            
    p.terminate()
    
    # Smart filtering: If WASAPI microphones are available, keep ONLY them.
    # Otherwise, fallback to showing all.
    wasapi_mics = [m for m in microphones if m['host_api'] == 'Windows WASAPI']
    if wasapi_mics:
        # Match default device by name among WASAPI devices (since system default index may point to MME version)
        has_default = False
        for m in wasapi_mics:
            if default_mic_name and default_mic_name in m['name']:
                m['is_default'] = True
                has_default = True
            else:
                m['is_default'] = False
                
        if not has_default and wasapi_mics:
            wasapi_mics[0]['is_default'] = True
            
        microphones = wasapi_mics
    else:
        # Fallback formatting: Append API name if we are showing legacy mixed devices
        for m in microphones:
            m['name'] = f"{m['name']} ({m['host_api']})"
            
    return jsonify({
        'microphones': microphones,
        'loopbacks': loopbacks
    })

@app.route('/api/start', methods=['POST'])
def start_recording():
    global recording_active, recording_thread, recording_start_time, current_filename, stop_event
    
    with state_lock:
        if recording_active:
            return jsonify({'success': False, 'message': 'Recording is already active'}), 400
            
        data = request.json or {}
        mic_index = data.get('mic_index')
        loopback_index = data.get('loopback_index')
        
        if mic_index is None or loopback_index is None:
            return jsonify({'success': False, 'message': 'Missing microphone or loopback index'}), 400
            
        # Formulate timestamped filename
        now = datetime.datetime.now()
        current_filename = f"Meeting_{now.strftime('%Y%m%d_%H%M%S')}.wav"
        
        # Load initial gain selections
        global current_mic_gain, current_loopback_vol
        current_mic_gain = float(data.get('mic_gain', 1.5))
        current_loopback_vol = float(data.get('loopback_vol', 0.5))
        
        # Start Thread
        stop_event.clear()
        recording_active = True
        recording_start_time = time.time()
        
        recording_thread = threading.Thread(
            target=recorder_loop,
            args=(int(mic_index), int(loopback_index), current_filename),
            daemon=True
        )
        recording_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Recording started',
            'filename': current_filename
        })

@app.route('/api/stop', methods=['POST'])
def stop_recording():
    global recording_active, recording_thread, stop_event
    
    with state_lock:
        if not recording_active:
            return jsonify({'success': False, 'message': 'No recording is active'}), 400
            
        # Trigger stop signal
        stop_event.set()
        
    # Wait for the main recording thread to clean up everything
    if recording_thread:
        recording_thread.join(timeout=5.0)
        
    return jsonify({
        'success': True,
        'message': 'Recording stopped',
        'filename': current_filename
    })

@app.route('/api/adjust', methods=['POST'])
def adjust_gains():
    global current_mic_gain, current_loopback_vol
    data = request.json or {}
    
    if 'mic_gain' in data:
        current_mic_gain = float(data['mic_gain'])
    if 'loopback_vol' in data:
        current_loopback_vol = float(data['loopback_vol'])
        
    return jsonify({
        'success': True,
        'mic_gain': current_mic_gain,
        'loopback_vol': current_loopback_vol
    })

@app.route('/api/status', methods=['GET'])
def get_status():
    global recording_active, recording_start_time, latest_db_mic, latest_db_loopback, current_filename
    
    duration = 0.0
    if recording_active and recording_start_time:
        duration = time.time() - recording_start_time
        
    return jsonify({
        'recording': recording_active,
        'duration': round(duration, 1),
        'filename': current_filename if recording_active else "",
        'db_mic': round(latest_db_mic, 1),
        'db_loopback': round(latest_db_loopback, 1)
    })

@app.route('/api/recordings', methods=['GET'])
def list_recordings():
    files = []
    if not os.path.exists(RECORDINGS_DIR):
        return jsonify([])
        
    for name in os.listdir(RECORDINGS_DIR):
        if name.endswith('.wav'):
            path = os.path.join(RECORDINGS_DIR, name)
            stat = os.stat(path)
            created = datetime.datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            
            # Simple duration estimation (48kHz, stereo 16-bit = 192,000 bytes/sec)
            duration_sec = 0
            if stat.st_size > 44:
                duration_sec = round((stat.st_size - 44) / (SAMPLE_RATE * 2 * 2))
                
            files.append({
                'filename': name,
                'created': created,
                'size_mb': size_mb,
                'duration': duration_sec
            })
            
    # Sort files by newest first
    files.sort(key=lambda x: x['created'], reverse=True)
    return jsonify(files)

@app.route('/api/download/<filename>', methods=['GET'])
def download_recording(filename):
    as_attachment = request.args.get('download', 'false').lower() == 'true'
    return send_from_directory(RECORDINGS_DIR, filename, as_attachment=as_attachment)

@app.route('/api/delete/<filename>', methods=['POST'])
def delete_recording(filename):
    filepath = os.path.join(RECORDINGS_DIR, filename)
    if os.path.exists(filepath):
        try:
            os.remove(filepath)
            return jsonify({'success': True, 'message': f'Deleted {filename}'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 500
    return jsonify({'success': False, 'message': 'File not found'}), 404

def run_server():
    # Start web browser after 1 second delay
    def open_browser():
        time.sleep(1.0)
        webbrowser.open("http://127.0.0.1:5000")
        
    threading.Thread(target=open_browser, daemon=True).start()
    app.run(host='127.0.0.1', port=5000, debug=False)

if __name__ == '__main__':
    run_server()
