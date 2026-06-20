# Meeting Audio Recorder 🎙️

An elegant, dual-channel meeting audio recorder for Windows that captures both system output (what you hear, e.g., other participants in Zoom/Teams) and your microphone (what you say) in perfect synchronization. 

It mixes the streams in real-time and saves them as a standard WAV file. Control is managed via a beautiful, dark-themed glassmorphism web interface that opens automatically.

---

## Key Features ✨

*   **WASAPI Loopback Capture**: Captures digital system audio directly from the Windows audio engine. It works **independently of your physical Windows volume slider**—even if you mute your computer, the meeting is still recorded at 100% volume.
*   **Active Silent Output Loop**: Bypasses the Windows WASAPI loopback limitation (which stops sending frames when there is silence) by running an inaudible background silent playback thread. This keeps the loopback device active and ensures **perfect synchronization** between your microphone and the meeting audio.
*   **Real-time Volume Balance Sliders**: Adjust microphone boost (up to 3.0x) and system audio scale (down to 10% volume) on-the-fly *during* recording.
*   **Smart Device Filtering**: Cleaned interface that displays only optimal Windows WASAPI devices, avoiding legacy MME or DirectSound duplicates.
*   **Built-in Preview Player**: Play, download, or delete past recordings directly from the dashboard.
*   **Standalone EXE / Console-free**: Runs as a single executable without showing a command window.

---

## Quick Start 🚀

### Option A: Using the Compiled Executable (Standalone)
1. Download the compiled `MeetingRecorder.exe` from the Releases section (or compile it yourself following the instructions below).
2. Double-click **`MeetingRecorder.exe`**.
3. The server starts silently in the background, and your default web browser will automatically open to `http://127.0.0.1:5000`.
4. Select your audio sources, click **Record**, and manage your recording.
5. Simply close the browser tab to automatically stop and close the background server (via built-in heartbeat watchdog).

### Option B: Running from Source
1. Double-click **`run.bat`** in the root directory.
2. The batch script will automatically create a Python virtual environment, upgrade pip, install all dependencies, and launch the server.

---

## Building the Standalone EXE 🛠️

To package the application into a single executable file with a hidden console:

1. Install PyInstaller in your Python environment:
   ```bash
   pip install pyinstaller
   ```
2. Run the packaging command, bundling the Flask HTML templates and static assets:
   ```bash
   pyinstaller --noconsole --onefile --add-data "templates;templates" --add-data "static;static" --name "MeetingRecorder" app.py
   ```
3. Once completed, your standalone executable will be generated at `dist/MeetingRecorder.exe`.

---

## Technology Stack 📚

*   **Backend**: Python, Flask, PyAudioWPatch, SoundDevice, SoundFile, NumPy
*   **Frontend**: HTML5, Vanilla CSS3 (Glassmorphism design system), Javascript ES6
