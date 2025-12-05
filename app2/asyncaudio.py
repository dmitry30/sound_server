import asyncio
import audioop

import numpy as np
import logging
from collections import deque
from typing import Optional, Callable, Any, List
import json
import base64

logger = logging.getLogger(__name__)


class RealtimeAudioProcessor:
    """
    Класс для асинхронной обработки аудиосигнала в реальном времени.

    Параметры:
        sample_rate (int): Частота дискретизации аудио (Гц)
        channels (int): Количество каналов (1 - моно, 2 - стерео)
        chunk_duration (float): Длительность одного чанка в секундах
        buffer_duration (float): Максимальная длительность буфера в секундах
        processing_callback: Асинхронная функция для обработки аудиоданных
    """

    def __init__(
            self,
            sample_rate: int = 16000,
            channels: int = 1,
            chunk_duration: float = 0.1,  # 100 ms
            buffer_duration: float = 10.0,  # 10 seconds
            processing_callback: Optional[Callable] = None
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_duration = chunk_duration
        self.buffer_duration = buffer_duration

        # Размер чанка в сэмплах
        self.chunk_size = int(sample_rate * chunk_duration * channels)

        # Блокировка для безопасного доступа к буферу
        self.buffer_lock = asyncio.Lock()

        # Флаг работы обработчика
        self.is_processing = False

        # Задача обработки
        self.processing_task: Optional[asyncio.Task] = None

        # Callback функция для обработки
        self.processing_callback = processing_callback

        # Очередь для накопленных чанков перед обработкой
        self.accumulation_buffer = np.array([])
        self.accumulation_size = 0

        self.is_silent = True
        self.silent_count = 0

        # Метрики
        self.total_samples_processed = 0
        self.total_chunks_processed = 0

    async def add_audio_data(self, audio_bytes: bytes, user_id: str = "unknown") -> None:
        try:
            # Конвертируем байты в numpy array (пример для int16)
            # Здесь нужно использовать правильный формат данных
            audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

            async with self.buffer_lock:
                i = self.accumulation_buffer.size // self.chunk_size * self.chunk_size
                self.accumulation_buffer = np.append(self.accumulation_buffer, audio_array)

                while i < self.accumulation_buffer.size - self.chunk_size:
                    audio_chunk = self.accumulation_buffer[i:i+self.chunk_size]

                    rms = np.sqrt(np.mean(np.square(audio_chunk.astype(np.float64))))
                    # logger.info(f"{rms}")
                    if rms > 500:
                        if self.is_silent:
                            logger.info("Start speak")
                            self.is_silent = False
                            self.accumulation_buffer = self.accumulation_buffer[i:]
                            i = 0
                        self.silent_count = 0
                    else:
                        # logger.info(f"{self.accumulation_buffer}")
                        if not self.is_silent and self.silent_count >= 10:
                            logger.info("Stop speak")
                            self.is_silent = True
                            data_to_process = self.accumulation_buffer[:i-self.silent_count*self.chunk_size].copy()
                            #logger.info(f"{self.accumulation_buffer[:i-self.silent_count*self.chunk_size]}")
                            asyncio.create_task(self._process_accumulated_data(data_to_process))
                            self.accumulation_buffer = self.accumulation_buffer[i-self.silent_count*self.chunk_size:]
                            i = 0
                        self.silent_count += 1
                    i += self.chunk_size
                if self.is_silent:
                    self.accumulation_buffer = self.accumulation_buffer[i:]



                # Также добавляем в буфер накопления для порционной обработки
                # self.accumulation_buffer.extend(audio_array)
                # self.accumulation_size += len(audio_array)
                # logger.info(str((self.accumulation_size, self.chunk_size)))
                # asyncio.create_task(self._trigger_processing())

            #logger.debug(f"Added {len(audio_array)} samples from user {user_id}")

        except Exception as e:
            logger.error(f"Error adding audio data: {e}", exc_info=True)
            raise

    async def add_base64_audio(self, base64_data: str, user_id: str = "unknown") -> None:
        """
        Добавляет аудиоданные из base64 строки.
        """
        try:
            audio_bytes = base64.b64decode(base64_data)
            await self.add_audio_data(audio_bytes, user_id)
        except Exception as e:
            logger.error(f"Error decoding base64 audio: {e}")
            raise

    async def _trigger_processing(self) -> None:
        logger.info("trigger")
        return
        """Триггерит обработку накопленных данных."""
        if not self.accumulation_buffer or self.processing_callback is None:
            return

        # Копируем данные для обработки
        async with self.buffer_lock:
            if not self.accumulation_buffer or self.processing_callback is None:
                return
            data_to_process = self.accumulation_buffer.copy()
            self.accumulation_buffer.clear()
            self.accumulation_size = 0

        # Запускаем обработку в фоне
        asyncio.create_task(self._process_accumulated_data(data_to_process))

    async def _process_accumulated_data(self, data_chunks) -> None:
        logger.info("process accumulated data")
        """
        Обрабатывает накопленные аудиоданные.
        """
        try:
            # Объединяем все чанки
            all_data = data_chunks
            #logger.info(f"{data_chunks}")

            # Вызываем callback функцию
            if self.processing_callback:
                result = await self.processing_callback(
                    audio_data=all_data,
                    user_id=0,
                    sample_rate=self.sample_rate,
                    channels=self.channels,
                    timestamp=asyncio.get_event_loop().time()
                )

                self.total_samples_processed += len(all_data)
                self.total_chunks_processed += 1

                logger.debug(f"Processed {len(all_data)} samples, total: {self.total_samples_processed}")

                return result

        except Exception as e:
            logger.error(f"Error processing accumulated data: {e}", exc_info=True)

    async def start_processing(self, interval: float = 0.1) -> None:
        """
        Запускает фоновую задачу периодической обработки.

        Параметры:
            interval: Интервал обработки в секундах
        """
        if self.is_processing:
            logger.warning("Processing is already running")
            return

        self.is_processing = True
        self.processing_task = asyncio.create_task(self._processing_loop(interval))
        logger.info("Audio processing started")

    async def _processing_loop(self, interval: float) -> None:
        """Основной цикл обработки."""
        while self.is_processing:
            try:
                await asyncio.sleep(interval)

                # Проверяем, есть ли данные для обработки
                if self.accumulation_size > 0:
                    await self._trigger_processing()

                ## Также можно добавить периодическую обработку всего буфера
                #await self._process_full_buffer_if_needed()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in processing loop: {e}", exc_info=True)

    async def clear_buffer(self) -> None:
        """Очищает буфер."""
        async with self.buffer_lock:
            self.audio_buffer.clear()
            self.accumulation_buffer.clear()
            self.accumulation_size = 0
        logger.info("Audio buffer cleared")

    async def stop_processing(self) -> None:
        """Останавливает обработку."""
        self.is_processing = False

        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
            self.processing_task = None

        logger.info("Audio processing stopped")

    async def __aenter__(self):
        """Поддержка контекстного менеджера."""
        await self.start_processing()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Поддержка контекстного менеджера."""
        await self.stop_processing()


# Пример использования в вашем WebSocket обработчике
async def example_processing_callback(audio_data: np.ndarray, user_id: str,
                                      sample_rate: int, channels: int, timestamp: float):
    """
    Пример callback функции для обработки аудио.
    """
    # Здесь ваша логика обработки аудио
    # Например: распознавание речи, анализ, etc.

    # Простой пример: вычисление RMS уровня
    rms = np.sqrt(np.mean(audio_data.astype(np.float32) ** 2))

    logger.info(f"Processing audio from {user_id}: {len(audio_data)} samples, RMS: {rms:.4f}")

    # Возвращаем результат обработки
    return {
        'user_id': user_id,
        'samples_processed': len(audio_data),
        'rms_level': rms,
        'timestamp': timestamp
    }


# Интеграция с вашим существующим кодом
async def handle_websocket_connection(websocket):
    """
    Пример обработки WebSocket соединения с использованием класса.
    """
    # Создаем процессор
    audio_processor = RealtimeAudioProcessor(
        sample_rate=16000,
        channels=1,
        processing_callback=example_processing_callback
    )

    # Запускаем фоновую обработку
    await audio_processor.start_processing()

    try:
        while True:
            # Receive data from client
            data = await websocket.receive_text()
            message = json.loads(data)

            logger.info(f"Received WebSocket message type: {message.get('type')}")

            if message["type"] == "audio_chunk":
                user_id = message.get("user_id", "unknown")
                logger.info(f"Audio chunk from user {user_id}, data length: {len(message.get('data', ''))}")

                try:
                    # Используем процессор для добавления данных
                    await audio_processor.add_base64_audio(
                        message["data"],
                        user_id
                    )

                    # Можно также получить статистику
                    stats = await audio_processor.get_stats()
                    logger.debug(f"Processor stats: {stats}")

                except Exception as e:
                    logger.error(f"Error processing audio chunk: {e}", exc_info=True)
                    continue

    finally:
        # Останавливаем обработку при закрытии соединения
        await audio_processor.stop_processing()


# Альтернативная версия с контекстным менеджером
async def handle_websocket_connection_v2(websocket):
    """
    Пример с использованием контекстного менеджера.
    """
    async with RealtimeAudioProcessor(
            sample_rate=16000,
            channels=1,
            processing_callback=example_processing_callback
    ) as audio_processor:

        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "audio_chunk":
                user_id = message.get("user_id", "unknown")

                try:
                    audio_bytes = base64.b64decode(message["data"])

                    # Добавляем сырые байты
                    await audio_processor.add_audio_data(audio_bytes, user_id)

                except Exception as e:
                    logger.error(f"Error processing audio chunk: {e}", exc_info=True)
                    continue