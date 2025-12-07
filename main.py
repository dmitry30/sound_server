from fastapi import FastAPI
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
from contextlib import asynccontextmanager
import uvicorn
import logging
import asyncio
import json
import base64
import numpy as np
from app2.asyncaudio import RealtimeAudioProcessor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Пример использования в вашем WebSocket обработчике
async def example_processing_callback(audio_data: np.ndarray, user_id: str,
                                      sample_rate: int, channels: int, timestamp: float):
    """
    Пример callback функции для обработки аудио.
    """
    # Здесь ваша логика обработки аудио
    # Например: распознавание речи, анализ, etc.
    logger.info(f"{audio_data}")
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.audio_processor = RealtimeAudioProcessor(
        sample_rate=16000,
        channels=1,
        processing_callback=example_processing_callback
    )

    # Запускаем фоновую обработку
    await app.state.audio_processor.start_processing()

    yield  # App runs here

    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title="Voice Chat with Subtitles",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app2/static", html=False), name="static")
templates = Jinja2Templates(directory="app2/templates")



@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/api/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    logger.info(f"WebSocket connected: room={room_id}")
    await websocket.accept()

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
                    await websocket.app.state.audio_processor.add_base64_audio(
                        message["data"],
                        user_id
                    )
                except Exception as e:
                    logger.error(f"Error processing audio chunk: {e}", exc_info=True)
                    continue
            elif message["type"] == "user_joined":
                user_id = message.get("user_id", "unknown")
                logger.info(f"User {user_id} joined room {room_id}")

            elif message["type"] == "user_left":
                user_id = message.get("user_id", "unknown")
                logger.info(f"User {user_id} left room {room_id}")

    except WebSocketDisconnect:
        logger.info(f"Client disconnected from room {room_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)



if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="localhost",
        port=8081,
        reload=True
    )