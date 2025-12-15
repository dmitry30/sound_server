class VoiceChatApp {
    constructor() {
        this.websocket = null;
        this.audioContext = null;
        this.isRecording = false;
        this.isConnected = false;
        this.audioStream = null;
        this.audioWorkletNode = null;
        this.isPlaying = false;
        this.audioMethodElement = document.createElement('span');
        this.audioMethodElement.id = 'audioMethod';
        this.audioMethodElement.textContent = 'AudioWorklet';

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

    async initializeAudio() {
        try {
            // Initialize audio context for playback
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000,
                latencyHint: 'interactive'
            });

            // Load audio worklet module
            await this.audioContext.audioWorklet.addModule('/static/js/audio-processor.js');

            // Create gain node for volume control
            this.gainNode = this.audioContext.createGain();
            this.gainNode.gain.value = 0.7;
            this.gainNode.connect(this.audioContext.destination);
            this.audioMethodElement.textContent = 'AudioWorklet';

        } catch (error) {
            console.error('Error initializing audio:', error);
            // Fallback to ScriptProcessorNode if AudioWorklet is not supported
            this.useAudioWorklet = false;
            this.audioMethodElement.textContent = 'ScriptProcessor (fallback)';
        }
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
            // Initialize audio if not already initialized
            if (!this.audioContext) {
                await this.initializeAudio();
            }

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

                // Send user joined message
                this.websocket.send(JSON.stringify({
                    type: 'user_joined',
                    user_id: userId,
                    room_id: roomId
                }));

                // Request history
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

                // Send user left message
                if (this.websocket) {
                    this.websocket.send(JSON.stringify({
                        type: 'user_left',
                        user_id: userId,
                        room_id: roomId
                    }));
                }
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
            const userId = this.userIdInput.value.trim();
            const roomId = this.roomIdInput.value.trim();

            // Send user left message
            this.websocket.send(JSON.stringify({
                type: 'user_left',
                user_id: userId,
                room_id: roomId
            }));

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
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false
                }
            });

            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }

            // Create media stream source
            const source = this.audioContext.createMediaStreamSource(this.audioStream);

            // Create AudioWorkletNode
            this.audioWorkletNode = new AudioWorkletNode(this.audioContext, 'audio-processor', {
                numberOfInputs: 1,
                numberOfOutputs: 1,
                outputChannelCount: [1]
            });

            // Handle audio data from worklet
            this.audioWorkletNode.port.onmessage = (event) => {
                if (event.data.type === 'audioData' && this.isConnected && this.websocket) {
                    const audioData = event.data.data;
                    this.sendAudioData(audioData);
                }
            };

            // Connect nodes
            source.connect(this.audioWorkletNode);
            this.audioWorkletNode.connect(this.audioContext.destination);

            this.isRecording = true;
            this.updateUI();
            this.recordingStatus.textContent = 'Запись активна';
            document.body.classList.add('recording');

            console.log('Recording started with AudioWorklet');

        } catch (error) {
            console.error('Error starting recording:', error);

            // Fallback to older API
            if (error.name === 'NotSupportedError' || error.name === 'TypeError') {
                console.log('AudioWorklet not supported, falling back to ScriptProcessorNode');
            } else {
                alert('Ошибка доступа к микрофону: ' + error.message);
            }
        }
    }

    sendAudioData(audioData) {
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            console.warn('WebSocket not ready');
            return;
        }

        try {
            const int16Data = this.floatToInt16(audioData);
            const base64Data = this.arrayBufferToBase64(int16Data.buffer);
            //this.playAudio(base64Data)
            console.log('Sending audio chunk:', {
                size: base64Data.length,
                audioSamples: audioData.length,
                timestamp: Date.now()
            });

            this.websocket.send(JSON.stringify({
                type: 'audio_chunk',
                data: base64Data,
                user_id: this.userIdInput.value.trim(),
                timestamp: Date.now()
            }));

        } catch (error) {
            console.error('Error sending audio data:', error);
        }
    }


    stopRecording() {
        if (this.audioWorkletNode) {
            this.audioWorkletNode.port.postMessage('flush');
            this.audioWorkletNode.disconnect();
            this.audioWorkletNode = null;
        }

        if (this.audioStream) {
            this.audioStream.getTracks().forEach(track => track.stop());
            this.audioStream = null;
        }

        this.isRecording = false;
        this.updateUI();
        this.recordingStatus.textContent = 'Запись не активна';
        document.body.classList.remove('recording');

        console.log('Recording stopped');
    }

    playAudio(base64Data) {
        if (!this.audioContext) {
            console.warn('Audio context not initialized');
            return;
        }

        if (this.audioContext.state === 'suspended') {
            this.audioContext.resume();
        }

        try {
            // Создаем новый источник для каждого фрагмента аудио
            const source = this.audioContext.createBufferSource();

            // Конвертируем base64 в ArrayBuffer
            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);

            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }

            // ВАЖНО: данные приходят в формате Int16, 16kHz, моно
            // Создаем AudioBuffer с правильными параметрами
            const buffer = this.audioContext.createBuffer(1, bytes.length / 2, 16000);

            // Конвертируем Int16 в Float32
            const channelData = buffer.getChannelData(0);
            const int16Array = new Int16Array(bytes.buffer);

            for (let i = 0; i < int16Array.length; i++) {
                channelData[i] = int16Array[i] / 32768.0;
            }

            source.buffer = buffer;
            source.connect(this.audioContext.destination);
            source.start(0);

            console.log('Playing audio chunk:', int16Array.length, 'samples');

            source.onended = () => {
                console.log('Audio playback finished');
            };

        } catch (error) {
            console.error('Error playing audio:', error);
        }
    }


    handleWebSocketMessage(message) {
        console.log('Received WebSocket message type:', message.type, 'data:', message);

        switch (message.type) {
            case 'audio_stream':
                console.log('Playing audio stream, data length:', message.data?.length);
                this.playAudio(message.data);
                break;

            case 'new_text':
                console.log('New text received:', message.text, 'from:', message.user_id);
                this.displayNewText(message);
                break;

            case 'text_history':
                console.log('Text history received:', message.history?.length, 'items');
                this.displayTextHistory(message.history);
                break;

            default:
                console.log('Unknown message type:', message.type, 'full message:', message);
        }
    }

    floatToInt16(float32Array) {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
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

    displayNewText(message) {
        this.addMessageToTranscript({
            user_id: message.user_id,
            text: message.text,
            emote: message.emote,
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

        // messageElement.innerHTML = `
        //     <div class="message-header">
        //         <span class="user-id">${this.escapeHtml(message.user_id)}</span>
        //         <span class="timestamp">${timestamp}</span>
        //     </div>
        //     <div class="message-text">${this.escapeHtml(message.text)}</div>
        // `;

        // this.transcriptContainer.appendChild(messageElement);
        // this.scrollToBottom();
         // Получаем первую эмоцию
        let firstEmote = '';
        if (message.emote && Array.isArray(message.emote) && message.emote.length > 0) {
            firstEmote = message.emote[0].toLowerCase();
        }

        // Создаем элементы отдельно для лучшего контроля
        const headerElement = document.createElement('div');
        headerElement.className = 'message-header';
        
        const userIdSpan = document.createElement('span');
        userIdSpan.className = 'user-id';
        userIdSpan.textContent = message.user_id;
        
        const timestampSpan = document.createElement('span');
        timestampSpan.className = 'timestamp';
        timestampSpan.textContent = timestamp;
        
        headerElement.appendChild(userIdSpan);
        headerElement.appendChild(timestampSpan);
        
        // Добавляем индикатор эмоции если есть
        if (firstEmote) {
            const emoteSpan = document.createElement('span');
            emoteSpan.className = 'emote-indicator';
            emoteSpan.textContent = message.emote[0];
            headerElement.appendChild(emoteSpan);
        }
        
        const textElement = document.createElement('div');
        textElement.className = 'message-text';
        textElement.textContent = message.text;
        
        // Применяем стиль в зависимости от эмоции
        if (firstEmote) {
            this.applyEmoteStyle(textElement, firstEmote);
        }
        
        messageElement.appendChild(headerElement);
        messageElement.appendChild(textElement);
        
        this.transcriptContainer.appendChild(messageElement);
        this.scrollToBottom();
    }

    applyEmoteStyle(element, emote) {
    // Словарь стилей для каждой эмоции
    const emoteStyles = {
        'hap': {
            color: '#2e7d32',
            backgroundColor: '#e8f5e9',
            borderLeft: '4px solid #2e7d32'
        },
        'sad': {
            color: '#1565c0',
            backgroundColor: '#e3f2fd',
            borderLeft: '4px solid #1565c0'
        },
        'ang': {
            color: '#c62828',
            backgroundColor: '#ffebee',
            borderLeft: '4px solid #c62828'
        },
        'neu': {
            color: '#616161',
            backgroundColor: '#f5f5f5',
            borderLeft: '4px solid #616161'
        }
    };
    
    const style = emoteStyles[emote];
    if (style) {
        Object.assign(element.style, style);
        element.style.padding = '8px';
        element.style.borderRadius = '4px';
        element.style.marginTop = '4px';
    }
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

        const statusContainer = document.querySelector('.status');
        if (statusContainer && !statusContainer.contains(this.audioMethodElement)) {
            statusContainer.appendChild(this.audioMethodElement);
        }
    }
}

// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new VoiceChatApp();
});

// showSystemMessage(text) {
//     const messageElement = document.createElement('div');
//     messageElement.className = 'message system-message';
//     messageElement.innerHTML = `
//         <div class="message-header">
//             <span class="system-label">Системное сообщение</span>
//         </div>
//         <div class="message-text">${this.escapeHtml(text)}</div>
//     `;
    
//     this.transcriptContainer.appendChild(messageElement);
//     this.scrollToBottom();
// }