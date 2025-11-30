class VoiceChatApp {
    constructor() {
        this.websocket = null;
        this.mediaRecorder = null;
        this.audioContext = null;
        this.isRecording = false;
        this.isConnected = false;
        this.audioStream = null;

        // DOM elements
        this.connectBtn = document.getElementById('connectBtn');
        this.disconnectBtn = document.getElementById('disconnectBtn');
        this.startRecordingBtn = document.getElementById('startRecording');
        this.stopRecordingBtn = document.getElementById('stopRecording');
        this.connectionStatus = document.getElementById('connectionStatus');
        this.recordingStatus = document.getElementById('recordingStatus');
        this.transcriptContainer = document.getElementById('transcript');
        this.roomIdInput = document.getElementById('roomId');
        this.userIdInput = document.getElementById('userId');

        this.initializeEventListeners();
    }

    initializeEventListeners() {
        this.connectBtn.addEventListener('click', () => this.connect());
        this.disconnectBtn.addEventListener('click', () => this.disconnect());
        this.startRecordingBtn.addEventListener('click', () => this.startRecording());
        this.stopRecordingBtn.addEventListener('click', () => this.stopRecording());

        // Enter key for room connection
        this.roomIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.connect();
        });

        this.userIdInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') this.connect();
        });
    }

    async connect() {
        const roomId = this.roomIdInput.value.trim();
        const userId = this.userIdInput.value.trim();

        if (!roomId || !userId) {
            alert('Пожалуйста, введите ID комнаты и ваш ID');
            return;
        }

        try {
            // WebSocket connection
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/api/ws/${roomId}`;

            this.websocket = new WebSocket(wsUrl);

            this.websocket.onopen = () => {
                this.isConnected = true;
                this.updateUI();
                this.connectionStatus.textContent = 'Подключено';
                document.body.classList.add('connected');
                console.log('WebSocket connected');

                // Request history after connection
                this.websocket.send(JSON.stringify({
                    type: 'get_history'
                }));
            };

            this.websocket.onmessage = (event) => {
                this.handleWebSocketMessage(JSON.parse(event.data));
            };

            this.websocket.onclose = () => {
                this.isConnected = false;
                this.updateUI();
                this.connectionStatus.textContent = 'Отключено';
                document.body.classList.remove('connected');
                console.log('WebSocket disconnected');
            };

            this.websocket.onerror = (error) => {
                console.error('WebSocket error:', error);
                alert('Ошибка подключения к серверу');
            };

        } catch (error) {
            console.error('Connection error:', error);
            alert('Ошибка подключения');
        }
    }

    disconnect() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
        }

        if (this.isRecording) {
            this.stopRecording();
        }

        this.isConnected = false;
        this.updateUI();
    }

    async startRecording() {
        if (!this.isConnected) {
            alert('Сначала подключитесь к комнате');
            return;
        }

        try {
            // Get microphone access
            this.audioStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    channelCount: 1,
                    sampleRate: 16000,
                    echoCancellation: true,
                    noiseSuppression: true
                }
            });

            // Initialize audio context
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });

            const source = this.audioContext.createMediaStreamSource(this.audioStream);

            // Create processor for audio data
            const bufferSize = 4096;
            const processor = this.audioContext.createScriptProcessor(bufferSize, 1, 1);

            processor.onaudioprocess = (event) => {
                if (this.isRecording && this.isConnected) {
                    // Get audio data from input buffer
                    const inputBuffer = event.inputBuffer;
                    const channelData = inputBuffer.getChannelData(0); // Get first channel
                    this.sendAudioChunk(channelData);
                }
            };

            source.connect(processor);
            processor.connect(this.audioContext.destination);

            this.isRecording = true;
            this.updateUI();
            this.recordingStatus.textContent = 'Запись активна';
            document.body.classList.add('recording');

            console.log('Recording started');

        } catch (error) {
            console.error('Error starting recording:', error);
            alert('Ошибка доступа к микрофону. Проверьте разрешения для микрофона.');
        }
    }

    stopRecording() {
        this.isRecording = false;
        this.updateUI();
        this.recordingStatus.textContent = 'Запись не активна';
        document.body.classList.remove('recording');

        // Stop audio stream
        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        if (this.audioContext) {
            this.audioContext.close().then(() => {
                this.audioContext = null;
            });
        }

        console.log('Recording stopped');
    }

    sendAudioChunk(audioData) {
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            return;
        }

        try {
            // Convert Float32Array to Int16Array
            const int16Data = this.floatToInt16(audioData);

            // Convert to base64 for transmission
            const base64Data = this.arrayBufferToBase64(int16Data.buffer);

            // Send audio chunk via WebSocket
            this.websocket.send(JSON.stringify({
                type: 'audio_chunk',
                data: base64Data,
                user_id: this.userIdInput.value.trim(),
                timestamp: Date.now()
            }));

        } catch (error) {
            console.error('Error sending audio chunk:', error);
        }
    }

    floatToInt16(float32Array) {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            // Normalize float32 (-1 to 1) to int16 (-32768 to 32767)
            const sample = Math.max(-1, Math.min(1, float32Array[i]));
            int16Array[i] = sample < 0 ? sample * 32768 : sample * 32767;
        }
        return int16Array;
    }

    arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        for (let i = 0; i < bytes.byteLength; i++) {
            binary += String.fromCharCode(bytes[i]);
        }
        return btoa(binary);
    }

    handleWebSocketMessage(message) {
        console.log('Received message:', message);

        switch (message.type) {
            case 'new_text':
                this.displayNewText(message);
                break;

            case 'text_history':
                this.displayTextHistory(message.history);
                break;

            default:
                console.log('Unknown message type:', message.type);
        }
    }

    displayNewText(message) {
        this.addMessageToTranscript({
            user_id: message.user_id,
            text: message.text,
            timestamp: message.timestamp
        });
    }

    displayTextHistory(history) {
        // Clear current transcript
        this.transcriptContainer.innerHTML = '';

        if (!history || history.length === 0) {
            this.transcriptContainer.innerHTML = '<div class="empty-state">Транскрипция появится здесь...</div>';
            return;
        }

        // Add all messages from history
        history.forEach(message => {
            this.addMessageToTranscript(message);
        });

        this.scrollToBottom();
    }

    addMessageToTranscript(message) {
        // Remove empty state if present
        const emptyState = this.transcriptContainer.querySelector('.empty-state');
        if (emptyState) {
            emptyState.remove();
        }

        const messageElement = document.createElement('div');
        messageElement.className = 'message';

        const timestamp = new Date(message.timestamp).toLocaleTimeString();

        messageElement.innerHTML = `
            <div class="message-header">
                <span class="user-id">${this.escapeHtml(message.user_id)}</span>
                <span class="timestamp">${timestamp}</span>
            </div>
            <div class="message-text">${this.escapeHtml(message.text)}</div>
        `;

        this.transcriptContainer.appendChild(messageElement);
        this.scrollToBottom();
    }

    scrollToBottom() {
        this.transcriptContainer.scrollTop = this.transcriptContainer.scrollHeight;
    }

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    updateUI() {
        // Connection buttons
        this.connectBtn.disabled = this.isConnected;
        this.disconnectBtn.disabled = !this.isConnected;

        // Recording buttons
        this.startRecordingBtn.disabled = !this.isConnected || this.isRecording;
        this.stopRecordingBtn.disabled = !this.isConnected || !this.isRecording;
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new VoiceChatApp();
});