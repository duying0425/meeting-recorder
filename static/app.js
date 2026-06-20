document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const selectMic = document.getElementById('select-mic');
    const selectLoopback = document.getElementById('select-loopback');
    const btnRefresh = document.getElementById('btn-refresh');
    const btnRecord = document.getElementById('btn-record');
    const timerDisplay = document.getElementById('timer-display-element');
    const recordingBadge = document.getElementById('connection-status');
    const badgeText = recordingBadge.querySelector('.status-text');
    const recordingFilenameContainer = document.getElementById('filename-display-element');
    const spanFilename = document.getElementById('span-filename');
    
    // Volume Sliders
    const sliderMicGain = document.getElementById('slider-mic-gain');
    const sliderLoopbackVol = document.getElementById('slider-loopback-vol');
    const valMicGain = document.getElementById('val-mic-gain');
    const valLoopbackVol = document.getElementById('val-loopback-vol');
    
    // Level Meters
    const meterMic = document.getElementById('meter-mic');
    const meterLoopback = document.getElementById('meter-loopback');
    const textMicDb = document.getElementById('val-mic-db');
    const textLoopbackDb = document.getElementById('val-loopback-db');
    
    // Recordings List
    const tableBody = document.getElementById('recordings-list-body');
    const countBadge = document.getElementById('recording-count-badge');
    
    // Audio Player Preview
    const audioPreviewBar = document.getElementById('audio-preview-bar');
    const audioPlayer = document.getElementById('html-audio-player');
    const playerFilename = document.getElementById('player-filename');
    const btnClosePlayer = document.getElementById('btn-close-player');
    
    // Configuration Card (to disable during recording)
    const configCard = document.getElementById('config-card-element');

    // App State
    let isRecording = false;
    let statusInterval = null;
    const UPDATE_INTERVAL_MS = 100; // Fast updates for real-time visualizer meters (10fps)

    // Helper: Convert decibels (dB) to CSS width percentage (range: -60dB to 0dB)
    function dbToPercent(db) {
        if (db <= -60) return 0;
        if (db >= 0) return 100;
        return Math.round(((db + 60) / 60) * 100);
    }

    // Helper: Format seconds to HH:MM:SS
    function formatTime(totalSeconds) {
        const hrs = Math.floor(totalSeconds / 3600).toString().padStart(2, '0');
        const mins = Math.floor((totalSeconds % 3600) / 60).toString().padStart(2, '0');
        const secs = Math.floor(totalSeconds % 60).toString().padStart(2, '0');
        return `${hrs}:${mins}:${secs}`;
    }

    // Fetch and populate available audio sources
    async function loadDevices() {
        try {
            selectMic.innerHTML = '<option value="">Searching microphone devices...</option>';
            selectLoopback.innerHTML = '<option value="">Searching loopback devices...</option>';
            
            const res = await fetch('/api/devices');
            const data = await res.json();
            
            selectMic.innerHTML = '';
            selectLoopback.innerHTML = '';
            
            if (data.microphones.length === 0) {
                selectMic.innerHTML = '<option value="">No microphone found</option>';
            } else {
                data.microphones.forEach(device => {
                    const opt = document.createElement('option');
                    opt.value = device.index;
                    opt.textContent = device.name;
                    opt.selected = device.is_default;
                    selectMic.appendChild(opt);
                });
            }
            
            if (data.loopbacks.length === 0) {
                selectLoopback.innerHTML = '<option value="">No speakers loopback found</option>';
            } else {
                data.loopbacks.forEach(device => {
                    const opt = document.createElement('option');
                    opt.value = device.index;
                    opt.textContent = device.name;
                    opt.selected = device.is_default;
                    selectLoopback.appendChild(opt);
                });
            }
        } catch (err) {
            console.error('Failed to load audio devices:', err);
            selectMic.innerHTML = '<option value="">Error loading devices</option>';
            selectLoopback.innerHTML = '<option value="">Error loading devices</option>';
        }
    }

    // Fetch and populate recordings folder
    async function loadRecordings() {
        try {
            const res = await fetch('/api/recordings');
            const files = await res.json();
            
            countBadge.textContent = `${files.length} file${files.length !== 1 ? 's' : ''}`;
            
            if (files.length === 0) {
                tableBody.innerHTML = `
                    <tr class="empty-state-row">
                        <td colspan="5" class="empty-state">
                            <i class="fa-solid fa-circle-exclamation empty-icon"></i>
                            <p>No audio files found. Start recording a meeting above.</p>
                        </td>
                    </tr>`;
                return;
            }
            
            tableBody.innerHTML = '';
            files.forEach(file => {
                const tr = document.createElement('tr');
                
                // Formatted details
                const durationText = formatTime(file.duration);
                
                tr.innerHTML = `
                    <td><strong>${file.filename}</strong></td>
                    <td>${file.created}</td>
                    <td>${durationText}</td>
                    <td>${file.size_mb} MB</td>
                    <td class="text-right">
                        <div class="actions-cell">
                            <button class="btn-action play-btn" data-file="${file.filename}">
                                <i class="fa-solid fa-play"></i> Play
                            </button>
                            <button class="btn-action download-btn" data-file="${file.filename}">
                                <i class="fa-solid fa-download"></i> Save
                            </button>
                            <button class="btn-action delete-btn" data-file="${file.filename}">
                                <i class="fa-solid fa-trash-can"></i> Delete
                            </button>
                        </div>
                    </td>
                `;
                tableBody.appendChild(tr);
            });
            
            // Re-bind click events for dynamic rows
            bindTableEvents();
        } catch (err) {
            console.error('Failed to load recordings:', err);
        }
    }

    function bindTableEvents() {
        // Play
        tableBody.querySelectorAll('.play-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const filename = btn.getAttribute('data-file');
                playAudioFile(filename);
            });
        });
        
        // Download
        tableBody.querySelectorAll('.download-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const filename = btn.getAttribute('data-file');
                window.location.href = `/api/download/${encodeURIComponent(filename)}?download=true`;
            });
        });
        
        // Delete
        tableBody.querySelectorAll('.delete-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const filename = btn.getAttribute('data-file');
                if (confirm(`Are you sure you want to delete recording: ${filename}?`)) {
                    try {
                        const res = await fetch(`/api/delete/${encodeURIComponent(filename)}`, { method: 'POST' });
                        const data = await res.json();
                        if (data.success) {
                            loadRecordings();
                            // If deleted file is currently loaded in preview player, close it
                            if (playerFilename.textContent === filename) {
                                closeAudioPlayer();
                            }
                        } else {
                            alert('Error: ' + data.message);
                        }
                    } catch (err) {
                        alert('Failed to delete file.');
                    }
                }
            });
        });
    }

    // Play recording file in preview bar
    function playAudioFile(filename) {
        playerFilename.textContent = filename;
        audioPlayer.src = `/api/download/${encodeURIComponent(filename)}`;
        audioPreviewBar.classList.remove('hidden');
        audioPlayer.play().catch(err => console.log('Audio autoplay prevented:', err));
    }

    function closeAudioPlayer() {
        audioPlayer.pause();
        audioPlayer.src = '';
        audioPreviewBar.classList.add('hidden');
    }

    // Toggle recording start/stop
    async function toggleRecording() {
        if (!isRecording) {
            // START
            const micIndex = selectMic.value;
            const loopbackIndex = selectLoopback.value;
            
            if (!micIndex || !loopbackIndex) {
                alert('Please select valid microphone and loopback devices before recording.');
                return;
            }
            
            try {
                const res = await fetch('/api/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mic_index: micIndex,
                        loopback_index: loopbackIndex,
                        mic_gain: parseFloat(sliderMicGain.value),
                        loopback_vol: parseFloat(sliderLoopbackVol.value)
                    })
                });
                const data = await res.json();
                
                if (data.success) {
                    isRecording = true;
                    setRecordingUI(true, data.filename);
                    
                    // Start telemetry polling loop
                    statusInterval = setInterval(pollRecordingStatus, UPDATE_INTERVAL_MS);
                } else {
                    alert('Error starting recording: ' + data.message);
                }
            } catch (err) {
                alert('Network error. Failed to start recording.');
            }
        } else {
            // STOP
            try {
                btnRecord.disabled = true;
                const res = await fetch('/api/stop', { method: 'POST' });
                const data = await res.json();
                
                if (data.success) {
                    isRecording = false;
                    clearInterval(statusInterval);
                    setRecordingUI(false);
                    loadRecordings();
                } else {
                    alert('Error stopping recording: ' + data.message);
                }
            } catch (err) {
                alert('Network error. Failed to stop recording.');
            } finally {
                btnRecord.disabled = false;
            }
        }
    }

    // Update UI states
    function setRecordingUI(active, filename = "") {
        if (active) {
            btnRecord.classList.remove('ready');
            btnRecord.classList.add('recording');
            btnRecord.querySelector('.play-icon').classList.add('hidden');
            btnRecord.querySelector('.stop-icon').classList.remove('hidden');
            
            recordingBadge.classList.remove('online');
            recordingBadge.classList.add('recording');
            badgeText.textContent = 'Recording';
            
            recordingFilenameContainer.classList.remove('hidden');
            spanFilename.textContent = filename;
            
            // Disable config selects during recording (but keep sliders enabled for real-time control)
            selectMic.disabled = true;
            selectLoopback.disabled = true;
            btnRefresh.disabled = true;
        } else {
            btnRecord.classList.remove('recording');
            btnRecord.classList.add('ready');
            btnRecord.querySelector('.play-icon').classList.remove('hidden');
            btnRecord.querySelector('.stop-icon').classList.add('hidden');
            
            recordingBadge.classList.remove('recording');
            recordingBadge.classList.add('online');
            badgeText.textContent = 'Ready';
            
            recordingFilenameContainer.classList.add('hidden');
            timerDisplay.textContent = '00:00:00';
            
            // Reset meters
            meterMic.style.width = '0%';
            meterLoopback.style.width = '0%';
            textMicDb.textContent = '-100 dB';
            textLoopbackDb.textContent = '-100 dB';
            
            // Enable config selects
            selectMic.disabled = false;
            selectLoopback.disabled = false;
            btnRefresh.disabled = false;
        }
    }

    // Poll current recording duration and dB levels
    async function pollRecordingStatus() {
        if (!isRecording) return;
        try {
            const res = await fetch('/api/status');
            const data = await res.json();
            
            if (data.recording) {
                // Update Timer
                timerDisplay.textContent = formatTime(data.duration);
                
                // Update Microphone visualizer
                const micPercent = dbToPercent(data.db_mic);
                meterMic.style.width = `${micPercent}%`;
                textMicDb.textContent = data.db_mic <= -60 ? 'Silent' : `${data.db_mic} dB`;
                
                // Update Loopback visualizer
                const loopbackPercent = dbToPercent(data.db_loopback);
                meterLoopback.style.width = `${loopbackPercent}%`;
                textLoopbackDb.textContent = data.db_loopback <= -60 ? 'Silent' : `${data.db_loopback} dB`;
            } else {
                // Backend stopped recording (e.g. error)
                isRecording = false;
                clearInterval(statusInterval);
                setRecordingUI(false);
                loadRecordings();
            }
        } catch (err) {
            console.error('Error polling status:', err);
        }
    }

    // Sliders real-time adjustments
    sliderMicGain.addEventListener('input', () => {
        valMicGain.textContent = `${sliderMicGain.value}x`;
        sendGainAdjustment();
    });
    sliderLoopbackVol.addEventListener('input', () => {
        valLoopbackVol.textContent = `${sliderLoopbackVol.value}x`;
        sendGainAdjustment();
    });

    async function sendGainAdjustment() {
        if (!isRecording) return;
        try {
            await fetch('/api/adjust', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    mic_gain: parseFloat(sliderMicGain.value),
                    loopback_vol: parseFloat(sliderLoopbackVol.value)
                })
            });
        } catch (err) {
            console.error('Failed to adjust volume levels:', err);
        }
    }

    // Bind event listeners
    btnRecord.addEventListener('click', toggleRecording);
    btnRefresh.addEventListener('click', loadDevices);
    btnClosePlayer.addEventListener('click', closeAudioPlayer);

    const btnExit = document.getElementById('btn-exit');
    btnExit.addEventListener('click', async () => {
        if (confirm("Are you sure you want to exit and shut down the recorder application?")) {
            try {
                if (isRecording) {
                    clearInterval(statusInterval);
                    isRecording = false;
                }
                document.body.innerHTML = `
                    <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; font-family:'Outfit',sans-serif; background:linear-gradient(135deg, #0a0d16 0%, #151c30 100%); color:#f3f4f6; text-align:center; padding:1rem;">
                        <i class="fa-solid fa-power-off" style="font-size:4rem; color:#ef4444; margin-bottom:1.5rem;"></i>
                        <h1 style="font-size:2rem; font-weight:600; margin-bottom:0.5rem;">Application Closed</h1>
                        <p style="color:#9ca3af; max-width:400px; line-height:1.6;">The recorder server has been shut down successfully. You can now close this browser tab.</p>
                    </div>
                `;
                await fetch('/api/shutdown', { method: 'POST' });
            } catch (err) {
                console.log('App shutdown requested.');
            }
        }
    });

    // Initial load
    loadDevices();
    loadRecordings();
});
