"""
Session Manager - Manages session lifecycle, metadata, filenames, and logging.

Handles:
- Session metadata (mouse ID, recording type, user, chamber)
- Filename generation (YYMMDDHHMM_mouseID_type.mp4)
- Session JSON sidecar file creation
- Session history tracking
"""

import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


@dataclass
class SessionMetadata:
    """User-provided metadata for a recording session."""
    mouse_id: str = "unknown"
    recording_type: str = "unknown"
    user_name: str = "unknown"
    chamber: int = 0

    def is_default(self) -> bool:
        """Returns True if no metadata was explicitly set."""
        return (
            self.mouse_id == "unknown"
            and self.recording_type == "unknown"
            and self.user_name == "unknown"
        )


@dataclass
class SessionRecord:
    """Complete record of a finished session."""
    session_id: str = ""
    start_time_utc: float = 0.0
    end_time_utc: float = 0.0
    start_time_local: str = ""
    end_time_local: str = ""
    duration_seconds: float = 0.0
    mouse_id: str = ""
    recording_type: str = ""
    user_name: str = ""
    chamber: int = 0
    camera: str = ""
    radiens_xdat_filename: str = ""
    radiens_xdat_path: str = ""
    video_filename: str = ""
    export_status: str = "pending"
    nas_transfer_status: str = "skipped"


