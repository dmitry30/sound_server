import asyncio
import numpy as np
import time  # <-- Импортируем time
from typing import Dict, Optional
from queue import Queue
import threading
import logging

logger = logging.getLogger(__name__)


class STTProcessor:
    def __init__(self, main_event_loop: asyncio.AbstractEventLoop = None):
        from app.ml.speech_to_text import SpeechToTextModel
        from app.processing.post_processor import PostProcessor
        from app.processing.text_manager import TextManager

        self.stt_model = SpeechToTextModel()
        self.post_processor = PostProcessor()
        self.text_manager = TextManager()

        # Main event loop for async operations
        self.main_event_loop = main_event_loop or asyncio.get_event_loop()

        # Queue for audio processing
        self.audio_queue = Queue()

        # State for each user's audio buffer
        self.user_audio_buffers: Dict[str, list] = {}  # user_id -> list of audio chunks
        self.user_buffer_locks: Dict[str, threading.Lock] = {}

        # Processing thread
        self.processing_thread = None
        self.is_running = False

        # STT parameters
        self.min_audio_length = 16000  # 1 second at 16kHz
        self.silence_threshold = 0.0001  # Низкий порог для тестирования

        # Для отладки
        self.transcription_counter = 0

    def start(self):
        """Start STT processing thread"""
        self.is_running = True
        self.processing_thread = threading.Thread(target=self._processing_loop, daemon=True)
        self.processing_thread.start()
        logger.info("STT processing thread started")

    def stop(self):
        """Stop STT processing thread"""
        self.is_running = False
        if self.processing_thread:
            self.processing_thread.join(timeout=2)
            logger.info("STT processing thread stopped")

    def add_audio_for_processing(self, room_id: str, user_id: str, audio_data: bytes):
        """Add audio data to processing queue"""
        logger.info(f"Adding audio for processing: room={room_id}, user={user_id}, size={len(audio_data)}")
        self.audio_queue.put({
            'room_id': room_id,
            'user_id': user_id,
            'audio_data': audio_data,
            'timestamp': time.time()  # <-- Исправлено: time.time() вместо threading.time()
        })

    def _processing_loop(self):
        """Main processing loop running in separate thread"""
        logger.info("STT processing loop started")
        while self.is_running:
            try:
                # Get audio data from queue with timeout
                try:
                    item = self.audio_queue.get(timeout=0.1)
                except:
                    continue

                room_id = item['room_id']
                user_id = item['user_id']
                audio_data = item['audio_data']

                logger.info(f"Processing audio: user={user_id}, audio_size={len(audio_data)}")

                # Get or create buffer for user
                if user_id not in self.user_audio_buffers:
                    self.user_audio_buffers[user_id] = []
                    self.user_buffer_locks[user_id] = threading.Lock()

                with self.user_buffer_locks[user_id]:
                    # Add to user's buffer
                    self.user_audio_buffers[user_id].append(audio_data)

                    # Check if buffer is long enough for processing
                    total_length = sum(len(chunk) for chunk in self.user_audio_buffers[user_id])

                    logger.info(f"User buffer: {user_id}, total_length={total_length}")

                    if total_length >= self.min_audio_length:  # 1 second of audio
                        # Concatenate audio chunks
                        combined_audio = self._combine_audio_chunks(self.user_audio_buffers[user_id])

                        # Convert bytes to numpy
                        audio_array = self._bytes_to_audio(combined_audio)

                        if audio_array is not None:
                            # Check for speech activity
                            has_speech = self._has_speech(audio_array)
                            logger.info(f"Speech detected: {has_speech}, energy: {np.mean(np.square(audio_array)):.6f}")

                            if has_speech:
                                # Transcribe
                                raw_text = self.stt_model.transcribe(audio_array)
                                logger.info(f"Raw text: {raw_text}")

                                if raw_text and raw_text.strip():
                                    # Post-process
                                    final_text = self.post_processor.process_text(raw_text)
                                    logger.info(f"Final text: {final_text}")

                                    if final_text and final_text.strip():
                                        # Add to text history (thread-safe)
                                        text_entry = self.text_manager.add_text(
                                            user_id=user_id,
                                            text=final_text,
                                            room_id=room_id
                                        )

                                        logger.info(
                                            f"Broadcasting transcription #{self.transcription_counter}: {final_text}")
                                        self.transcription_counter += 1

                                        # Schedule broadcast in main thread
                                        self._schedule_broadcast(room_id, text_entry)

                        # Clear buffer after processing
                        self.user_audio_buffers[user_id] = []
                        logger.info(f"Cleared buffer for user: {user_id}")

                self.audio_queue.task_done()

            except Exception as e:
                logger.error(f"Error in STT processing loop: {e}", exc_info=True)
                continue

    def _schedule_broadcast(self, room_id: str, text_entry: dict):
        """Schedule broadcast in main event loop"""
        try:
            # Создаем future для выполнения в главном потоке
            future = asyncio.run_coroutine_threadsafe(
                self._broadcast_transcription(room_id, text_entry),
                self.main_event_loop
            )

            # Можно добавить обработку результата
            # result = future.result(timeout=5)

        except Exception as e:
            logger.error(f"Error scheduling broadcast: {e}", exc_info=True)

    async def _broadcast_transcription(self, room_id: str, text_entry: dict):
        """Broadcast transcription to room (called from main thread)"""
        try:
            from app.core.websocket_manager import manager

            logger.info(f"Starting broadcast to room {room_id}: {text_entry['text']}")

            # Получаем историю для комнаты
            history = self.text_manager.get_recent_history(room_id)

            # Создаем сообщение для отправки
            message = {
                "type": "new_text",
                "user_id": text_entry["user_id"],
                "text": text_entry["text"],
                "timestamp": text_entry["timestamp"],
                "history": history
            }

            logger.info(f"Sending message: {message}")

            # Отправляем всем в комнате
            await manager.broadcast_to_room(message, room_id)

            logger.info("Message broadcast successfully")

        except Exception as e:
            logger.error(f"Error broadcasting transcription: {e}", exc_info=True)

    def _combine_audio_chunks(self, chunks: list) -> bytes:
        """Combine multiple audio chunks"""
        return b''.join(chunks)

    def _bytes_to_audio(self, audio_bytes: bytes) -> Optional[np.ndarray]:
        """Convert bytes to numpy array"""
        try:
            # Convert Int16 bytes to float32 numpy array
            audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
            audio_float32 = audio_int16.astype(np.float32) / 32768.0
            return np.clip(audio_float32, -1.0, 1.0)
        except Exception as e:
            logger.error(f"Error converting bytes to audio: {e}")
            return None

    def _has_speech(self, audio_array: np.ndarray) -> bool:
        """Simple speech detection"""
        try:
            if len(audio_array) == 0:
                return False

            # Calculate energy
            energy = np.mean(np.square(audio_array))

            # Check if above threshold
            return energy > self.silence_threshold

        except Exception as e:
            logger.error(f"Error in speech detection: {e}")
            return False

    def cleanup_user_buffer(self, user_id: str):
        """Clean up buffer for user"""
        if user_id in self.user_audio_buffers:
            del self.user_audio_buffers[user_id]
        if user_id in self.user_buffer_locks:
            del self.user_buffer_locks[user_id]