"""
Session Daemon - Main entry point for the NeuroSurveillance Session Controller.

Orchestrates all components:
1. Loads config.yaml
2. Connects MQTT, connects Radiens
3. Publishes OFF to all cameras on startup (clean slate)
4. Starts Flask API in background thread
5. Main polling loop: poll Radiens every 1s, detect transitions
6. SIGTERM handler: abort active session, publish OFF, disconnect

Usage:
    python daemon.py [--config /path/to/config.yaml]
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml

from radiens_poller import RadiensPoller, RadiensStatus
from frigate_controller import FrigateController
from session_manager import SessionManager
from api import app, init_api

logger = logging.getLogger("neurosurveillance")

# ---------------------------------------------------------------------------
# Default config path
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_PATH = "/opt/neurosurveillance/config.yaml"


def load_config(config_path: str) -> dict:
    """Load and validate config.yaml."""
    path = Path(config_path)
    if not path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    with open(path) as f:
        config = yaml.safe_load(f)

    if not config:
        logger.error("Config file is empty: %s", config_path)
        sys.exit(1)

    # Validate required sections
    required = ["daemon", "api", "mqtt", "frigate", "cameras"]
    for section in required:
        if section not in config:
            logger.error("Missing required config section: '%s'", section)
            sys.exit(1)

    return config


def setup_logging(config: dict):
    """Configure logging with console and rotating file output."""
    daemon_cfg = config.get("daemon", {})
    log_level_str = daemon_cfg.get("log_level", "info").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    log_dir = daemon_cfg.get("log_dir", "/opt/neurosurveillance/logs")

    # Ensure log directory exists
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    # File handler (rotating, 10MB, keep 5 files)
    log_file = os.path.join(log_dir, "session-daemon.log")
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logger.info("Logging configured: level=%s, file=%s", log_level_str, log_file)


class SessionDaemon:
    """Main daemon that orchestrates Radiens polling, Frigate control, and the API."""

    def __init__(self, config: dict):
        self.config = config
        self._running = False
        self._shutdown_event = threading.Event()

        daemon_cfg = config.get("daemon", {})
        self.poll_interval = daemon_cfg.get("poll_interval", 1.0)
        tz_name = daemon_cfg.get("timezone", "Asia/Seoul")

        cameras = config.get("cameras", {})
        sessions_dir = config.get("sessions", {}).get(
            "data_dir", "/opt/neurosurveillance/sessions"
        )

        # Initialize components
        self.session_manager = SessionManager(
            sessions_dir=sessions_dir,
            export_dir=config["frigate"].get(
                "export_dir", "/opt/neurosurveillance/exports"
            ),
            tz_name=tz_name,
            cameras=cameras,
        )

        self.frigate = FrigateController(
            mqtt_host=config["mqtt"].get("host", "127.0.0.1"),
            mqtt_port=config["mqtt"].get("port", 1883),
            frigate_url=config["frigate"].get("url", "http://127.0.0.1:5000"),
            cameras=cameras,
        )

        self.poller = RadiensPoller(
            poll_interval=self.poll_interval,
            on_session_start=self._handle_session_start,
            on_session_end=self._handle_session_end,
        )

        # Initialize the Flask API with references to components
        init_api(
            session_manager=self.session_manager,
            radiens_poller=self.poller,
            frigate_controller=self.frigate,
            config=config,
        )

    def start(self):
        """Start the daemon: connect services, reset state, run main loop."""
        logger.info("=" * 60)
        logger.info("NeuroSurveillance Session Daemon starting")
        logger.info("=" * 60)

        self._running = True

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # 1. Connect to MQTT
        logger.info("Connecting to MQTT broker...")
        if not self.frigate.connect_mqtt():
            logger.error(
                "Failed to connect to MQTT broker at %s:%d. "
                "Ensure Mosquitto is running (docker ps).",
                self.config["mqtt"].get("host"),
                self.config["mqtt"].get("port"),
            )
            sys.exit(1)

        # 2. Reset recording state (clean slate)
        logger.info("Resetting all camera recordings to OFF (clean slate)...")
        self.frigate.stop_all_recording()

        # 3. Connect to Radiens
        logger.info("Connecting to Radiens...")
        if not self.poller.connect():
            logger.warning(
                "Could not connect to Radiens on startup. "
                "The daemon will keep retrying in the main loop. "
                "Ensure Radiens is running."
            )
            # Do NOT exit -- Radiens may start later

        # 4. Start Flask API in background thread
        api_host = self.config["api"].get("host", "127.0.0.1")
        api_port = self.config["api"].get("port", 8585)
        api_thread = threading.Thread(
            target=self._run_api,
            args=(api_host, api_port),
            daemon=True,
            name="api-thread",
        )
        api_thread.start()
        logger.info("API server started on http://%s:%d", api_host, api_port)

        # 5. Main polling loop
        logger.info(
            "Entering main loop (poll interval: %.1fs)", self.poll_interval
        )
        self._main_loop()

    def _main_loop(self):
        """Poll Radiens continuously. Transitions trigger callbacks."""
        while self._running and not self._shutdown_event.is_set():
            # If Radiens is not connected, try to reconnect
            if not self.poller.connected:
                self.poller.connect()

            # Poll (handles transitions via callbacks)
            self.poller.poll()

            # Sleep with shutdown check
            self._shutdown_event.wait(timeout=self.poll_interval)

    def _handle_session_start(self, status: RadiensStatus):
        """Called when Radiens transitions R_OFF -> R_ON."""
        logger.info(">>> SESSION START detected")

        # Start session in manager (uses pending metadata)
        session = self.session_manager.start_session(
            radiens_base_name=status.base_name,
            radiens_file_path=status.file_path,
        )

        # Enable Frigate recording for this session's camera
        if not self.frigate.set_recording(session.camera, enabled=True):
            logger.error(
                "Failed to enable Frigate recording for %s. "
                "Video may not be captured for this session!",
                session.camera,
            )

        logger.info(
            "Session %s active: camera=%s, mouse=%s, type=%s",
            session.session_id[:8],
            session.camera,
            session.mouse_id,
            session.recording_type,
        )

    def _handle_session_end(self, status: RadiensStatus):
        """Called when Radiens transitions R_ON -> R_OFF."""
        logger.info(">>> SESSION END detected")

        # End session in manager (records end time, generates filename)
        session = self.session_manager.end_session()
        if session is None:
            logger.warning("Session end detected but no active session to close")
            return

        # Disable Frigate recording
        self.frigate.set_recording(session.camera, enabled=False)

        logger.info(
            "Session %s ended: duration=%.0fs, filename=%s",
            session.session_id[:8],
            session.duration_seconds,
            session.video_filename,
        )

        # Export video from Frigate (runs in a background thread to avoid
        # blocking the main polling loop)
        export_thread = threading.Thread(
            target=self._export_session,
            args=(session,),
            daemon=True,
            name=f"export-{session.session_id[:8]}",
        )
        export_thread.start()

    def _export_session(self, session):
        """Export video from Frigate. Runs in a background thread.

        Args:
            session: The completed SessionRecord.
        """
        try:
            logger.info(
                "Starting Frigate export for session %s...",
                session.session_id[:8],
            )

            # Add a small buffer (2s) to start/end to ensure we capture
            # the full session (Frigate records in segments)
            start_time = session.start_time_utc - 2
            end_time = session.end_time_utc + 2

            export_id = self.frigate.export_recording(
                camera_id=session.camera,
                start_time=start_time,
                end_time=end_time,
            )

            if export_id is None:
                logger.error(
                    "Frigate export request failed for session %s",
                    session.session_id[:8],
                )
                self.session_manager.update_export_status("failed: export request rejected")
                return

            # Wait for export to complete
            result = self.frigate.wait_for_export(export_id)
            if result is None:
                logger.error(
                    "Frigate export timed out for session %s",
                    session.session_id[:8],
                )
                self.session_manager.update_export_status("failed: export timed out")
                return

            self.session_manager.update_export_status("completed")
            logger.info(
                "Export completed for session %s: %s",
                session.session_id[:8],
                session.video_filename,
            )

            # NAS transfer would go here (deferred)
            # if self.config.get("nas", {}).get("enabled"):
            #     self._transfer_to_nas(session)

        except Exception as e:
            logger.error(
                "Export failed for session %s: %s",
                session.session_id[:8],
                e,
                exc_info=True,
            )
            self.session_manager.update_export_status(f"failed: {e}")

    def _run_api(self, host: str, port: int):
        """Run the Flask API server. Called in a background thread."""
        # Suppress Flask/Werkzeug startup banner and request logs
        werkzeug_logger = logging.getLogger("werkzeug")
        werkzeug_logger.setLevel(logging.WARNING)

        app.run(host=host, port=port, debug=False, use_reloader=False)

    def _signal_handler(self, signum, frame):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, shutting down...", sig_name)
        self.stop()

    def stop(self):
        """Graceful shutdown: abort active session, stop recording, disconnect."""
        self._running = False
        self._shutdown_event.set()

        # Abort active session if any
        if self.session_manager.has_active_session:
            logger.warning("Aborting active session due to shutdown")
            session = self.session_manager.abort_session(reason="daemon shutdown")
            if session:
                # Try to stop recording for the aborted session's camera
                self.frigate.set_recording(session.camera, enabled=False)

        # Stop all recording (safety net)
        logger.info("Stopping all camera recordings...")
        self.frigate.stop_all_recording()

        # Disconnect MQTT
        logger.info("Disconnecting MQTT...")
        self.frigate.disconnect_mqtt()

        logger.info("Session Daemon stopped")


def main():
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="NeuroSurveillance Session Daemon"
    )
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to config.yaml (default: {DEFAULT_CONFIG_PATH})",
    )
    args = parser.parse_args()

    # Load config first (before logging, since config defines log settings)
    # Use basic logging until config is loaded
    logging.basicConfig(level=logging.INFO)
    config = load_config(args.config)

    # Set up proper logging from config
    setup_logging(config)

    # Create and start daemon
    daemon = SessionDaemon(config)
    try:
        daemon.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        daemon.stop()
    except Exception as e:
        logger.critical("Daemon crashed: %s", e, exc_info=True)
        daemon.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