class SessionManager:
    """Manages session lifecycle, metadata, and logging.

    Args:
        sessions_dir: Directory for session JSON sidecar files.
        export_dir: Directory for exported MP4 files.
        tz_name: Timezone name for local timestamps (e.g. 'Asia/Seoul').
        cameras: Dict mapping chamber numbers to camera IDs.
    """

    def __init__(
        self,
        sessions_dir: str = "/opt/neurosurveillance/sessions",
        export_dir: str = "/opt/neurosurveillance/exports",
        tz_name: str = "Asia/Seoul",
        cameras: Optional[dict] = None,
    ):
        self.sessions_dir = Path(sessions_dir)
        self.export_dir = Path(export_dir)
        self.tz = ZoneInfo(tz_name)
        self.cameras = cameras or {"chamber_0": "pi_cam_0", "chamber_1": "pi_cam_1"}

        # Current pending metadata (set by API before session starts)
        self._pending_metadata = SessionMetadata()

        # Active session (set when recording starts, cleared on end)
        self._active_session: Optional[SessionRecord] = None

        # History of completed sessions (in-memory, also persisted to disk)
        self._history: list[SessionRecord] = []

        # Ensure directories exist
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.export_dir.mkdir(parents=True, exist_ok=True)

        # Load existing session history from disk
        self._load_history()

    def set_metadata(
        self,
        mouse_id: Optional[str] = None,
        recording_type: Optional[str] = None,
        user_name: Optional[str] = None,
        chamber: Optional[int] = None,
    ) -> SessionMetadata:
        """Set metadata for the next session. Partial updates allowed."""
        if mouse_id is not None:
            self._pending_metadata.mouse_id = mouse_id
        if recording_type is not None:
            self._pending_metadata.recording_type = recording_type
        if user_name is not None:
            self._pending_metadata.user_name = user_name
        if chamber is not None:
            self._pending_metadata.chamber = chamber

        logger.info(
            "Session metadata updated: mouse=%s, type=%s, user=%s, chamber=%d",
            self._pending_metadata.mouse_id,
            self._pending_metadata.recording_type,
            self._pending_metadata.user_name,
            self._pending_metadata.chamber,
        )
        return self._pending_metadata

    def clear_metadata(self):
        """Reset metadata to defaults for the next session."""
        self._pending_metadata = SessionMetadata()
        logger.info("Session metadata cleared (reset to defaults)")

    def start_session(
        self,
        radiens_base_name: str = "",
        radiens_file_path: str = "",
    ) -> SessionRecord:
        """Start a new session. Called when Radiens R_OFF -> R_ON detected.

        Uses pending metadata (if set) and records start time.

        Args:
            radiens_base_name: Radiens XDAT base filename from get_status().
            radiens_file_path: Radiens XDAT file path from get_status().

        Returns:
            The new SessionRecord.
        """
        now_utc = time.time()
        now_local = datetime.fromtimestamp(now_utc, tz=self.tz)

        meta = self._pending_metadata
        camera_key = f"chamber_{meta.chamber}"
        camera_id = self.cameras.get(camera_key, f"pi_cam_{meta.chamber}")

        session = SessionRecord(
            session_id=str(uuid.uuid4()),
            start_time_utc=now_utc,
            start_time_local=now_local.isoformat(),
            mouse_id=meta.mouse_id,
            recording_type=meta.recording_type,
            user_name=meta.user_name,
            chamber=meta.chamber,
            camera=camera_id,
            radiens_xdat_filename=radiens_base_name,
            radiens_xdat_path=radiens_file_path,
        )

        self._active_session = session

        if meta.is_default():
            logger.warning(
                "Session started WITHOUT metadata (using defaults). "
                "Files will be named with 'unknown' placeholders."
            )
        else:
            logger.info(
                "Session started: mouse=%s, type=%s, user=%s, chamber=%d, camera=%s",
                session.mouse_id, session.recording_type,
                session.user_name, session.chamber, session.camera,
            )

        return session

    def end_session(self) -> Optional[SessionRecord]:
        """End the active session. Called when Radiens R_ON -> R_OFF detected.

        Records end time, generates filename, and writes session sidecar.

        Returns:
            The completed SessionRecord, or None if no active session.
        """
        if self._active_session is None:
            logger.warning("end_session called but no active session")
            return None

        session = self._active_session
        now_utc = time.time()
        now_local = datetime.fromtimestamp(now_utc, tz=self.tz)

        session.end_time_utc = now_utc
        session.end_time_local = now_local.isoformat()
        session.duration_seconds = round(now_utc - session.start_time_utc, 1)
        session.video_filename = self._generate_filename(session)

        logger.info(
            "Session ended: duration=%.0fs, filename=%s",
            session.duration_seconds,
            session.video_filename,
        )

        # Write session sidecar JSON
        self._write_session_json(session)

        # Add to history
        self._history.append(session)

        # Clear active session and metadata for next run
        self._active_session = None
        self.clear_metadata()

        return session

    def abort_session(self, reason: str = "daemon shutdown") -> Optional[SessionRecord]:
        """Abort the active session (e.g. on daemon shutdown).

        Writes a partial session record with the abort reason.

        Returns:
            The aborted SessionRecord, or None if no active session.
        """
        if self._active_session is None:
            return None

        session = self._active_session
        now_utc = time.time()
        now_local = datetime.fromtimestamp(now_utc, tz=self.tz)

        session.end_time_utc = now_utc
        session.end_time_local = now_local.isoformat()
        session.duration_seconds = round(now_utc - session.start_time_utc, 1)
        session.video_filename = self._generate_filename(session)
        session.export_status = f"aborted: {reason}"

        logger.warning(
            "Session ABORTED: reason=%s, duration=%.0fs",
            reason, session.duration_seconds,
        )

        self._write_session_json(session)
        self._history.append(session)
        self._active_session = None
        self.clear_metadata()

        return session

    def update_export_status(self, status: str):
        """Update the export status of the most recent session."""
        if self._history:
            self._history[-1].export_status = status
            # Re-write the session JSON with updated status
            self._write_session_json(self._history[-1])

    def _generate_filename(self, session: SessionRecord) -> str:
        """Generate filename: YYMMDDHHMM_mouseID_type.mp4

        Uses local time (Asia/Seoul) for the timestamp portion.
        """
        start_local = datetime.fromtimestamp(session.start_time_utc, tz=self.tz)
        timestamp = start_local.strftime("%y%m%d%H%M")
        mouse = session.mouse_id.replace(" ", "_")
        rec_type = session.recording_type.replace(" ", "_")
        return f"{timestamp}_{mouse}_{rec_type}.mp4"

    def _write_session_json(self, session: SessionRecord):
        """Write session sidecar JSON to disk."""
        # Filename: same as video but with _session.json suffix
        base = session.video_filename.rsplit(".", 1)[0] if session.video_filename else session.session_id
        json_filename = f"{base}_session.json"
        json_path = self.sessions_dir / json_filename

        try:
            data = asdict(session)
            with open(json_path, "w") as f:
                json.dump(data, f, indent=2)
            logger.info("Session JSON written: %s", json_path)
        except Exception as e:
            logger.error("Failed to write session JSON to %s: %s", json_path, e)

    def _load_history(self):
        """Load session history from existing JSON files on disk."""
        try:
            json_files = sorted(self.sessions_dir.glob("*_session.json"))
            for json_file in json_files:
                try:
                    with open(json_file) as f:
                        data = json.load(f)
                    record = SessionRecord(**{
                        k: v for k, v in data.items()
                        if k in SessionRecord.__dataclass_fields__
                    })
                    self._history.append(record)
                except Exception as e:
                    logger.warning("Failed to load session file %s: %s", json_file, e)

            if self._history:
                logger.info("Loaded %d session records from disk", len(self._history))
        except Exception as e:
            logger.warning("Failed to scan session history directory: %s", e)

    @property
    def active_session(self) -> Optional[SessionRecord]:
        """The currently active session, or None."""
        return self._active_session

    @property
    def pending_metadata(self) -> SessionMetadata:
        """The metadata set for the next session."""
        return self._pending_metadata

    @property
    def history(self) -> list[SessionRecord]:
        """All completed sessions."""
        return self._history

    @property
    def has_active_session(self) -> bool:
        return self._active_session is not None
