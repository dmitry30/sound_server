from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import base64
import logging

from app.core.websocket_manager import manager
from app.core.audio_manager import audio_manager

logger = logging.getLogger(__name__)

router = APIRouter()


# Будем получать stt_processor через app.state при каждом запросе

@router.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)
    user_id = None

    logger.info(f"WebSocket connected: room={room_id}")

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
                    # Decode base64 audio data
                    audio_bytes = base64.b64decode(message["data"])
                    logger.info(f"Decoded audio bytes: {len(audio_bytes)} bytes")

                    # Получаем app из websocket
                    app = websocket.app

                    # Add to audio manager for mixing
                    await audio_manager.add_audio_chunk(room_id, user_id, audio_bytes)

                    # Add to STT processing queue
                    if hasattr(app.state, 'stt_processor') and app.state.stt_processor:
                        stt_processor = app.state.stt_processor
                        stt_processor.add_audio_for_processing(room_id, user_id, audio_bytes)
                        logger.info("Audio added to processing queue")
                    else:
                        logger.error("STT processor not initialized in app.state")

                except Exception as e:
                    logger.error(f"Error processing audio chunk: {e}", exc_info=True)
                    continue

            elif message["type"] == "get_history":
                logger.info("History requested")
                # Send current history to requesting client
                app = websocket.app
                if hasattr(app.state, 'stt_processor') and app.state.stt_processor:
                    stt_processor = app.state.stt_processor
                    history = stt_processor.text_manager.get_recent_history(room_id)
                    logger.info(f"Sending history: {len(history)} items")

                    await manager.send_personal_message(
                        {
                            "type": "text_history",
                            "history": history
                        },
                        websocket
                    )
                else:
                    logger.error("STT processor not initialized")
                    await manager.send_personal_message(
                        {
                            "type": "text_history",
                            "history": []
                        },
                        websocket
                    )

            elif message["type"] == "user_joined":
                user_id = message.get("user_id", "unknown")
                logger.info(f"User {user_id} joined room {room_id}")

            elif message["type"] == "user_left":
                user_id = message.get("user_id", "unknown")
                logger.info(f"User {user_id} left room {room_id}")

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from room {room_id}")
        app = websocket.app
        if hasattr(app.state, 'stt_processor') and app.state.stt_processor and user_id:
            stt_processor = app.state.stt_processor
            stt_processor.cleanup_user_buffer(user_id)
        manager.disconnect(websocket, room_id)

    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
        app = websocket.app
        if hasattr(app.state, 'stt_processor') and app.state.stt_processor and user_id:
            stt_processor = app.state.stt_processor
            stt_processor.cleanup_user_buffer(user_id)
        manager.disconnect(websocket, room_id)