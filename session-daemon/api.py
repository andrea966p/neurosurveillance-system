"""
HTTP REST API - Lightweight Flask API for session metadata and status.

Binds to 127.0.0.1:8585 (localhost only). Provides endpoints for:
- Setting session metadata (mouse_id, recording_type, user_name, chamber)
- Querying daemon status, current session, and session history
- Health check for systemd watchdog

This API is consumed by the future UI (deferred to external app-building tool).
It can also be used directly via curl for testing and scripting.
"""

import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

from flask import Flask, jsonify, request

if TYPE_CHECKING:
    from session_manager import SessionManager
    from radiens_poller import RadiensPoller
    from frigate_controller import FrigateController

logger = logging.getLogger(__name__)

app = Flask(__name__)

# These are set by daemon.py at startup via init_api()
_session_manager: "SessionManager | None" = None
_radiens_poller: "RadiensPoller | None" = None
_frigate_controller: "FrigateController | None" = None
_config: dict | None = None


def init_api(
    session_manager: "SessionManager",
    radiens_poller: "RadiensPoller",
    frigate_controller: "FrigateController",
    config: dict,
):
    """Initialize the API with references to daemon components.

    Called once by daemon.py before starting the Flask server.
    """
    global _session_manager, _radiens_poller, _frigate_controller, _config
    _session_manager = session_manager
    _radiens_poller = radiens_poller
    _frigate_controller = frigate_controller
    _config = config
    logger.info("API initialized")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.route("/api/status", methods=["GET"])
def get_status():
    """Daemon status overview.

    Returns:
        - daemon: running state
        - radiens: connection status, current recording state
        - mqtt: connection status
        - frigate: reachable or not
        - session: active session summary (if any)
        - pending_metadata: metadata set for next session
    """
    radiens_connected = _radiens_poller.connected if _radiens_poller else False
    radiens_state = (
        _radiens_poller.previous_state.value if _radiens_poller else "UNKNOWN"
    )

    mqtt_connected = (
        _frigate_controller.mqtt_connected if _frigate_controller else False
    )

    active = None
    if _session_manager and _session_manager.has_active_session:
        session = _session_manager.active_session
        active = {
            "session_id": session.session_id,
            "mouse_id": session.mouse_id,
            "recording_type": session.recording_type,
            "chamber": session.chamber,
            "camera": session.camera,
            "start_time_local": session.start_time_local,
        }

    pending = None
    if _session_manager:
        meta = _session_manager.pending_metadata
        pending = {
            "mouse_id": meta.mouse_id,
            "recording_type": meta.recording_type,
            "user_name": meta.user_name,
            "chamber": meta.chamber,
            "is_default": meta.is_default(),
        }

    return jsonify({
        "daemon": "running",
        "radiens": {
            "connected": radiens_connected,
            "recording_state": radiens_state,
        },
        "mqtt": {
            "connected": mqtt_connected,
        },
        "session": active,
        "pending_metadata": pending,
    })


@app.route("/api/session/metadata", methods=["POST"])
def set_metadata():
    """Set metadata for the next recording session.

    Accepts JSON body with any combination of:
        - mouse_id (str): Mouse identifier (e.g. "HETCF3R1")
        - recording_type (str): Recording type (e.g. "basal", "sd")
        - user_name (str): Researcher name (e.g. "andrea")
        - chamber (int): Chamber number (0 or 1)

    Partial updates are allowed -- only provided fields are changed.

    Returns:
        Updated metadata.

    Example:
        curl -X POST http://127.0.0.1:8585/api/session/metadata \\
          -H "Content-Type: application/json" \\
          -d '{"mouse_id": "HETCF3R1", "recording_type": "basal", "chamber": 0}'
    """
    if not _session_manager:
        return jsonify({"error": "Session manager not initialized"}), 503

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400

    # Validate chamber if provided
    if "chamber" in data:
        try:
            chamber = int(data["chamber"])
            if chamber not in (0, 1):
                return jsonify({
                    "error": f"Invalid chamber: {chamber}. Must be 0 or 1."
                }), 400
            data["chamber"] = chamber
        except (ValueError, TypeError):
            return jsonify({
                "error": "chamber must be an integer (0 or 1)"
            }), 400

    # Validate lab member if user_name provided
    if "user_name" in data and _config:
        lab_members = _config.get("lab_members", [])
        if lab_members and data["user_name"] not in lab_members:
            logger.warning(
                "user_name '%s' not in lab_members list: %s",
                data["user_name"],
                lab_members,
            )
            # Warning only -- don't reject the request

    updated = _session_manager.set_metadata(
        mouse_id=data.get("mouse_id"),
        recording_type=data.get("recording_type"),
        user_name=data.get("user_name"),
        chamber=data.get("chamber"),
    )

    return jsonify({
        "status": "ok",
        "metadata": {
            "mouse_id": updated.mouse_id,
            "recording_type": updated.recording_type,
            "user_name": updated.user_name,
            "chamber": updated.chamber,
            "is_default": updated.is_default(),
        },
    })


@app.route("/api/session/metadata", methods=["DELETE"])
def clear_metadata():
    """Clear pending metadata (reset to defaults)."""
    if not _session_manager:
        return jsonify({"error": "Session manager not initialized"}), 503

    _session_manager.clear_metadata()
    return jsonify({"status": "ok", "message": "Metadata cleared to defaults"})


@app.route("/api/session/current", methods=["GET"])
def get_current_session():
    """Get the currently active session, if any.

    Returns:
        Session details if active, or {"session": null}.
    """
    if not _session_manager:
        return jsonify({"error": "Session manager not initialized"}), 503

    if _session_manager.has_active_session:
        session = _session_manager.active_session
        return jsonify({"session": asdict(session)})

    return jsonify({"session": None})


@app.route("/api/session/history", methods=["GET"])
def get_session_history():
    """List past sessions.

    Query parameters:
        - limit (int): Max number of sessions to return (default 50, newest first)

    Returns:
        List of session records.
    """
    if not _session_manager:
        return jsonify({"error": "Session manager not initialized"}), 503

    limit = request.args.get("limit", 50, type=int)
    limit = max(1, min(limit, 500))  # Clamp between 1 and 500

    # Return newest first
    history = _session_manager.history
    recent = list(reversed(history[-limit:]))

    return jsonify({
        "count": len(recent),
        "total": len(history),
        "sessions": [asdict(s) for s in recent],
    })


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint.

    Returns 200 if the daemon is running and core services are connected.
    Returns 503 if critical services are down.

    Used by systemd watchdog and monitoring.
    """
    radiens_ok = _radiens_poller.connected if _radiens_poller else False
    mqtt_ok = _frigate_controller.mqtt_connected if _frigate_controller else False

    healthy = radiens_ok and mqtt_ok
    status_code = 200 if healthy else 503

    return jsonify({
        "healthy": healthy,
        "radiens_connected": radiens_ok,
        "mqtt_connected": mqtt_ok,
    }), status_code
