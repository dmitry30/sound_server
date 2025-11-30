import numpy as np
from typing import List
import logging

logger = logging.getLogger(__name__)


class VoiceActivityDetector:
    def __init__(self, threshold: float = 0.01, min_speech_duration: float = 0.2):
        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.speech_buffer = []
        self.silence_frames = 0
        self.min_speech_frames = int(min_speech_duration * 16000 / 1024)
        self.frame_count = 0

    def is_speech(self, audio_chunk: np.ndarray) -> bool:
        """
        Detect if audio chunk contains speech.
        Returns True if speech is detected.
        """
        try:
            # Validate input
            if audio_chunk is None or len(audio_chunk) == 0:
                return False

            # Ensure we have valid numerical data
            if np.any(np.isnan(audio_chunk)) or np.any(np.isinf(audio_chunk)):
                return False

            # Calculate energy of the audio chunk (with safe operations)
            audio_safe = np.clip(audio_chunk, -1.0, 1.0)
            energy = np.mean(audio_safe ** 2)

            # Simple energy-based VAD
            is_speech_frame = energy > self.threshold

            # Update speech buffer for duration-based decision
            if is_speech_frame:
                self.speech_buffer.append(True)
                self.silence_frames = 0
            else:
                self.silence_frames += 1
                if len(self.speech_buffer) > 0:
                    self.speech_buffer.append(False)

            # Keep buffer reasonable size
            if len(self.speech_buffer) > 100:
                self.speech_buffer = self.speech_buffer[-50:]

            # Only make decision after collecting enough frames
            self.frame_count += 1
            if self.frame_count < 5:  # Wait for initial frames
                return False

            # Decision based on recent speech activity
            if len(self.speech_buffer) >= self.min_speech_frames:
                speech_ratio = sum(self.speech_buffer) / len(self.speech_buffer)
                return speech_ratio > 0.4

            return False

        except Exception as e:
            logger.error(f"VAD error: {e}")
            return False

    def reset(self):
        """Reset VAD state"""
        self.speech_buffer = []
        self.silence_frames = 0
        self.frame_count = 0