import asyncio
import traceback

import numpy as np
import logging
import base64
from app.preprocessor import BlockData, PreProcessor
from app.processor import Processor
# from app.postprocessor import PostProcessor

logger = logging.getLogger(__name__)


class RealtimeAudioProcessor:
    def __init__(self):
        self.buffer_lock = asyncio.Lock()
        self.processor = Processor()
        self.pre_processor = PreProcessor()
        # self.post_processor = PostProcessor()

    async def add_base64_audio(self, base64_data: str) -> None:
        try:
            audio_bytes = base64.b64decode(base64_data)
            await self.add_audio_data(audio_bytes)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error decoding base64 audio: {e}")
            raise

    async def add_audio_data(self, audio_bytes: bytes) -> None:
        async for block in self.pre_processor(np.frombuffer(audio_bytes, dtype=np.int16)):
            asyncio.create_task(self._process_accumulated_data(block))

    async def _process_accumulated_data(self, block: BlockData) -> None:
        if await self.processor.process_audio(audio_data=block):
            
            curr_chunk = block.first_chunk
            text = ""
            while curr_chunk:
                # logger.info(f"{curr_chunk.text} | ")
                text += curr_chunk.text + '|'
                curr_chunk = curr_chunk.post_chunk
            logger.info(f"{text}")
            print(block.text) 

            # TODO: АМИР это тебе
            # structured_text_data = await self.post_processing_callback(audio_data=block)

            # тут должна быть broadcast