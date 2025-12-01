import numpy as np
from typing import Optional
import random
import logging

logger = logging.getLogger(__name__)


class SpeechToTextModel:
    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self.is_loaded = True  # Всегда загружена для тестирования
        self.counter = 0

        # Список тестовых фраз
        self.test_phrases = [
            "Привет, как дела?",
            "Сегодня хорошая погода.",
            "Мне нравится этот проект.",
            "Что вы думаете об этом?",
            "Давайте обсудим идеи.",
            "Спасибо за помощь!",
            "До свидания.",
            "Повторите, пожалуйста.",
            "Я не понял вопрос.",
            "Отличная работа!"
        ]

    def transcribe(self, audio_data: np.ndarray) -> Optional[str]:
        """
        Простая заглушка для тестирования.
        Возвращает тестовые фразы по очереди.
        """
        try:
            if audio_data is None or len(audio_data) < 1000:
                logger.info("Audio too short for transcription")
                return None

            # Логируем информацию об аудио
            logger.info(f"Transcribing audio: shape={audio_data.shape}, mean={np.mean(audio_data):.6f}")

            # Простая проверка - если аудио почти тихое, возвращаем None
            energy = np.mean(np.square(audio_data))
            if energy < 0.001:
                logger.info("Audio energy too low, probably silence")
                return None

            # Берем следующую фразу из списка
            phrase_index = self.counter % len(self.test_phrases)
            transcription = self.test_phrases[phrase_index]

            self.counter += 1

            logger.info(f"Transcription result: {transcription}")
            return transcription

        except Exception as e:
            logger.error(f"Transcription error: {e}")
            return None