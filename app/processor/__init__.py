import asyncio
import json
import logging
import numpy as np
from typing import Optional
import os
from pathlib import Path
import requests
import zipfile

from app.preprocessor import BlockData, ChunkData


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SpeechToTextModel:
    # URL моделей Vosk для русского языка
    MODEL_URLS = {
        "small": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
        "medium": "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip",
    }
    MODEL_NAMES = {"small": "vosk-model-small-ru-0.22", "medium": "vosk-model-ru-0.42"}

    def __init__(
        self,
        model_size: str = "small",
        model_path: Optional[str] = None,
        sample_rate: int = 16000,
    ):
        """
        Инициализация модели распознавания речи.

        Args:
            model_size: Размер модели ("small", "medium", "large")
            model_path: Путь к локальной модели (если None - скачает автоматически)
            sample_rate: Частота дискретизации аудио (по умолчанию 16000)
        """
        self.sample_rate = sample_rate

        # Проверяем доступность Vosk
        try:
            from vosk import Model, KaldiRecognizer

            self.vosk_available = True
        except ImportError:
            logger.error("Ошибка: Vosk не установлен. Установите: pip install vosk")
            self.vosk_available = False
            self.is_loaded = False
            return

        # Загружаем модель
        if model_path is None:
            model_path = self._get_model_path(model_size)

        logger.info(f"Загрузка модели Vosk: {model_path}")

        try:
            self.model = Model(model_path)
            self.recognizer = KaldiRecognizer(self.model, sample_rate)
            self.recognizer.SetWords(False)  # Отключаем вывод слов для простоты

            self.is_loaded = True
            logger.info(f"Модель '{model_size}' загружена успешно")

        except Exception as e:
            logger.error(f"Ошибка загрузки модели: {e}")
            self.is_loaded = False

    def _get_model_path(self, model_size: str) -> str:
        """Получение пути к модели, скачивание если нужно"""
        models_dir = Path("vosk_models")
        models_dir.mkdir(exist_ok=True)

        model_name = self.MODEL_NAMES.get(model_size, "small")
        model_path = models_dir / model_name

        # Если модель уже существует
        if model_path.exists():
            return str(model_path)

        # Скачиваем модель
        return self._download_model(model_size)

    def _download_model(self, model_size: str) -> str:
        """Скачивание модели Vosk"""
        models_dir = Path("vosk_models")
        model_url = self.MODEL_URLS.get(model_size, self.MODEL_URLS["small"])
        model_name = self.MODEL_NAMES.get(model_size, "vosk-model-small-ru-0.22")

        logger.info(f"Скачивание модели {model_size}...")
        logger.info(f"URL: {model_url}")

        try:
            # Скачиваем архив
            response = requests.get(model_url, stream=True)
            response.raise_for_status()

            zip_name = model_url.split("/")[-1]
            zip_path = models_dir / zip_name

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Архив скачан: {zip_path}")

            # Распаковываем
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(models_dir)

            # Удаляем архив
            os.remove(zip_path)

            model_path = models_dir / model_name
            logger.info(f"Модель распакована: {model_path}")

            return str(model_path)

        except Exception as e:
            logger.error(f"Ошибка скачивания модели: {e}")

            # Создаем директорию для fallback
            fallback_path = models_dir / "fallback"
            fallback_path.mkdir(exist_ok=True)

            # Создаем простой конфиг
            config = {"model": "fallback", "sample_rate": 16000}
            config_path = fallback_path / "conf.json"
            with open(config_path, "w") as f:
                json.dump(config, f)

            logger.warning(f"Создана fallback модель: {fallback_path}")
            return str(fallback_path)

    def transcribe(
        self, audio_data: np.ndarray, do_reset: bool = False
    ) -> Optional[str]:
        """
        Транскрибирование порции аудио.

        Args:
            audio_data: Аудиоданные как numpy array

        Returns:
            Распознанный текст или None
        """
        if not self.is_loaded or audio_data is None or len(audio_data) == 0:
            print("Модель не загружена")
            return None

        try:
            # Конвертируем numpy array в байты (16-bit PCM)
            audio_int16 = (audio_data * 32767).astype(np.int16)
            audio_bytes = audio_int16.tobytes()

            # Пробуем распознать
            if self.recognizer.AcceptWaveform(audio_bytes):
                result = json.loads(self.recognizer.Result())
                text = result.get("text", "")

                if text:
                    return text, True
            else:
                # Частичный результат
                partial = json.loads(self.recognizer.PartialResult())
                partial_text = partial.get("partial", "")
                if partial_text:
                    # Возвращаем частичный результат или None

                    do_reset and self.reset()
                    return partial_text, do_reset

            return "", False

        except Exception as e:
            logger.error(f"Ошибка транскрипции: {e}")
            return None

    def finalize(self) -> Optional[str]:
        """
        Завершение транскрипции и получение финального результата.
        Вызывается в конце аудиопотока.
        """
        # if not self.is_loaded or len(self.audio_buffer) == 0:
        #     return None
        if not self.is_loaded:
            logger.error("Модель не загружена")
            return None

        try:
            # Принудительно завершаем распознавание
            result = json.loads(self.recognizer.FinalResult())
            text = result.get("text", "")

            # Сбрасываем состояние для новой сессии
            self.recognizer.Reset()
            # self.audio_buffer.clear()

            return text if text else None

        except Exception as e:
            logger.error(f"Ошибка финализации: {e}")
            return None

    def reset(self):
        """Сброс состояния для новой сессии"""
        if self.is_loaded:
            self.recognizer.Reset()
            # self.audio_buffer.clear()
            logger.info("Состояние модели сброшено")


