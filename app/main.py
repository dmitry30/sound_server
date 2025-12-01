from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from fastapi import Request
from contextlib import asynccontextmanager
import uvicorn
import logging
import asyncio

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализируем глобальные переменные заранее
stt_processor = None
audio_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    global stt_processor, audio_manager

    # Startup
    logger.info("Starting application...")

    # Инициализируем сервисы
    from app.core.stt_processor import STTProcessor
    from app.core.audio_manager import AudioManager

    # Получаем главный event loop
    main_event_loop = asyncio.get_event_loop()

    # Инициализируем STT процессор
    stt_processor = STTProcessor(main_event_loop=main_event_loop)

    # Инициализируем audio manager
    audio_manager = AudioManager()

    # Устанавливаем глобальную ссылку на приложение в routes
    #from app.api.routes import set_app
    #set_app(app)

    # Start audio mixing
    await audio_manager.start()

    # Start STT processing thread
    stt_processor.start()

    # Сохраняем в app.state для доступа из других модулей
    app.state.stt_processor = stt_processor
    app.state.audio_manager = audio_manager

    logger.info("Background services started")

    yield  # App runs here

    # Shutdown
    logger.info("Shutting down application...")

    # Stop audio mixing
    await audio_manager.stop()

    # Stop STT processing thread
    if stt_processor:
        stt_processor.stop()

    logger.info("Background services stopped")


app = FastAPI(
    title="Voice Chat with Subtitles",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Include API routes (импортируем ПОСЛЕ определения app)
from app.api.routes import router as api_router

app.include_router(api_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=8081,
        reload=True
    )