from __future__ import annotations
import asyncio
import numpy as np
import logging
import webrtcvad
import noisereduce as nr
import librosa
from scipy import signal
import collections
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    audio: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int16))
    audio_proc: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    text: str = None
    full_text: str = ""
    pre_chunk: ChunkData = None
    post_chunk: ChunkData = None


@dataclass
class BlockData:
    first_chunk: ChunkData = None
    next_chunk: ChunkData = None
    text: str = ""
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class PreProcessor:
    def __init__(self):
        self.accumulation_buffer = np.array([], dtype=np.int16)
        self.accumulation_buffer_proc = np.array([], dtype=np.int16)
        self.chunk_lock = asyncio.Lock()
        self.is_silent = True
        self.current_block = None
        self.current_chunk = None
        self.chunk_size = int(0.1 * 16000)
        self.silent_count = 0

        # Параметры из второго кода
        self.sample_rate = 16000
        self.chunk_duration = 0.1
        self.vad_mode = 3
        self.noise_reduce = True
        self.denoise_level = 0.5
        self.high_pass_cutoff = 80

        # Инициализация VAD
        self.vad = webrtcvad.Vad(self.vad_mode)

        # Буферы для обработки
        self.audio_buffer = collections.deque(maxlen=10)
        self.noise_profile = None
        self.is_noise_profile_ready = False

        # Статистика для адаптивной обработки
        self.energy_threshold = None
        self.speech_history = []

        # Инициализация фильтров
        self._init_filters()

    def _init_filters(self):
        """Инициализация цифровых фильтров"""
        # ФВЧ фильтр для удаления низкочастотного шума
        nyquist = self.sample_rate / 2
        cutoff = self.high_pass_cutoff / nyquist
        self.b_highpass, self.a_highpass = signal.butter(
            4, cutoff, btype='high', analog=False
        )

        # Фильтр для сглаживания
        self.b_smooth, self.a_smooth = signal.butter(
            2, 100 / nyquist, btype='low', analog=False
        )
    def _high_pass_filter(self, audio_chunk):
        """Фильтр высоких частот"""
        return signal.filtfilt(self.b_highpass, self.a_highpass, audio_chunk)

    def _smooth_audio(self, audio_chunk):
        """Сглаживание аудиосигнала"""
        return signal.filtfilt(self.b_smooth, self.a_smooth, audio_chunk)

    def _normalize_audio(self, audio_chunk):
        """Нормализация аудиосигнала"""
        if np.max(np.abs(audio_chunk)) > 0:
            return audio_chunk / np.max(np.abs(audio_chunk))
        return audio_chunk

    def _calculate_energy(self, audio_chunk):
        """Расчет энергии сигнала"""
        return np.sum(audio_chunk.astype(np.float32) ** 2) / len(audio_chunk)

    def _calculate_spectral_centroid(self, audio_chunk):
        """Расчет спектрального центроида"""
        if len(audio_chunk) < 256:
            return 0

        spectrum = np.abs(np.fft.rfft(audio_chunk.astype(np.float32)))
        frequencies = np.fft.rfftfreq(len(audio_chunk), 1 / self.sample_rate)

        if np.sum(spectrum) > 0:
            return np.sum(frequencies * spectrum) / np.sum(spectrum)
        return 0

    def update_noise_profile(self, audio_chunk, is_noise=True):
        """
        Обновление профиля шума
        """
        if is_noise:
            chunk_float = self._normalize_audio(audio_chunk.copy().astype(np.float32) / 32768.0)

            if self.noise_profile is None:
                self.noise_profile = chunk_float
            else:
                # Экспоненциальное скользящее среднее
                alpha = 0.01
                self.noise_profile = alpha * chunk_float + (1 - alpha) * self.noise_profile

            self.is_noise_profile_ready = True

    def reduce_noise(self, audio_chunk):
        """Подавление шума"""
        if not self.noise_reduce or not self.is_noise_profile_ready:
            return audio_chunk

        try:
            # Подавление шума
            reduced_audio = nr.reduce_noise(
                y=audio_chunk,
                y_noise=self.noise_profile,
                sr=self.sample_rate,
                prop_decrease=self.denoise_level,
                stationary=True
            )

            return reduced_audio

        except Exception as e:
            logger.warning(f"Ошибка при подавлении шума: {e}")
            return audio_chunk

    def vad_detection(self, audio_chunk):
        """
        Детекция активности речи (VAD)
        """
        audio_chunk = (audio_chunk.copy() * 32768.0).astype(np.int16)
        try:
            # webrtcvad требует 16kHz, 16-bit, mono
            # if len(audio_chunk) != self.chunk_size:
            #     # Ресемплинг если необходимо
            #     if len(audio_chunk) != 160 * int(self.chunk_duration * 100):
            #         resampled = librosa.resample(
            #             audio_chunk.astype(np.float32) / 32768.0,
            #             orig_sr=self.sample_rate,
            #             target_sr=16000
            #         )
            #         audio_chunk = (resampled * 32768.0).astype(np.int16)

            # Конвертация в bytes для webrtcvad
            frames = np.array_split(audio_chunk, 5)
            # Проверяем каждый фрейм
            speech_frames = 0
            for frame in frames:
                # Конвертируем в bytes для webrtcvad
                audio_bytes = frame.astype(np.int16).tobytes()

                try:
                    if self.vad.is_speech(audio_bytes, self.sample_rate):
                        speech_frames += 1
                except Exception as e:
                    logger.debug(f"VAD frame error: {e}")
                    continue
            is_speech = speech_frames > 1
            # Дополнительная проверка по энергии
            energy = self._calculate_energy(audio_chunk)
            spectral_centroid = self._calculate_spectral_centroid(audio_chunk)

            # Адаптивный порог энергии
            if self.energy_threshold is None:
                self.energy_threshold = energy * 1.5

            # Обновление истории
            self.speech_history.append(is_speech)
            if len(self.speech_history) > 20:
                self.speech_history.pop(0)

            # Обновление порога
            if not is_speech:
                self.energy_threshold = 0.9 * self.energy_threshold + 0.1 * energy

            # Комбинированное решение
            energy_check = energy > self.energy_threshold * 1.2
            spectral_check = spectral_centroid > 500  # Речь обычно выше по частоте

            return is_speech #and (energy_check or spectral_check)

        except Exception as e:
            logger.warning(f"Ошибка в VAD: {e}")
            return False

    def process_audio_chunk(self, audio_chunk):
        """
        Полная обработка одного чанка
        """
        processed = audio_chunk.copy().astype(np.float32) / 32768.0

        # 1. Фильтр высоких частот
        processed = self._high_pass_filter(processed)

        # 2. Подавление шума
        if self.noise_reduce:
            processed = self.reduce_noise(processed)

        # 3. Сглаживание
        #processed = self._smooth_audio(processed)

        # 4. Нормализация
        #processed = self._normalize_audio(processed)

        # 5. Детекция речи
        is_speech = self.vad_detection(processed)

        # 6. Обновление профиля шума при отсутствии речи
        if not is_speech:
            self.update_noise_profile(audio_chunk, is_noise=True)

        return (processed * 32768.0).astype(np.int16), is_speech

    async def __call__(self, audio: np.ndarray):
        async with self.chunk_lock:
            i = self.accumulation_buffer.size // self.chunk_size * self.chunk_size
            self.accumulation_buffer = np.append(self.accumulation_buffer, audio)

            while i < self.accumulation_buffer.size - self.chunk_size:
                audio_chunk = self.accumulation_buffer[i:i + self.chunk_size]

                # Используем улучшенный детектор речи из второго кода
                processed_chunk, is_speech = self.process_audio_chunk(audio_chunk.copy())

                if not self.is_silent:
                    self.accumulation_buffer_proc = np.append(self.accumulation_buffer_proc, processed_chunk)

                if is_speech:
                    if self.is_silent:
                        logger.info(f"Start speak")
                        self.current_block = BlockData()
                        self.current_chunk = ChunkData()
                        self.current_block.first_chunk = self.current_chunk
                        self.current_block.next_chunk = self.current_chunk
                        self.is_silent = False
                        self.accumulation_buffer = self.accumulation_buffer[i:]
                        i = 0
                    self.silent_count = 0
                else:
                    if not self.is_silent and self.silent_count >= 10:
                        logger.info(f"Stop speak")
                        self.is_silent = True
                        self.current_chunk.audio = self.accumulation_buffer[:i].copy()
                        self.current_chunk.audio_proc = self.accumulation_buffer_proc
                        # self.current_chunk = ChunkData(pre_chunk=self.current_chunk)
                        # self.current_chunk.pre_chunk.post_chunk = self.current_chunk
                        yield self.current_block
                        self.current_block = None
                        self.current_chunk = None
                        self.accumulation_buffer = self.accumulation_buffer[i:]
                        self.accumulation_buffer_proc = np.array([], dtype=np.int16)
                        i = 0
                    self.silent_count += 1
                i += self.chunk_size

            if self.is_silent:
                self.accumulation_buffer = self.accumulation_buffer[i:]
            else:
                if self.silent_count == 0:
                    self.current_chunk.audio = self.accumulation_buffer[:i].copy()
                    self.current_chunk.audio_proc = self.accumulation_buffer_proc
                    self.current_chunk = ChunkData(pre_chunk=self.current_chunk)
                    self.current_chunk.pre_chunk.post_chunk = self.current_chunk
                    yield self.current_block
                    self.accumulation_buffer = self.accumulation_buffer[i:]
                    self.accumulation_buffer_proc = np.array([], dtype=np.int16)
                else:
                    pass