class Processor:
    def __init__(self, model_size: str = "small"):
        """
        Инициализация процессора с моделью распознавания речи.

        Args:
            model_size: Размер модели Vosk ("small", "medium")
        """
        self.speech_to_text = SpeechToTextModel(model_size=model_size)

    async def process_audio(self, audio_data: BlockData) -> Optional[bool]:
        async with audio_data.lock:
            # logger.info("processing_audio")
            curr_chunk: ChunkData = audio_data.next_chunk

            predicted_text, is_full = self.speech_to_text.transcribe(
                curr_chunk.audio.astype(np.float32) / 32768.8, do_reset=curr_chunk.post_chunk is None
            )
            # logger.info(f"♪♪♪ {predicted_text}")
            # if predicted_text is not None:
            #     if (prev:=curr_chunk.pre_chunk) is not None:
            #         if isinstance(prev.text, str):
            #             logger.info("ОБРЕЗАНО")
            #             logger.info(f"♀♀♀prev:{prev.text}")
            #             predicted_text = predicted_text.replace(prev.text, "").strip()
            curr_chunk.full_text = predicted_text
            if is_full:
                curr_text = predicted_text
                chunk = curr_chunk
                while chunk.pre_chunk and not chunk.pre_chunk.text:
                    prev_text = chunk.pre_chunk.full_text
                    prev_text_sp = prev_text.split(" ")
                    curr_text_sp = curr_text.split(" ")
            
                    i = 0
                    while i < min(len(prev_text_sp), len(curr_text_sp)) and prev_text_sp[i] == curr_text_sp[i]:
                        i += 1

                    curr_text = ' '.join(curr_text_sp[:i])
                    chunk.text = ' ' + ' '.join(curr_text_sp[i:])

                    chunk = chunk.pre_chunk
                chunk.text = curr_text
            
            # logger.info(f"▲▲▲{curr_chunk.text}")
            if curr_chunk.post_chunk is None:
                return True
            else:
                audio_data.next_chunk = curr_chunk.post_chunk

    async def reset_processor(self):
        """Сброс состояния процессора"""
        async with self.processing_lock:
            self.speech_to_text.reset()
