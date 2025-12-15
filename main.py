from fastapi import FastAPI
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import FileResponse, HTMLResponse
from fastapi import Request
from contextlib import asynccontextmanager
import uvicorn
import logging
import json
from app import RealtimeAudioProcessor

import mimetypes

mimetypes.init()
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')
mimetypes.add_type('image/svg+xml', '.svg')
mimetypes.add_type('application/wasm', '.wasm')
mimetypes.add_type('font/woff', '.woff')
mimetypes.add_type('font/woff2', '.woff2')


class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def broadcast_to_room(self, room_id: str, message: dict):
        """Отправить сообщение всем клиентам в комнате"""
        if room_id not in self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections[room_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error sending message: {e}")
                disconnected.append(connection)

        # Удалить отключенные соединения
        for connection in disconnected:
            self.disconnect(connection, room_id)

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Отправить сообщение конкретному клиенту"""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")




# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.audio_processor = RealtimeAudioProcessor()
    app.state.connection_manager = ConnectionManager()
    yield  # App runs here
    # Shutdown
    logger.info("Shutting down application...")


app = FastAPI(
    title="Voice Chat with Subtitles",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static", html=False), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/static/js/audio-processor.js")
async def get_audio_processor():
    return FileResponse(
        "static/js/audio-processor.js",
        media_type="application/javascript"
    )


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.websocket("/api/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    connection_manager = websocket.app.state.connection_manager
    await connection_manager.connect(websocket, room_id)
    logger.info(f"WebSocket connected: room={room_id}")
    #await websocket.accept()

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "audio_chunk":
                user_id = message.get("user_id", "unknown")
                try:
                    await websocket.app.state.audio_processor.add_base64_audio(
                        message["data"], 
                        user_id=user_id,
                        room_id=room_id,
                        connection_manager=connection_manager
                    )
                except Exception as e:
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