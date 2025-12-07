import json
import numpy as np
from typing import Optional
import os
from pathlib import Path
import requests
import zipfile


class SpeechToTextModel:
    """
    Упрощенный потоковый STT на основе Vosk для русского языка.
    Принимает порционное аудио в формате numpy array.
    """

    # URL моделей Vosk для русского языка
    MODEL_URLS = {
        "small": "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip",
        "medium": "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip",
        "large": "https://alphacephei.com/vosk/models/vosk-model-ru-0.42.zip",
    }

    MODEL_NAMES = {
        "small": "vosk-model-small-ru-0.22",
        "medium": "vosk-model-ru-0.42",
        "large": "vosk-model-ru-0.42",
    }

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
            print("Ошибка: Vosk не установлен. Установите: pip install vosk")
            self.vosk_available = False
            self.is_loaded = False
            return

        # Загружаем модель
        if model_path is None:
            model_path = self._get_model_path(model_size)

        print(f"Загрузка модели Vosk: {model_path}")

        try:
            self.model = Model(model_path)
            self.recognizer = KaldiRecognizer(self.model, sample_rate)
            self.recognizer.SetWords(False)  # Отключаем вывод слов для простоты

            # Буфер для накопления аудио
            # self.audio_buffer = bytearray()

            self.is_loaded = True
            print(f"Модель '{model_size}' загружена успешно")

        except Exception as e:
            print(f"Ошибка загрузки модели: {e}")
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

        print(f"Скачивание модели {model_size}...")
        print(f"URL: {model_url}")

        try:
            # Скачиваем архив
            response = requests.get(model_url, stream=True)
            response.raise_for_status()

            zip_name = model_url.split("/")[-1]
            zip_path = models_dir / zip_name

            with open(zip_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Архив скачан: {zip_path}")

            # Распаковываем
            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                zip_ref.extractall(models_dir)

            # Удаляем архив
            os.remove(zip_path)

            model_path = models_dir / model_name
            print(f"Модель распакована: {model_path}")

            return str(model_path)

        except Exception as e:
            print(f"Ошибка скачивания модели: {e}")

            # Создаем директорию для fallback
            fallback_path = models_dir / "fallback"
            fallback_path.mkdir(exist_ok=True)

            # Создаем простой конфиг
            config = {"model": "fallback", "sample_rate": 16000}
            config_path = fallback_path / "conf.json"
            with open(config_path, "w") as f:
                json.dump(config, f)

            print(f"Создана fallback модель: {fallback_path}")
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

            # Добавляем в буфер
            # self.audio_buffer.extend(audio_bytes)

            # Пробуем распознать
            if self.recognizer.AcceptWaveform(audio_bytes):
                result = json.loads(self.recognizer.Result())
                text = result.get("text", "")

                if text:
                    self.recognizer.Reset()
                    print("full")
                    return text
            else:
                # Частичный результат
                partial = json.loads(self.recognizer.PartialResult())
                partial_text = partial.get("partial", "")
                if partial_text:
                    # Возвращаем частичный результат или None

                    do_reset and self.reset()
                    # print("partial")
                    return (
                        partial_text  # Раскомментируйте если нужны частичные результаты
                    )
                    pass

            return None

        except Exception as e:
            print(f"Ошибка транскрипции: {e}")
            return None

    def finalize(self) -> Optional[str]:
        """
        Завершение транскрипции и получение финального результата.
        Вызывается в конце аудиопотока.
        """
        # if not self.is_loaded or len(self.audio_buffer) == 0:
        #     return None
        if not self.is_loaded:
            print("Модель не загружена")
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
            print(f"Ошибка финализации: {e}")
            return None

    def reset(self):
        """Сброс состояния для новой сессии"""
        if self.is_loaded:
            self.recognizer.Reset()
            # self.audio_buffer.clear()
            print("Состояние модели сброшено")
