# This file makes the app directory a Python package

# Импортируем после инициализации в main.py
def get_stt_processor():
    from app.main import stt_processor
    return stt_processor