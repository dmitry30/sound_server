// Audio processor worklet
class AudioProcessorWorklet extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
        this.bufferSize = 4096;
        this.port.onmessage = (event) => {
            if (event.data === 'flush') {
                this.flushBuffer();
            }
        };
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input.length > 0) {
            const channelData = input[0];
            this.buffer.push(...channelData);

            // Send buffer when it's full
            if (this.buffer.length >= this.bufferSize) {
                this.sendBuffer();
            }
        }

        return true;
    }

    sendBuffer() {
        const bufferToSend = this.buffer.slice(0, this.bufferSize);
        this.buffer = this.buffer.slice(this.bufferSize);

        this.port.postMessage({
            type: 'audioData',
            data: bufferToSend
        });
    }

    flushBuffer() {
        if (this.buffer.length > 0) {
            this.port.postMessage({
                type: 'audioData',
                data: this.buffer
            });
            this.buffer = [];
        }
    }
}

registerProcessor('audio-processor', AudioProcessorWorklet);