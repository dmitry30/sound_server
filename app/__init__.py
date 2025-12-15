import asyncio
import base64
import logging
import time
import traceback

import numpy as np

from app.postprocessor import PostProcessing
from app.preprocessor import BlockData, PreProcessor
from app.processor import Processor

logger = logging.getLogger(__name__)


class RealtimeAudioProcessor:
    def __init__(self):
        self.buffer_lock = asyncio.Lock()
        self.processor = Processor()
        self.pre_processor = PreProcessor()
        self.post_processor = PostProcessing()

    async def add_base64_audio(self, base64_data: str, user_id: str, room_id: str, connection_manager) -> None:
        try:
            audio_bytes = base64.b64decode(base64_data)
            await self.add_audio_data(audio_bytes, user_id, room_id, connection_manager)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Error decoding base64 audio: {e}")
            raise

    async def add_audio_data(self, audio_bytes: bytes, user_id: str, room_id: str, connection_manager) -> None:
        async for block in self.pre_processor(np.frombuffer(audio_bytes, dtype=np.int16)):
            asyncio.create_task(self._process_accumulated_data(block, user_id, room_id, connection_manager))

    async def _process_accumulated_data(self, block: BlockData, user_id: str, room_id: str, connection_manager) -> None:
        if await self.processor.process_audio(audio_data=block):
            
            curr_chunk = block.first_chunk
            text_list = []
            audio_list = []
            text = ''
            while curr_chunk:
                # logger.info(f"{curr_chunk.text} | ")
                if curr_chunk.text:
                    text_list.append(curr_chunk.text)
                    audio_list.append(curr_chunk.audio)
                    text += curr_chunk.text + ' '
                curr_chunk = curr_chunk.post_chunk
            logger.info(f"{text}")
            print(block.text)

            # TODO: АМИР это тебе
            structured_text_data, sentences, emotions = await self.post_processor.process(text, text_list, audio_list)
            logger.info(f"Результат: {structured_text_data}")
            logger.info("Эмоции по предложениям:")
            # logger.info(f"предложения: {sentences}")
            emote = []
            for emotion in emotions:
                logger.info(emotion)
                emote.append(emotion[0].get('label'))
            # тут должна быть broadcast

            if structured_text_data:
                message = {
                    "type": "new_text",
                    "text": structured_text_data.strip(),
                    "emote": emote,
                    "user_id": user_id,
                    "timestamp": time.time() * 1000
                }

                await connection_manager.broadcast_to_room(room_id, message)