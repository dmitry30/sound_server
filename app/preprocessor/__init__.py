from __future__ import annotations
import asyncio
import numpy as np
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class ChunkData:
    audio: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.int16))
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
        self.accumulation_buffer = np.array([])
        self.chunk_lock = asyncio.Lock()
        self.is_silent = True
        self.current_block = None
        self.current_chunk = None
        self.chunk_size = int(0.1 * 16000)
        self.silent_count = 0

    async def __call__(self, audio: np.ndarray):
        async with self.chunk_lock:
            i = self.accumulation_buffer.size // self.chunk_size * self.chunk_size
            self.accumulation_buffer = np.append(self.accumulation_buffer, audio)

            while i < self.accumulation_buffer.size - self.chunk_size:
                audio_chunk = self.accumulation_buffer[i:i + self.chunk_size]

                rms = np.sqrt(np.mean(np.square(audio_chunk.astype(np.float64))))
                # logger.info(f"{rms}")
                if rms > 500:
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
                        #self.current_chunk = ChunkData(pre_chunk=self.current_chunk)
                        #self.current_chunk.pre_chunk.post_chunk = self.current_chunk
                        yield self.current_block
                        self.current_block = None
                        self.current_chunk = None
                        self.accumulation_buffer = self.accumulation_buffer[i - self.silent_count * self.chunk_size:]
                        i = 0
                    self.silent_count += 1
                i += self.chunk_size

            if self.is_silent:
                self.accumulation_buffer = self.accumulation_buffer[i:]
            else:
                if self.silent_count == 0:
                    self.current_chunk.audio = self.accumulation_buffer[:i].copy()
                    self.current_chunk = ChunkData(pre_chunk=self.current_chunk)
                    self.current_chunk.pre_chunk.post_chunk = self.current_chunk
                    yield self.current_block
                    self.accumulation_buffer = self.accumulation_buffer[i:]
                else:
                    pass