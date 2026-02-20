"""
Radiens Poller - Polls NeuroNexus Radiens for EEG recording state changes.

Detects R_OFF -> R_ON (session start) and R_ON -> R_OFF (session end)
transitions by polling AllegoClient.get_status() at a configurable interval.

The poller only OBSERVES Radiens state. It never starts/stops EEG recording.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RecordingState(Enum):
    """Radiens recording states."""
    ON = "R_ON"
    OFF = "R_OFF"
    UNKNOWN = "UNKNOWN"


@dataclass
class RadiensStatus:
    """Snapshot of Radiens state from a single poll."""
    recording: RecordingState = RecordingState.UNKNOWN
    stream: str = ""
    base_name: str = ""
    file_path: str = ""
    connected: bool = False
    error: Optional[str] = None
    poll_time: float = field(default_factory=time.time)


class RadiensPoller:
    """Polls Radiens AllegoClient for recording state transitions.

    Args:
        poll_interval: Seconds between polls (default 1.0).
        on_session_start: Callback when R_OFF -> R_ON detected.
        on_session_end: Callback when R_ON -> R_OFF detected.
    """

    def __init__(
        self,
        poll_interval: float = 1.0,
        on_session_start: Optional[Callable[[RadiensStatus], None]] = None,
        on_session_end: Optional[Callable[[RadiensStatus], None]] = None,
    ):
        self.poll_interval = poll_interval
        self.on_session_start = on_session_start
        self.on_session_end = on_session_end

        self._client = None
        self._previous_state = RecordingState.UNKNOWN
        self._connected = False
        self._consecutive_errors = 0
        self._max_silent_errors = 5  # Log every Nth consecutive error

    def connect(self) -> bool:
        """Connect to Radiens. Returns True if successful."""
        try:
            from radiens import AllegoClient
            self._client = AllegoClient()
            # Test the connection with a status poll
            status = self._client.get_status()
            self._connected = True
            self._consecutive_errors = 0
            logger.info("Connected to Radiens (recording: %s)", status.recording)
            return True
        except ImportError:
            logger.error(
                "radiens package not installed. "
                "Install it from NeuroNexus (not available on PyPI)."
            )
            self._connected = False
            return False
        except Exception as e:
            logger.error("Failed to connect to Radiens: %s", e)
            self._connected = False
            return False

    def poll(self) -> RadiensStatus:
        """Poll Radiens once and return current status.

        Detects state transitions and fires callbacks.
        If Radiens is unreachable, returns a status with connected=False
        and does NOT change internal state (fail-safe).
        """
        if self._client is None:
            return RadiensStatus(
                connected=False,
                error="Not connected (call connect() first)",
            )

        try:
            allego_status = self._client.get_status()
            self._connected = True
            self._consecutive_errors = 0

            # Parse recording state
            rec_str = str(allego_status.recording)
            if rec_str == "R_ON":
                current_state = RecordingState.ON
            elif rec_str == "R_OFF":
                current_state = RecordingState.OFF
            else:
                current_state = RecordingState.UNKNOWN
                logger.warning("Unexpected recording state: %s", rec_str)

            # Extract metadata from status
            status = RadiensStatus(
                recording=current_state,
                stream=str(getattr(allego_status, "stream", "")),
                base_name=str(getattr(allego_status, "base_name", "")),
                file_path=str(getattr(allego_status, "path", "")),
                connected=True,
            )

            # Detect transitions
            if (
                self._previous_state == RecordingState.OFF
                and current_state == RecordingState.ON
            ):
                logger.info(
                    "Recording STARTED (R_OFF -> R_ON), base_name=%s",
                    status.base_name,
                )
                if self.on_session_start:
                    self.on_session_start(status)

            elif (
                self._previous_state == RecordingState.ON
                and current_state == RecordingState.OFF
            ):
                logger.info("Recording STOPPED (R_ON -> R_OFF)")
                if self.on_session_end:
                    self.on_session_end(status)

            # On first successful poll, just record the state without
            # firing transitions (we don't know the "previous" state yet)
            if self._previous_state == RecordingState.UNKNOWN:
                logger.info("Initial Radiens state: %s", current_state.value)

            self._previous_state = current_state
            return status

        except Exception as e:
            self._consecutive_errors += 1
            self._connected = False

            # Avoid log spam: log first error, then every Nth
            if (
                self._consecutive_errors == 1
                or self._consecutive_errors % self._max_silent_errors == 0
            ):
                logger.warning(
                    "Radiens poll failed (%d consecutive): %s",
                    self._consecutive_errors,
                    e,
                )

            # Do NOT change _previous_state on error (fail-safe)
            return RadiensStatus(
                connected=False,
                error=str(e),
            )

    @property
    def connected(self) -> bool:
        """Whether the last poll was successful."""
        return self._connected

    @property
    def previous_state(self) -> RecordingState:
        """The last known recording state."""
        return self._previous_state
