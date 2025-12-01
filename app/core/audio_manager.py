import asyncio
import numpy as np
import time  # <-- Добавляем импорт time
import json
import base64
from typing import Dict, List, Tuple, Optional
from collections import deque
import logging

from app.core.websocket_manager import manager
from app.processing.text_manager import TextManager

logger = logging.getLogger(__name__)


class AudioManager:
    def __init__(self, sample_rate: int = 16000, max_buffer_size: int = 10):
        self.sample_rate = sample_rate
        self.max_buffer_size = max_buffer_size

        # Audio buffers per room per user
        self.audio_buffers: Dict[str, Dict[str, deque]] = {}  # room_id -> user_id -> deque of audio chunks

        # Text manager
        self.text_manager = TextManager()

        # Background task for audio mixing
        self.mixing_task = None
        self._mixing_loop_running = False

    async def start(self):
        """Start background tasks"""
        self._mixing_loop_running = True
        self.mixing_task = asyncio.create_task(self._audio_mixing_loop())
        logger.info("Audio mixing task started")

    async def stop(self):
        """Stop background tasks"""
        self._mixing_loop_running = False
        if self.mixing_task:
            self.mixing_task.cancel()
            try:
                await self.mixing_task
            except asyncio.CancelledError:
                pass
            logger.info("Audio mixing task stopped")

    async def add_audio_chunk(self, room_id: str, user_id: str, audio_data: bytes):
        """Add audio chunk from user to buffer"""
        if room_id not in self.audio_buffers:
            self.audio_buffers[room_id] = {}

        if user_id not in self.audio_buffers[room_id]:
            self.audio_buffers[room_id][user_id] = deque(maxlen=self.max_buffer_size)

        # Store raw bytes for mixing
        self.audio_buffers[room_id][user_id].append({
            'data': audio_data,
            'timestamp': time.time()  # <-- Исправлено: time.time() вместо asyncio.get_event_loop().time()
        })

    async def _audio_mixing_loop(self):
        """Background task for mixing and broadcasting audio"""
        while self._mixing_loop_running:
            try:
                # Mix audio for each room
                for room_id, user_buffers in list(self.audio_buffers.items()):
                    if not user_buffers:
                        continue

                    # Mix audio from all users
                    mixed_audio = await self._mix_audio_for_room(room_id)

                    if mixed_audio:
                        # Broadcast mixed audio to all users in room
                        await self._broadcast_mixed_audio(room_id, mixed_audio)

                await asyncio.sleep(0.05)  # 20Hz mixing rate

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in audio mixing loop: {e}")
                await asyncio.sleep(1)

    async def _mix_audio_for_room(self, room_id: str) -> Optional[bytes]:
        """Mix audio from all users in room"""
        user_buffers = self.audio_buffers.get(room_id, {})
        if not user_buffers:
            return None

        mixed_chunks = []

        for user_id, buffer in user_buffers.items():
            if buffer:
                # Get latest chunk
                chunk_data = buffer[-1]['data']

                # Convert bytes to numpy array
                audio_array = self._bytes_to_audio(chunk_data)
                if audio_array is not None:
                    mixed_chunks.append(audio_array)

        if not mixed_chunks:
            return None

        # Mix audio chunks (simple sum with normalization)
        mixed_audio = np.zeros_like(mixed_chunks[0])
        for chunk in mixed_chunks:
            if len(chunk) == len(mixed_audio):
                mixed_audio += chunk

        # Normalize to prevent clipping
        max_val = np.max(np.abs(mixed_audio))
        if max_val > 0:
            mixed_audio = mixed_audio / max_val * 0.7  # 70% volume

        # Convert back to bytes
        return self._audio_to_bytes(mixed_audio)

    async def _broadcast_mixed_audio(self, room_id: str, mixed_audio: bytes):
        """Broadcast mixed audio to all users in room"""
        base64_audio = base64.b64encode(mixed_audio).decode('utf-8')

        await manager.broadcast_to_room(
            {
                "type": "audio_stream",
                "data": base64_audio,
                "timestamp": time.time()  # <-- Исправлено
            },
            room_id
        )

    def _bytes_to_audio(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """Convert bytes to numpy array"""
        try:
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_array_float = audio_array.astype(np.float32) / 32768.0
            return np.clip(audio_array_float, -1.0, 1.0)
        except Exception as e:
            logger.error(f"Error converting bytes to audio: {e}")
            return None

    def _audio_to_bytes(self, audio_array: np.ndarray) -> bytes:
        """Convert numpy array to bytes"""
        try:
            # Convert float32 to int16
            audio_int16 = (audio_array * 32767).astype(np.int16)
            return audio_int16.tobytes()
        except Exception as e:
            logger.error(f"Error converting audio to bytes: {e}")
            return b''

    def cleanup_room(self, room_id: str):
        """Clean up audio buffers for room"""
        if room_id in self.audio_buffers:
            del self.audio_buffers[room_id]


# Global audio manager instance
audio_manager = AudioManager()