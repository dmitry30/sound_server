from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import base64
import numpy as np
import logging

from app.core.websocket_manager import manager
from app.audio.processor import AudioProcessor
from app.ml.speech_to_text import SpeechToTextModel
from app.processing.post_processor import PostProcessor
from app.processing.text_manager import TextManager

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize components
audio_processor = AudioProcessor()
stt_model = SpeechToTextModel()
post_processor = PostProcessor()
text_manager = TextManager()


@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)

    try:
        while True:
            # Receive audio data from client
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "audio_chunk":
                try:
                    # Decode base64 audio data
                    audio_bytes = base64.b64decode(message["data"])

                    # Process audio (Developer 1)
                    processed_audio = audio_processor.process_audio_chunk(audio_bytes)

                    if processed_audio is not None and len(processed_audio) > 1000:
                        # Convert to text (Developer 2)
                        raw_text = stt_model.transcribe(processed_audio)

                        if raw_text and raw_text.strip():
                            # Post-process text (Developer 3)
                            final_text = post_processor.process_text(raw_text)

                            if final_text and final_text.strip():
                                # Add to text history
                                text_entry = text_manager.add_text(
                                    user_id=message.get("user_id", "unknown"),
                                    text=final_text,
                                    room_id=room_id
                                )

                                # Broadcast to all clients in room
                                await manager.broadcast_to_room(
                                    {
                                        "type": "new_text",
                                        "user_id": text_entry["user_id"],
                                        "text": text_entry["text"],
                                        "timestamp": text_entry["timestamp"],
                                        "history": text_manager.get_recent_history(room_id)
                                    },
                                    room_id,
                                    exclude_websocket=websocket
                                )
                                logger.info(f"New text from {text_entry['user_id']}: {text_entry['text']}")

                except Exception as e:
                    logger.error(f"Error processing audio chunk: {e}")
                    continue

            elif message["type"] == "get_history":
                # Send current history to requesting client
                await manager.send_personal_message(
                    {
                        "type": "text_history",
                        "history": text_manager.get_recent_history(room_id)
                    },
                    websocket
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        logger.info(f"Client disconnected from room {room_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, room_id)