from typing import Dict, List, Optional
from datetime import datetime
import uuid


class TextEntry:
    def __init__(self, user_id: str, text: str, room_id: str):
        self.id = str(uuid.uuid4())
        self.user_id = user_id
        self.text = text
        self.room_id = room_id
        self.timestamp = datetime.now()
        self.is_finalized = True


class TextManager:
    def __init__(self, max_history_per_room: int = 100):
        self.max_history_per_room = max_history_per_room
        self.room_histories: Dict[str, List[TextEntry]] = {}

    def add_text(self, user_id: str, text: str, room_id: str) -> dict:
        """Add new text entry to room history"""
        if room_id not in self.room_histories:
            self.room_histories[room_id] = []

        # Create new entry
        entry = TextEntry(user_id, text, room_id)
        self.room_histories[room_id].append(entry)

        # Limit history size
        if len(self.room_histories[room_id]) > self.max_history_per_room:
            self.room_histories[room_id] = self.room_histories[room_id][-self.max_history_per_room:]

        return self._entry_to_dict(entry)

    def get_recent_history(self, room_id: str, limit: int = 20) -> List[dict]:
        """Get recent text history for a room"""
        if room_id not in self.room_histories:
            return []

        recent_entries = self.room_histories[room_id][-limit:]
        return [self._entry_to_dict(entry) for entry in recent_entries]

    def get_user_history(self, room_id: str, user_id: str, limit: int = 10) -> List[dict]:
        """Get recent text history for specific user in room"""
        if room_id not in self.room_histories:
            return []

        user_entries = [entry for entry in self.room_histories[room_id] if entry.user_id == user_id]
        recent_user_entries = user_entries[-limit:]
        return [self._entry_to_dict(entry) for entry in recent_user_entries]

    def clear_room_history(self, room_id: str):
        """Clear all history for a room"""
        if room_id in self.room_histories:
            del self.room_histories[room_id]

    def _entry_to_dict(self, entry: TextEntry) -> dict:
        """Convert TextEntry to dictionary for JSON serialization"""
        return {
            "id": entry.id,
            "user_id": entry.user_id,
            "text": entry.text,
            "room_id": entry.room_id,
            "timestamp": entry.timestamp.isoformat(),
            "is_finalized": entry.is_finalized
        }