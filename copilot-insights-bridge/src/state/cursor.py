"""File-based high-water mark cursor for tracking pipeline progress."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class CursorState(BaseModel):
    """Persisted state for the bridge polling cursor."""

    last_processed_timestamp: datetime | None = None
    last_run_at: datetime | None = None
    events_processed_count: int = 0


class Cursor:
    """Read and write a JSON cursor file to track the last-processed position."""

    def __init__(self, cursor_path: str = ".bridge_cursor.json") -> None:
        self._path = Path(cursor_path)

    def load(self) -> CursorState:
        """Load cursor state from disk, returning defaults if the file is missing."""
        if not self._path.exists():
            return CursorState()
        data = json.loads(self._path.read_text())
        return CursorState.model_validate(data)

    def save(self, state: CursorState) -> None:
        """Atomically write cursor state to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(self._path.parent), suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(state.model_dump_json(indent=2))
            os.replace(tmp, str(self._path))
        except BaseException:
            os.unlink(tmp)
            raise
