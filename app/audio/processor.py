import numpy as np
import json
from typing import Optional, Tuple
import logging

from app.audio.vad import VoiceActivityDetector

logger = logging.getLogger(__name__)


class AudioProcessor:
    def __init__(self, sample_rate: int = 16000, chunk_size: int = 1024):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.vad = VoiceActivityDetector()

        # Buffer for accumulating audio chunks
        self.audio_buffer = []
        self.buffer_max_size = sample_rate * 2  # 2 seconds

    def process_audio_chunk(self, audio_data: bytes) -> Optional[np.ndarray]:
        """
        Process incoming audio chunk:
        1. Convert bytes to numpy array
        2. Apply preprocessing
        3. Voice activity detection
        4. Return only speech segments
        """
        try:
            # Convert bytes to numpy array
            audio_array = self._bytes_to_audio(audio_data)

            # Validate audio data
            if audio_array is None or len(audio_array) == 0:
                return None

            # Check for invalid values
            if np.any(np.isnan(audio_array)) or np.any(np.isinf(audio_array)):
                logger.warning("Invalid audio data detected: NaN or Inf values")
                return None

            # Apply preprocessing
            processed_audio = self._preprocess_audio(audio_array)

            if processed_audio is None:
                return None

            # Voice activity detection
            if self.vad.is_speech(processed_audio):
                # Add to buffer
                self.audio_buffer.extend(processed_audio.tolist())

                # Keep buffer within limits
                if len(self.audio_buffer) > self.buffer_max_size:
                    self.audio_buffer = self.audio_buffer[-self.buffer_max_size:]

                # Return processed audio for transcription
                return np.array(self.audio_buffer, dtype=np.float32)
            else:
                # Clear buffer if no speech detected for a while
                if len(self.audio_buffer) > self.sample_rate:  # If we have more than 1 second of audio
                    self.audio_buffer = []
                return None

        except Exception as e:
            logger.error(f"Audio processing error: {e}")
            return None

    def _bytes_to_audio(self, audio_data: bytes) -> Optional[np.ndarray]:
        """
        Convert bytes to numpy array of audio samples.
        Handle both Int16 and Float32 formats.
        """
        try:
            # Try to decode as Int16 first (from JavaScript)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)

            # Convert Int16 to Float32 (-32768 to 32767 -> -1.0 to 1.0)
            audio_array_float = audio_array.astype(np.float32) / 32768.0

            # Clip values to safe range
            audio_array_float = np.clip(audio_array_float, -1.0, 1.0)

            return audio_array_float

        except Exception as e:
            logger.error(f"Error converting audio bytes: {e}")
            return None

    def _preprocess_audio(self, audio_array: np.ndarray) -> Optional[np.ndarray]:
        """
        Apply audio preprocessing:
        - Normalization
        - Noise reduction
        - Resampling if needed
        """
        try:
            # Ensure we have valid data
            if len(audio_array) == 0:
                return None

            # Remove any remaining NaN or Inf values
            audio_array = np.nan_to_num(audio_array, nan=0.0, posinf=0.0, neginf=0.0)

            # Normalize audio to prevent overflow
            max_val = np.max(np.abs(audio_array))
            if max_val > 0:
                audio_array = audio_array / max_val
            else:
                # Silent audio, no need to process
                return None

            # Simple high-pass filter to remove DC offset
            audio_array = self._high_pass_filter(audio_array)

            return audio_array

        except Exception as e:
            logger.error(f"Audio preprocessing error: {e}")
            return None

    def _high_pass_filter(self, audio_array: np.ndarray, cutoff: float = 80.0) -> np.ndarray:
        """
        Simple first-order high-pass filter to remove DC offset.
        """
        if len(audio_array) < 2:
            return audio_array

        alpha = 0.95  # Filter coefficient
        filtered = np.zeros_like(audio_array)
        filtered[0] = audio_array[0]

        for i in range(1, len(audio_array)):
            filtered[i] = alpha * (filtered[i - 1] + audio_array[i] - audio_array[i - 1])

        return filtered

    def reset_buffer(self):
        """Clear the audio buffer"""
        self.audio_buffer = []