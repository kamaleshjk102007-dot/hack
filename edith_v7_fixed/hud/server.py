# E.D.I.T.H. — HUD Server with FULL Real-Time Metrics
import base64
import binascii
import json
import os, sys, time, threading, re, subprocess, pickle
from pathlib import Path
from datetime import datetime
from flask import Flask, Response, jsonify, request, session
from flask_socketio import SocketIO, disconnect

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.settings import HUD_HOST, HUD_PORT, USER_CITY, USER_STATE, USER_COUNTRY, USER_LAT, USER_LON
from utils.logger import get_logger
log = get_logger("hud")

app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config["SECRET_KEY"] = os.getenv("EDITH_SECRET_KEY") or os.urandom(32).hex()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.getenv("EDITH_COOKIE_SECURE", "false").lower() in ("true", "1", "yes"):
    app.config["SESSION_COOKIE_SECURE"] = True
# Restrict Socket.IO connections to localhost only. The HUD is a local
# single-user interface; accepting connections from arbitrary origins would
# expose every /api/* endpoint to any website the user visits (CSRF).
_HUD_ORIGINS = [
    f"http://localhost:{HUD_PORT}",
    f"http://127.0.0.1:{HUD_PORT}",
    f"http://[::1]:{HUD_PORT}",
]
if HUD_HOST not in ("127.0.0.1", "localhost", "::1", "0.0.0.0") and os.getenv("EDITH_ALLOW_REMOTE_HUD", "").lower() in ("true", "1", "yes"):
    _HUD_ORIGINS.append(f"http://{HUD_HOST}:{HUD_PORT}")

socketio = SocketIO(app, cors_allowed_origins=_HUD_ORIGINS, async_mode="threading",
    ping_timeout=20,        # kill dead connections after 20s (was 60s default)
    ping_interval=10,       # heartbeat every 10s
    max_http_buffer_size=1_000_000,  # 1MB max message — prevents memory bloat
    compression_threshold=1024,      # gzip any payload over 1KB (code-viewer
    http_compression=True)           # streams, memory dumps, etc.

# ── Server-side Session & Socket.IO Authentication Management ───
_session_lock = threading.Lock()
_revoked_session_ids = set()
_active_sessions = {}       # session_id -> metadata
_authenticated_sids = {}    # sid -> session_id
_SESSION_MAX_AGE_SECONDS = 86400  # 24 hours max lifetime


def authorize_session(sess, identity: str = "kamalesh") -> str:
    """Authorize a session and register server-side tracking."""
    sess_id = os.urandom(16).hex()
    sess["face_authorized"] = True
    sess["face_identity"] = identity
    sess["face_authorized_at"] = datetime.now().isoformat(timespec="seconds")
    sess["session_id"] = sess_id
    sess.pop("revoked", None)
    with _session_lock:
        _active_sessions[sess_id] = {
            "identity": identity,
            "created_at": datetime.now(),
        }
    return sess_id


def revoke_session(session_id: str | None = None, sid: str | None = None) -> bool:
    """Revoke a session server-side and terminate any active Socket.IO connections."""
    revoked = False
    with _session_lock:
        if session_id:
            _revoked_session_ids.add(session_id)
            _active_sessions.pop(session_id, None)
            revoked = True
        if sid and sid in _authenticated_sids:
            mapped_sess = _authenticated_sids.pop(sid, None)
            if mapped_sess:
                _revoked_session_ids.add(mapped_sess)
                _active_sessions.pop(mapped_sess, None)
            revoked = True

    # Terminate active socket connections associated with this session
    if sid:
        try:
            disconnect(sid=sid)
        except Exception:
            pass
    elif session_id:
        with _session_lock:
            sids_to_drop = [s for s, s_id in _authenticated_sids.items() if s_id == session_id]
        for s in sids_to_drop:
            try:
                disconnect(sid=s)
            except Exception:
                pass
            with _session_lock:
                _authenticated_sids.pop(s, None)
    return revoked


def is_authorized_session(sess=None) -> bool:
    """
    Verify authorization for HTTP and Socket.IO contexts.
    Enforces:
    1. Server-side authorized flag
    2. Exact identity match (FACE_ALLOWED_LABEL)
    3. Session not explicitly revoked
    4. Session ID not in revoked list
    5. Session timestamp present and not expired (max 24 hours)
    6. No clock manipulation (timestamp not in the future)
    """
    if sess is None:
        sess = session
    if not sess:
        return False
    if not (sess.get("face_authorized") is True and sess.get("face_identity") == "kamalesh"):
        return False
    if sess.get("revoked") is True:
        return False

    sess_id = sess.get("session_id")
    if sess_id:
        with _session_lock:
            if sess_id in _revoked_session_ids:
                return False

    auth_at = sess.get("face_authorized_at")
    if auth_at:
        try:
            auth_dt = datetime.fromisoformat(auth_at)
            now = datetime.now()
            # Max session validity: 24 hours (86400s)
            if (now - auth_dt).total_seconds() > _SESSION_MAX_AGE_SECONDS:
                return False
            # Future timestamp tampering guard (>5 min in future)
            if (auth_dt - now).total_seconds() > 300:
                return False
        except Exception:
            return False
    return True


def is_socketio_authorized() -> bool:
    """Verify session authorization for Socket.IO clients."""
    return is_authorized_session(session)


from functools import wraps

def _api_auth_required(f):
    """Decorator that enforces session auth on HTTP API endpoints.

    Returns HTTP 401 JSON for unauthenticated callers so that browser
    code receives a structured error rather than a redirect to a login
    page that may not exist.
    """
    @wraps(f)
    def _guarded(*args, **kwargs):
        if not is_authorized_session(session):
            return jsonify({"error": "Unauthorized", "authenticated": False}), 401
        return f(*args, **kwargs)
    return _guarded


@app.errorhandler(Exception)
def _handle_any_error(e):
    """Catch-all so NO route can ever return a bare, bodyless 500 again.
    Always logs the full traceback to edith.log/console and always returns
    a JSON body with the real exception, so the actual cause is visible
    instead of a generic 'INTERNAL SERVER ERROR'."""
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    log.error(f'Unhandled exception on {request.path}: {e}', exc_info=True)
    return jsonify({'error': str(e), 'type': type(e).__name__, 'path': request.path}), 500

_queue       = []
_prev_net    = None
_live_coords = {"lat": None, "lon": None}   # set by browser GPS
_face_auth   = {"loaded": False, "error": None, "last_attempt": 0.0}

# ── Face-auth brute-force guard ───────────────────────────────────
# Track per-IP attempt counts inside a rolling 60-second window.
# Limit: max 10 attempts per IP per minute (enough for normal use,
# tight enough to stop automated scanning).
_face_rate   = {}   # ip -> [timestamp, ...]
_face_rate_lock = __import__('threading').Lock()
_FACE_RATE_WINDOW = 60     # seconds
_FACE_RATE_MAX   = 10      # max attempts per window


def _face_rate_check(ip: str) -> bool:
    """Return True if the IP is within the allowed request rate."""
    import time as _t
    now = _t.time()
    with _face_rate_lock:
        times = [ts for ts in _face_rate.get(ip, []) if now - ts < _FACE_RATE_WINDOW]
        times.append(now)
        _face_rate[ip] = times
        return len(times) <= _FACE_RATE_MAX

FACE_DEFAULT_ROOT      = Path(r"D:\facerego\facerego\output")
FACE_DENIED_DIR        = Path(__file__).resolve().parent.parent / "security" / "denied_attempts"
FACE_ALLOWED_LABEL     = "kamalesh"
# The trained model previously identified Kamalesh at 0.797, so 0.80 created a
# false rejection. Keep this configurable, with a conservative calibrated default.
FACE_ALLOWED_THRESHOLD = float(os.getenv("EDITH_FACE_THRESHOLD", "0.75"))
FACE_MODEL_RETRY_SECS  = 5.0
IMAGENET_MEAN          = (0.485, 0.456, 0.406)
IMAGENET_STD           = (0.229, 0.224, 0.225)


def _find_face_model_files():
    """Resolve the model from an explicit setting or common local locations."""
    app_root = Path(__file__).resolve().parent.parent
    configured = os.getenv("EDITH_FACE_MODEL_DIR", "").strip()
    roots = []
    if configured:
        roots.append(Path(configured).expanduser())
    roots.extend([
        FACE_DEFAULT_ROOT,
        app_root / "models" / "face_recognition",
        app_root / "models" / "face",
        app_root / "output",
        app_root.parent / "facerego" / "output",
    ])
    seen = set()
    for root in roots:
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        model_path = root / "best_model.pth"
        labels_path = root / "label_encoder.pkl"
        if model_path.is_file() and labels_path.is_file():
            return model_path, labels_path
    searched = ", ".join(str(p) for p in roots)
    raise FileNotFoundError(
        "Face model files are unavailable. Place best_model.pth and "
        f"label_encoder.pkl together, or set EDITH_FACE_MODEL_DIR. Searched: {searched}"
    )


def _build_face_classifier(num_classes):
    import torch.nn as nn
    from torchvision import models

    class MobileNetV2FaceClassifier(nn.Module):
        def __init__(self, classes):
            super().__init__()
            backbone = models.mobilenet_v2(weights=None)
            self.features = backbone.features
            self.pool = nn.AdaptiveAvgPool2d(1)
            self.head = nn.Sequential(
                nn.Dropout(0.3),
                nn.Linear(1280, 256),
                nn.ReLU(inplace=True),
                nn.Dropout(0.2),
                nn.Linear(256, classes),
            )

        def forward(self, x):
            x = self.features(x)
            x = self.pool(x).flatten(1)
            return self.head(x)

    return MobileNetV2FaceClassifier(num_classes)


def _ensure_face_auth():
    global _face_auth
    if _face_auth.get("loaded"):
        return _face_auth
    now = time.monotonic()
    if _face_auth.get("error") and now - _face_auth.get("last_attempt", 0.0) < FACE_MODEL_RETRY_SECS:
        return _face_auth

    _face_auth["last_attempt"] = now
    _face_auth["error"] = None

    try:
        import cv2
        import torch
        from torchvision.transforms import v2

        model_path, labels_path = _find_face_model_files()

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        checkpoint = torch.load(model_path, map_location=device, weights_only=False)
        with open(labels_path, "rb") as f:
            metadata = pickle.load(f)

        if isinstance(metadata, dict):
            class_names = metadata.get("class_names") or metadata.get("classes")
            img_size = int(metadata.get("img_size", 224))
        else:
            class_names = getattr(metadata, "classes_", None)
            img_size = 224
        if class_names is None:
            raise ValueError("label_encoder.pkl does not contain class names")
        class_names = [str(name).strip() for name in class_names]
        model = _build_face_classifier(len(class_names)).to(device)
        state_dict = checkpoint.get("state_dict", checkpoint) if isinstance(checkpoint, dict) else checkpoint
        model.load_state_dict(state_dict)
        model.eval()

        transform = v2.Compose([
            v2.ToImage(),
            v2.ToDtype(torch.float32, scale=True),
            v2.Resize((img_size, img_size)),
            v2.Normalize(mean=IMAGENET_MEAN, std=IMAGENET_STD),
        ])

        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        if cascade.empty():
            raise RuntimeError("Failed to load OpenCV Haar cascade.")

        _face_auth.update({
            "loaded": True,
            "device": device,
            "model": model,
            "transform": transform,
            "class_names": class_names,
            "cascade": cascade,
            "model_path": str(model_path),
            "labels_path": str(labels_path),
        })
        log.info(
            "Face authentication model loaded successfully from %s (classes=%s, threshold=%.2f)",
            model_path, class_names, FACE_ALLOWED_THRESHOLD,
        )
    except Exception as e:
        _face_auth["error"] = str(e)
        log.error(f"Face authentication unavailable: {e}")

    return _face_auth


def _predict_face_auth(frame_bgr):
    state = _ensure_face_auth()
    if state.get("error"):
        return {
            "ok": False,
            "allowed": False,
            "reason": "model_error",
            "message": state["error"],
        }

    import cv2
    import numpy as np
    import torch

    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    faces = state["cascade"].detectMultiScale(
        gray,
        scaleFactor=1.1,
        minNeighbors=5,
        minSize=(80, 80),
    )
    if len(faces) == 0:
        return {
            "ok": False,
            "allowed": False,
            "reason": "no_face",
            "message": "No face detected. Center your face in the camera.",
        }

    x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
    pad = int(0.20 * max(w, h))
    x1 = max(0, x - pad)
    y1 = max(0, y - pad)
    x2 = min(frame_bgr.shape[1], x + w + pad)
    y2 = min(frame_bgr.shape[0], y + h + pad)
    face_bgr = frame_bgr[y1:y2, x1:x2]
    if face_bgr.size == 0:
        return {
            "ok": False,
            "allowed": False,
            "reason": "bad_crop",
            "message": "Detected face could not be processed.",
        }

    face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
    tensor = state["transform"](face_rgb).unsqueeze(0).to(state["device"])
    with torch.no_grad():
        probs = torch.softmax(state["model"](tensor), dim=1)[0].cpu().numpy()

    best_idx = int(np.argmax(probs))
    best_label = str(state["class_names"][best_idx]).strip()
    confidence = float(probs[best_idx])
    known = confidence >= FACE_ALLOWED_THRESHOLD
    allowed = known and best_label.casefold() == FACE_ALLOWED_LABEL.casefold()

    if allowed:
        message = f"Authorized identity confirmed: Kamalesh ({confidence:.1%})."
    elif known:
        message = f"Access denied. Detected {best_label}."
    else:
        message = (
            f"Face matched {best_label} at {confidence:.1%}; "
            f"at least {FACE_ALLOWED_THRESHOLD:.0%} is required. Improve lighting and face the camera."
        )

    return {
        "ok": True,
        "allowed": allowed,
        "known": known,
        "label": best_label,
        "confidence": confidence,
        "reason": "authorized" if allowed else "unauthorized",
        "message": message,
    }


def _save_denied_attempt(frame_bgr, result):
    """Persist an audit image for a real face that failed authorization."""
    try:
        import cv2
        FACE_DENIED_DIR.mkdir(parents=True, exist_ok=True)
        label = re.sub(r"[^a-zA-Z0-9_-]", "_", str(result.get("label", "unknown")))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = FACE_DENIED_DIR / f"denied_{stamp}_{label}.jpg"
        if not cv2.imwrite(str(path), frame_bgr):
            raise RuntimeError("OpenCV could not write the denied-attempt image")
        log.warning(
            "Denied face-access attempt captured: %s (label=%s confidence=%.3f)",
            path, result.get("label", "unknown"), float(result.get("confidence", 0.0)),
        )
    except Exception as e:
        log.error(f"Could not save denied face-access image: {e}")

def _reverse_geocode(lat, lon):
    """Turn lat/lon into city name using free Nominatim API."""
    try:
        import requests
        session = requests.Session()
        session.trust_env = False
        url = (f"https://nominatim.openstreetmap.org/reverse"
               f"?lat={lat}&lon={lon}&format=json&zoom=10")
        r = session.get(url, timeout=6,
                         headers={"User-Agent": "EDITH-HUD/9.4 contact@edith.local"})
        if r.status_code == 200:
            d   = r.json()
            addr = d.get("address", {})
            city    = (addr.get("city") or addr.get("town") or
                       addr.get("village") or addr.get("county") or "")
            state   = addr.get("state", "")
            country = addr.get("country", "")
            return {"city": city, "state": state, "country": country,
                    "lat": lat, "lon": lon}
    except Exception as e:
        log.warning(f"Reverse geocode failed: {e}")
    return {}

_location_cache: dict = {}
_location_cache_ts: float = 0.0
_LOCATION_CACHE_TTL = 300  # 5 min

def _get_current_location():
    """Return best available location: browser GPS > IP geolocation > fallback.

    Browser GPS (_live_coords) is the most accurate and is always
    reverse-geocoded fresh. If no GPS is available yet, fall back to IP-based
    geolocation (_detect_location) instead of returning an empty dict, and
    cache that IP lookup for a few minutes so the metrics loop (every 5s)
    doesn't hammer the geolocation API on every tick.
    """
    global _location_cache, _location_cache_ts

    lat = _live_coords.get("lat")
    lon = _live_coords.get("lon")
    if lat and lon:
        geo = _reverse_geocode(lat, lon)
        if geo:
            return geo
        return {"city": "", "state": "", "country": "",
                "lat": lat, "lon": lon}

    # No GPS yet — use cached/fresh IP geolocation instead of giving up.
    now = time.time()
    if _location_cache and (now - _location_cache_ts) < _LOCATION_CACHE_TTL:
        return _location_cache

    try:
        from plugins.all_phases import _detect_location
        loc = _detect_location()
        if loc and loc.get("lat") and loc.get("lon"):
            geo = {
                "city":    loc.get("city", ""),
                "state":   loc.get("region", ""),
                "country": loc.get("country", ""),
                "lat":     loc.get("lat", ""),
                "lon":     loc.get("lon", ""),
            }
            _location_cache = geo
            _location_cache_ts = now
            return geo
    except Exception as e:
        log.warning(f"IP location fallback failed: {e}")

    return {}   # caller falls back to .env defaults

@app.route("/")
def index():
    template = "hud.html" if session.get("face_authorized") else "face_auth.html"
    path = os.path.join(os.path.dirname(__file__), "templates", template)
    with open(path, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.get("/api/pattern-lock/status")
def pattern_lock_status():
    from security.pattern_lock import is_configured
    return jsonify({"faceVerified": bool(session.get("face_verified")),
                    "configured": is_configured()})


@app.post("/api/pattern-lock/enroll")
def pattern_lock_enroll():
    """Request first-time enrollment; the next successful face scan authorizes setup."""
    from security.pattern_lock import is_configured
    if is_configured():
        return jsonify({"ok": False, "message": "Pattern lock is already configured."}), 409
    session["pattern_enroll_requested"] = True
    return jsonify({"ok": True, "faceRequired": True})


@app.post("/api/pattern-lock/setup")
def pattern_lock_setup():
    from security.pattern_lock import configure, is_configured
    if is_configured():
        return jsonify({"ok": False, "message": "Pattern lock is already configured."}), 409
    # First-use enrollment may be performed directly only from this computer.
    # Remote/LAN clients still need the verified-face enrollment session.
    local_request = request.remote_addr in {"127.0.0.1", "::1", "localhost"}
    if not session.get("face_verified") and not local_request:
        return jsonify({"ok": False, "message": "Initial pattern setup is allowed only on this device."}), 401
    try:
        configure((request.get_json(silent=True) or {}).get("pattern"))
        authorize_session(session, FACE_ALLOWED_LABEL)
        session.pop("pattern_failures", None)
        return jsonify({"ok": True, "authorized": True})
    except (ValueError, RuntimeError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.post("/api/pattern-lock/verify")
def pattern_lock_verify():
    from security.pattern_lock import verify
    from security.pattern_lock import is_configured
    if not is_configured():
        return jsonify({"ok": False, "message": "Pattern lock has not been created yet."}), 409
    locked_until = float(session.get("pattern_locked_until", 0))
    if time.time() < locked_until:
        remaining = max(1, int(locked_until - time.time()))
        return jsonify({"ok": False, "message": f"Too many attempts. Try again in {remaining} seconds."}), 429
    try:
        matched = verify((request.get_json(silent=True) or {}).get("pattern"))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400
    if not matched:
        failures = int(session.get("pattern_failures", 0)) + 1
        session["pattern_failures"] = failures
        if failures >= 5:
            session["pattern_locked_until"] = time.time() + 30
            session["pattern_failures"] = 0
        return jsonify({"ok": False, "message": "Pattern did not match.",
                        "attemptsRemaining": max(0, 5 - failures)}), 403
    authorize_session(session, FACE_ALLOWED_LABEL)
    session.pop("pattern_failures", None)
    session.pop("pattern_locked_until", None)
    return jsonify({"ok": True, "authorized": True})


@app.post("/api/pattern-lock/change")
def pattern_lock_change():
    """Create or replace the pattern from an already-authorized profile session."""
    if not is_authorized_session(session):
        return jsonify({"ok": False, "error": "unauthorized", "message": "Authentication required."}), 401

    from security.pattern_lock import is_configured, verify, replace
    payload = request.get_json(silent=True) or {}
    new_pattern = payload.get("new_pattern") or payload.get("pattern")
    if not new_pattern:
        return jsonify({"ok": False, "message": "New pattern is required."}), 400

    # Rate limiting on pattern change attempts
    locked_until = float(session.get("pattern_change_locked_until", 0))
    if time.time() < locked_until:
        remaining = max(1, int(locked_until - time.time()))
        return jsonify({"ok": False, "message": f"Too many attempts. Try again in {remaining} seconds."}), 429

    # For an existing pattern, current_pattern is strictly REQUIRED and must be verified
    if is_configured():
        current_pattern = payload.get("current_pattern")
        if current_pattern is None:
            return jsonify({"ok": False, "message": "Current pattern is required."}), 400

        try:
            current_matched = verify(current_pattern)
        except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
            return jsonify({"ok": False, "message": f"Invalid current pattern: {exc}"}), 400

        if not current_matched:
            failures = int(session.get("pattern_change_failures", 0)) + 1
            session["pattern_change_failures"] = failures
            if failures >= 5:
                session["pattern_change_locked_until"] = time.time() + 30
                session["pattern_change_failures"] = 0
            log.warning("Pattern change attempt rejected: current pattern did not match")
            return jsonify({
                "ok": False,
                "message": "Current pattern did not match.",
                "attemptsRemaining": max(0, 5 - failures),
            }), 403

    try:
        replace(new_pattern)
        session.pop("pattern_change_failures", None)
        session.pop("pattern_change_locked_until", None)
        authorize_session(session, FACE_ALLOWED_LABEL)
        log.info("Pattern lock updated successfully")
        return jsonify({"ok": True, "message": "Pattern password updated."})
    except (ValueError, OSError) as exc:
        return jsonify({"ok": False, "message": str(exc)}), 400


@app.route("/legacy-hud")
def legacy_hud():
    path = os.path.join(os.path.dirname(__file__), "templates", "hud.html")
    with open(path, "r", encoding="utf-8") as f:
        return Response(f.read(), mimetype="text/html")


@app.get("/api/nexus/state")
def nexus_state():
    from nexus.runtime import runtime
    return jsonify(runtime.snapshot())


@app.get("/api/nexus/connectors")
def nexus_connectors():
    from nexus.runtime import runtime
    return jsonify({"connectors": runtime.connector_manifests()})


@app.get("/api/nexus/tools")
def nexus_tools():
    from nexus.runtime import runtime
    tools = []
    for connector in runtime.connector_manifests():
        for tool in connector["tools"]:
            tools.append({**tool, "connector": connector["name"],
                          "connection": connector["statusLabel"], "category": connector["category"]})
    return jsonify({"tools": tools})


@app.post("/api/nexus/local-agent/connect")
def nexus_connect_local_agent():
    from nexus.runtime import runtime
    return jsonify(runtime.connect_local_agent())


@app.post("/api/nexus/tasks")
def nexus_create_task():
    from nexus.runtime import runtime
    payload = request.get_json(silent=True) or {}
    task_request = str(payload.get("request", "")).strip()
    if not task_request:
        return jsonify({"error": "A task request is required."}), 400
    return jsonify(runtime.create_task(task_request, demo=payload.get("demo", False),
                                       attachments=payload.get("attachments", []))), 201


@app.get("/api/nexus/tasks/<task_id>")
def nexus_get_task(task_id):
    from nexus.runtime import runtime
    task = runtime.tasks.get(task_id)
    return jsonify(task) if task else (jsonify({"error": "Task not found."}), 404)


@app.post("/api/nexus/tasks/<task_id>/approve")
def nexus_approve_task(task_id):
    from nexus.runtime import runtime
    payload = request.get_json(silent=True) or {}
    token = payload.get("token") or payload.get("approval_token")
    task, err = runtime.approve(task_id, token)
    if err:
        status_code = 404 if err == "Task not found." else 403
        return jsonify({"error": err}), status_code
    return jsonify(task)


@app.post("/api/nexus/tasks/<task_id>/cancel")
def nexus_cancel_task(task_id):
    from nexus.runtime import runtime
    task = runtime.cancel(task_id)
    return jsonify(task) if task else (jsonify({"error": "Task not found."}), 404)


@app.get("/api/nexus/history")
def nexus_history():
    from nexus.runtime import runtime
    return jsonify({"history": list(reversed(runtime.history))})


@app.route("/api/nexus/memory", methods=["GET", "PATCH", "DELETE"])
def nexus_memory():
    from nexus.runtime import runtime
    if request.method == "GET":
        return jsonify({"memories": runtime.memories})
    payload = request.get_json(silent=True) or {}
    memory_id = str(payload.get("id", ""))
    item = next((m for m in runtime.memories if m["id"] == memory_id), None)
    if not item:
        return jsonify({"error": "Memory not found."}), 404
    if request.method == "DELETE":
        runtime.memories.remove(item)
    else:
        if "value" in payload: item["value"] = str(payload["value"])
        if "enabled" in payload: item["enabled"] = bool(payload["enabled"])
    return jsonify({"ok": True, "memories": runtime.memories})


@app.post("/api/face-auth")
def face_auth():
    # Rate-limit: 10 attempts per 60 s per client IP
    client_ip = request.remote_addr or "unknown"
    if not _face_rate_check(client_ip):
        log.warning("Face-auth rate limit exceeded for IP %s", client_ip)
        return jsonify({"ok": False, "allowed": False, "reason": "rate_limited",
                        "message": "Too many attempts. Please wait a minute."}), 429
    try:
        import cv2
        import numpy as np

        payload = request.get_json(silent=True) or {}
        image_data = payload.get("image", "")
        if not image_data:
            return jsonify({
                "ok": False,
                "allowed": False,
                "reason": "missing_image",
                "message": "No webcam frame received.",
            }), 400

        if "," in image_data:
            image_data = image_data.split(",", 1)[1]

        try:
            frame_bytes = base64.b64decode(image_data, validate=True)
        except (binascii.Error, ValueError):
            return jsonify({
                "ok": False,
                "allowed": False,
                "reason": "decode_error",
                "message": "The webcam frame was not valid image data.",
            }), 400
        frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        if frame is None:
            return jsonify({
                "ok": False,
                "allowed": False,
                "reason": "decode_error",
                "message": "Could not decode webcam frame.",
            }), 400

        result = _predict_face_auth(frame)
        if result.get("allowed"):
            from security.pattern_lock import is_configured
            enrollment = bool(session.get("pattern_enroll_requested")) and not is_configured()
            session.clear()
            if enrollment:
                session["face_verified"] = True
                result["pattern_required"] = True
                result["pattern_setup"] = True
            else:
                authorize_session(session, FACE_ALLOWED_LABEL)
                result["pattern_required"] = False
                result["pattern_setup"] = False
        elif result.get("reason") == "unauthorized":
            session.clear()
            _save_denied_attempt(frame, result)
        status = 200 if result.get("ok") or result.get("reason") in {"no_face", "unauthorized"} else 503
        return jsonify(result), status
    except Exception as e:
        log.error(f"Face auth request failed: {e}")
        return jsonify({
            "ok": False,
            "allowed": False,
            "reason": "server_error",
            "message": str(e),
        }), 500


@app.before_request
def require_face_authorization():
    """Keep all HUD/API functionality inaccessible until Kamalesh is verified."""
    # Origin validation for state-changing HTTP requests (CSRF mitigation)
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("Origin")
        if origin and origin not in _HUD_ORIGINS:
            log.warning(f"Blocked cross-origin state-changing request from Origin: {origin}")
            return jsonify({
                "ok": False,
                "error": "csrf_detected",
                "message": "Cross-origin requests are not permitted.",
            }), 403

    public_paths = {"/", "/api/logout", "/api/face-auth", "/api/pattern-lock/status", "/api/pattern-lock/enroll",
                    "/api/pattern-lock/setup", "/api/pattern-lock/verify", "/favicon.ico",
                    "/api/extension/summary", "/api/extension/sync"}
    if request.path in public_paths or request.path.startswith("/static/"):
        return None
    if is_authorized_session(session):
        return None
    if request.path.startswith("/api/"):
        return jsonify({
            "ok": False,
            "authenticated": False,
            "error": "face_auth_required",
            "message": "Kamalesh face verification is required.",
        }), 401
    return Response("Face authentication required", status=401, mimetype="text/plain")


@app.route("/api/logout", methods=["GET", "POST"])
def api_logout():
    """Revoke session server-side and clear client session."""
    sess_id = session.get("session_id")
    if sess_id:
        revoke_session(session_id=sess_id)
    session.clear()
    session["revoked"] = True
    return jsonify({"ok": True, "message": "Logged out successfully."})


@app.route('/api/model')
@_api_auth_required
def api_model():
    """Return cloud task-router status (provider names and availability only, no key values)."""
    try:
        from brain.ai_engine import get_active_model
        task_type = request.args.get('task_type', 'agent')
        data = get_active_model(task_type)
        # Belt-and-suspenders: strip any field whose name contains 'key' or 'secret'
        # from the HTTP response even if future changes re-introduce them.
        safe = {k: v for k, v in data.items() if "key" not in k.lower() and "secret" not in k.lower()}
        # Re-add the renamed status-only fields under their new names
        for status_field in ("gemini_key_status", "groq_key_status"):
            if status_field in data:
                safe[status_field] = data[status_field]
        return jsonify(safe)
    except Exception as e:
        log.error(f"Model info request failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/model/usage')
@_api_auth_required
def api_model_usage():
    """Return per-model usage bars (authenticated users only)."""
    try:
        from brain.cloud_router import get_model_usage, get_live_model, get_failure_log
        usage = get_model_usage()
        # Attach the most recent failure reason for any model currently on cooldown
        log_entries = get_failure_log(limit=200)
        last_reason = {}
        for ts, task_type, provider, reason in log_entries:
            # Provider libraries can emit multi-line connection traces. The
            # HUD needs a concise actionable status, not a raw traceback.
            text = str(reason).replace("\n", " ")
            if "Failed to resolve" in text or "NameResolutionError" in text:
                text = "Network/DNS could not reach this provider."
            elif len(text) > 180:
                text = text[:177] + "..."
            last_reason[provider] = text  # chronological: last write wins
        for label, stats in usage.items():
            if stats.get("on_cooldown"):
                stats["last_failure_reason"] = last_reason.get(label, "unknown")
        return jsonify({
            "usage": usage,
            "live": get_live_model(),
        })
    except Exception as e:
        log.error(f"Model usage request failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/vision', methods=['POST'])
def api_vision():
    """
    Real image analysis — Gemini multimodal (image bytes + text prompt),
    not just filename/metadata. Used by the 📁 attach-file chat feature
    when the attached file is an image.
    """
    try:
        data = request.get_json(force=True) or {}
        image_b64 = data.get('image', '')
        mime_type = data.get('mime', 'image/png')
        prompt    = data.get('prompt') or 'Describe and analyze this image in detail, Sir.'

        # Strip a data: URL prefix if the frontend sent the raw FileReader result
        if image_b64.startswith('data:'):
            image_b64 = image_b64.split(',', 1)[-1]

        if not image_b64:
            return jsonify({'error': 'no image data provided'}), 400

        from brain.ai_engine import query_vision
        response = query_vision(prompt, image_b64, mime_type)
        return jsonify({'response': response})
    except Exception as e:
        log.error(f'/api/vision 500: {e}', exc_info=True)
        return jsonify({'error': str(e), 'response': f"⚠️ Image analysis failed, Sir: {e}"}), 500


_EXTRACT_MAX_CHARS = 20000  # keep prompt size sane, matches spirit of client MAX_CHARS

def _extract_docx_text(data: bytes) -> str:
    import io
    from docx import Document
    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)

def _extract_pptx_text(data: bytes) -> str:
    import io
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    slides_out = []
    for i, slide in enumerate(prs.slides, 1):
        lines = [f"--- Slide {i} ---"]
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                lines.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    cells = [c.text.strip() for c in row.cells]
                    if any(cells):
                        lines.append(" | ".join(cells))
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
                lines.append(f"[Speaker notes: {slide.notes_slide.notes_text_frame.text.strip()}]")
        except Exception:
            pass
        if len(lines) > 1:
            slides_out.append("\n".join(lines))
    return "\n\n".join(slides_out)

def _extract_pdf_text(data: bytes) -> str:
    import io
    try:
        from pypdf import PdfReader
    except ImportError:
        from PyPDF2 import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages_out = []
    for i, page in enumerate(reader.pages, 1):
        t = (page.extract_text() or "").strip()
        if t:
            pages_out.append(f"--- Page {i} ---\n{t}")
    return "\n\n".join(pages_out)

_EXTRACTORS = {
    "docx": _extract_docx_text,
    "pptx": _extract_pptx_text,
    "pdf":  _extract_pdf_text,
}

# Package names as pip knows them (module name != pip name for pptx).
_EXTRACTOR_PIP_PKG = {
    "docx": "python-docx",
    "pptx": "python-pptx",
    "pdf":  "pypdf",
}

# Packages that _pip_install is permitted to install automatically.
# Adding a package here is a deliberate decision \u2014 do not expand without review.
_ALLOWED_AUTO_INSTALL_PKGS: frozenset[str] = frozenset({"python-pptx", "pypdf", "python-docx"})

# Patterns that indicate a package argument is actually a URL or path rather
# than a simple package name \u2014 all of these bypass PyPI and must be rejected.
_PKG_INJECTION_RE = re.compile(
    r"(?:https?://|git\+|ssh://|file://|#egg=|\.whl$|\.tar\.gz$|\.zip$"
    r"|--index-url|--extra-index-url|--find-links|-e\s|;)",
    re.I,
)


def _pip_install(pkg: str) -> bool:
    """Allowlist-gated auto-install of a missing extraction dependency.

    Only packages in _ALLOWED_AUTO_INSTALL_PKGS may be installed.  This
    prevents an attacker from triggering installation of an arbitrary package
    by crafting a ModuleNotFoundError with a chosen module name.
    """
    pkg = (pkg or "").strip()

    # \u2500\u2500 Allowlist check \u2500\u2500
    if pkg not in _ALLOWED_AUTO_INSTALL_PKGS:
        log.error(
            f"[SELF-HEAL] Refusing to install '{pkg}' \u2014 not in the permitted package allowlist. "
            f"Permitted: {sorted(_ALLOWED_AUTO_INSTALL_PKGS)}"
        )
        return False

    # \u2500\u2500 Injection guard (belt-and-suspenders) \u2500\u2500
    if _PKG_INJECTION_RE.search(pkg):
        log.error(f"[SELF-HEAL] Refusing to install '{pkg}' \u2014 argument looks like a URL or path.")
        return False

    # \u2500\u2500 Sanitize environment: strip secret-bearing env vars \u2500\u2500
    clean_env = os.environ.copy()
    for k in list(clean_env):
        if any(term in k.upper() for term in ("API_KEY", "SECRET", "TOKEN", "PASSWORD")):
            clean_env.pop(k, None)

    try:
        log.warning(f"[SELF-HEAL] '{pkg}' not installed \u2014 attempting auto pip install")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg, "--break-system-packages"],
            capture_output=True, text=True, timeout=90,
            env=clean_env,
        )
        if result.returncode == 0:
            log.info(f"[SELF-HEAL] Installed '{pkg}' successfully")
            return True
        # Some environments (Windows pip, managed venvs) reject that flag
        result2 = subprocess.run(
            [sys.executable, "-m", "pip", "install", pkg],
            capture_output=True, text=True, timeout=90,
            env=clean_env,
        )
        if result2.returncode == 0:
            log.info(f"[SELF-HEAL] Installed '{pkg}' successfully (fallback)")
            return True
        log.error(f"[SELF-HEAL] Failed to install '{pkg}': {result2.stderr[-500:]}")
        return False
    except Exception as e:
        log.error(f"[SELF-HEAL] pip install '{pkg}' errored: {e}")
        return False

@app.post('/api/extract-file')
def api_extract_file():
    """
    Server-side text extraction for docx/pptx/pdf attachments from the chat
    file-picker. The browser can't read these binary formats as text on its
    own — that's what used to produce the "binary/unsupported type, cannot
    read as text" message for every Word/PowerPoint/PDF attachment.
    """
    try:
        f = request.files.get("file")
        if not f or not f.filename:
            return jsonify({"ok": False, "error": "no file provided"}), 400

        name = f.filename
        file_ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        extractor = _EXTRACTORS.get(file_ext)
        if not extractor:
            return jsonify({"ok": False, "error": f"unsupported file type: .{file_ext}"}), 415

        data = f.read()

        def _run():
            return extractor(data)

        try:
            text = _run()
        except ModuleNotFoundError as e:
            # Missing dependency (e.g. python-pptx/pypdf never got pip
            # installed in this environment) — try to self-heal once by
            # installing it on the fly, then retry the exact same extraction.
            pkg = _EXTRACTOR_PIP_PKG.get(file_ext, str(e).split("'")[1] if "'" in str(e) else file_ext)
            if _pip_install(pkg):
                try:
                    text = _run()
                except Exception as e2:
                    log.error(f"/api/extract-file: retry after install failed for {name}: {e2}", exc_info=True)
                    return jsonify({"ok": False, "error": f"extraction failed after installing {pkg}: {e2}"}), 422
            else:
                return jsonify({
                    "ok": False,
                    "error": f"required package '{pkg}' is not installed and auto-install failed — "
                             f"run: pip install {pkg} --break-system-packages"
                }), 500
        except Exception as e:
            log.error(f"/api/extract-file: extraction failed for {name}: {e}", exc_info=True)
            return jsonify({"ok": False, "error": f"extraction failed: {e}"}), 422

        truncated = False
        if len(text) > _EXTRACT_MAX_CHARS:
            text = text[:_EXTRACT_MAX_CHARS]
            truncated = True

        return jsonify({"ok": True, "text": text, "truncated": truncated})
    except Exception as e:
        log.error(f'/api/extract-file 500: {e}', exc_info=True)
        return jsonify({"ok": False, "error": str(e)}), 500


@socketio.on("connect")
def on_connect(auth=None):
    # Strictly reject unauthenticated connections and ignore unvalidated client auth payloads
    if not is_socketio_authorized():
        log.warning("Socket.IO connection rejected: client is not authorized")
        return False
    sid = getattr(request, "sid", None)
    if sid:
        sess_id = session.get("session_id") or "authorized"
        with _session_lock:
            _authenticated_sids[sid] = sess_id
    log.info(f"HUD client connected (sid: {sid})")
    # Auto-detect real location and push to client
    try:
        from plugins.all_phases import _detect_location
        loc = _detect_location()
        if loc:
            socketio.emit("location", {
                "city":    loc.get("city", USER_CITY),
                "state":   loc.get("region", USER_STATE),
                "country": loc.get("country", USER_COUNTRY),
                "lat":     str(loc.get("lat", USER_LAT)),
                "lon":     str(loc.get("lon", USER_LON)),
                "display": f"{loc.get('city', USER_CITY)}, {loc.get('region', USER_STATE)}, {loc.get('country', USER_COUNTRY)}",
                "source":  "ip"
            })
        else:
            raise ValueError("detection failed")
    except Exception:
        # Fallback to .env values
        socketio.emit("location", {
            "city": USER_CITY, "state": USER_STATE, "country": USER_COUNTRY,
            "lat": USER_LAT, "lon": USER_LON,
            "display": f"{USER_CITY}, {USER_STATE}, {USER_COUNTRY}",
            "source": "fallback"
        })

def _safe_disconnect():
    """Safely terminate client connection if in an active Socket.IO context."""
    if hasattr(request, "sid"):
        try:
            disconnect()
        except Exception:
            pass


@socketio.on("set_location")
def on_set_location(data):
    """Browser sends GPS coordinates here."""
    if not is_socketio_authorized():
        log.warning("Rejected set_location from unauthorized Socket.IO client")
        _safe_disconnect()
        return
    if not isinstance(data, dict):
        return
    global _live_coords
    lat = data.get("lat")
    lon = data.get("lon")
    if lat and lon:
        _live_coords = {"lat": str(lat), "lon": str(lon)}
        log.info(f"Browser GPS location set: {lat}, {lon}")
        # Reverse geocode and push display name back to client
        geo = _reverse_geocode(lat, lon)
        if geo:
            socketio.emit("location", {
                "city":    geo.get("city", ""),
                "state":   geo.get("state", ""),
                "country": geo.get("country", ""),
                "lat":     str(lat),
                "lon":     str(lon),
                "display": f"{geo.get('city','')}, {geo.get('state','')}, {geo.get('country','')}",
                "source":  "gps"
            })
    else:
        log.info("Browser geolocation denied — will use wttr.in auto-detection")

@socketio.on("get_weather")
def on_get_weather(data=None):
    """Client requested weather — use stored GPS coords if available."""
    if not is_socketio_authorized():
        log.warning("Rejected get_weather from unauthorized Socket.IO client")
        _safe_disconnect()
        return
    try:
        from plugins.all_phases import get_weather
        lat = _live_coords.get("lat", "")
        lon = _live_coords.get("lon", "")
        result = get_weather("", lat=lat, lon=lon)
        socketio.emit("weather_data", {"weather": result})
    except Exception as e:
        socketio.emit("weather_data", {"weather": f"Weather error: {e}"})

@socketio.on("logout")
def on_logout(data=None):
    """Client requested logout via Socket.IO."""
    sid = getattr(request, "sid", None)
    sess_id = session.get("session_id")
    if sess_id or sid:
        revoke_session(session_id=sess_id, sid=sid)
    session.clear()
    session["revoked"] = True
    _safe_disconnect()

@socketio.on("disconnect")
def on_disconnect():
    sid = getattr(request, "sid", None)
    if sid:
        with _session_lock:
            _authenticated_sids.pop(sid, None)
    log.info(f"HUD client disconnected (sid: {sid})")

@socketio.on("command")
def on_command(data):
    if not is_socketio_authorized():
        log.warning("Rejected command from unauthorized Socket.IO client")
        _safe_disconnect()
        return
    if not isinstance(data, dict):
        log.warning("Rejected malformed command payload")
        return
    # Strictly ignore client-supplied auth flags, roles, or session identifiers
    cmd = str(data.get("command", "")).strip()
    if cmd:
        log.info(f"CMD: {cmd}")
        _queue.append(cmd)

# Cache for slow/expensive metrics — also read by Phase10 bg agent
_metrics_cache: dict = {}

def _get_all_metrics(tick: int = 0):
    import psutil
    global _prev_net, _metrics_cache
    d = {}

    # ── Fast metrics — every tick (5 s) ──────────────────────
    # CPU: non-blocking (interval=None uses last sample, avoids 0.3s sleep)
    d["cpu"]         = round(psutil.cpu_percent(interval=None), 1)
    d["cpu_per_core"]= psutil.cpu_percent(percpu=True, interval=None)

    # RAM
    vm = psutil.virtual_memory()
    d["ram"]         = round(vm.percent, 1)
    d["ram_used"]    = round(vm.used    / 1024**3, 1)
    d["ram_total"]   = round(vm.total   / 1024**3, 1)
    d["ram_free"]    = round(vm.available / 1024**3, 1)

    # Network speed (cheap — just counter diff)
    net_now = psutil.net_io_counters()
    if _prev_net is not None:
        dl = max(0, net_now.bytes_recv - _prev_net.bytes_recv)
        ul = max(0, net_now.bytes_sent - _prev_net.bytes_sent)
        d["net_dl"] = round(dl * 8 / 1_000_000, 2)
        d["net_ul"] = round(ul * 8 / 1_000_000, 2)
    else:
        d["net_dl"] = d["net_ul"] = 0.0
    _prev_net = net_now
    d["net_total_recv"] = round(net_now.bytes_recv / 1024**3, 2)
    d["net_total_sent"] = round(net_now.bytes_sent / 1024**3, 2)

    # Battery (cheap)
    bat = psutil.sensors_battery()
    if bat:
        d["battery"]          = round(bat.percent, 1)
        d["battery_charging"] = bat.power_plugged
        secs = bat.secsleft
        if secs and secs > 0 and not bat.power_plugged:
            h, rem = divmod(secs // 60, 60)
            d["battery_time"] = f"{h}h {rem:02d}m remaining"
        elif bat.power_plugged:
            d["battery_time"] = "Charging"
        else:
            d["battery_time"] = "Calculating..."
    else:
        d["battery"] = 97.0
        d["battery_charging"] = True
        d["battery_time"] = "Desktop"

    # ── Slow metrics — every 6th tick (~30 s) ────────────────
    if tick % 6 == 0:
        # CPU static info (never changes)
        freq = psutil.cpu_freq()
        _metrics_cache["cpu_freq"]    = round(freq.current) if freq else 0
        _metrics_cache["cpu_cores"]   = psutil.cpu_count(logical=False) or 0
        _metrics_cache["cpu_threads"] = psutil.cpu_count(logical=True) or 0

        # Disk usage
        try:
            disk = psutil.disk_usage("C:/")
        except Exception:
            disk = psutil.disk_usage("/")
        _metrics_cache["disk"]       = round(disk.percent, 1)
        _metrics_cache["disk_used"]  = round(disk.used  / 1024**3, 1)
        _metrics_cache["disk_total"] = round(disk.total / 1024**3, 1)
        _metrics_cache["disk_free"]  = round(disk.free  / 1024**3, 1)

        # Disk I/O counters
        try:
            dio = psutil.disk_io_counters()
            _metrics_cache["disk_read_mb"]  = round(dio.read_bytes  / 1024**2, 1)
            _metrics_cache["disk_write_mb"] = round(dio.write_bytes / 1024**2, 1)
        except Exception:
            _metrics_cache.setdefault("disk_read_mb", 0)
            _metrics_cache.setdefault("disk_write_mb", 0)

        # Process count (moderately expensive)
        _metrics_cache["processes"] = len(psutil.pids())

        # Temperature
        try:
            temps = psutil.sensors_temperatures() or {}
            all_t = [r.current for readings in temps.values()
                     for r in readings if r.current and r.current > 0]
            _metrics_cache["temp_cpu"] = round(max(all_t), 1)   if all_t else 45.0
            _metrics_cache["temp_gpu"] = round(sorted(all_t)[-2], 1) if len(all_t) >= 2 else 52.0
            _metrics_cache["temp_arc"] = round(min(all_t), 1)   if all_t else 36.0
        except Exception:
            _metrics_cache.setdefault("temp_cpu", 45.0)
            _metrics_cache.setdefault("temp_gpu", 52.0)
            _metrics_cache.setdefault("temp_arc", 36.0)

        # Uptime
        secs = int(time.time() - psutil.boot_time())
        _metrics_cache["uptime"] = f"{secs//3600}h {(secs%3600)//60:02d}m"

    # ── Ping — every 12th tick (~60 s), run in bg so it never blocks ──
    if tick % 12 == 0:
        def _do_ping():
            try:
                import platform
                if platform.system() == "Windows":
                    cmd_p = ["ping", "-n", "1", "-w", "1000", "8.8.8.8"]
                    pat   = r"Average = (\d+)ms"
                else:
                    cmd_p = ["ping", "-c", "1", "-W", "1", "8.8.8.8"]
                    pat   = r"time[=<]([\d.]+) ?ms"
                res = subprocess.run(cmd_p, capture_output=True, text=True, timeout=3)
                m = re.search(pat, res.stdout)
                _metrics_cache["net_ping"] = round(float(m.group(1))) if m else 0
            except Exception:
                _metrics_cache.setdefault("net_ping", 0)
        import threading as _th
        _th.Thread(target=_do_ping, daemon=True).start()

    # Merge slow-metric cache into result
    d.update(_metrics_cache)

    # Derived
    d.setdefault("cpu_freq", 0); d.setdefault("cpu_cores", 0)
    d.setdefault("disk", 0); d.setdefault("processes", 0)
    d.setdefault("temp_cpu", 45.0); d.setdefault("temp_gpu", 52.0); d.setdefault("temp_arc", 36.0)
    d.setdefault("uptime", "0h 00m"); d.setdefault("net_ping", 0)
    # Uptime
    secs = int(time.time() - psutil.boot_time())
    d["uptime"] = f"{secs//3600}h {(secs%3600)//60:02d}m"
    # Derived
    d["power"]   = d["battery"]
    d["shield"]  = 100.0
    d["overall"] = round(100 - (d["cpu"]*0.3 + d["ram"]*0.4 + d["disk"]*0.3)/3, 1)
    # Location (auto-detected, cached 5 min)
    loc = _get_current_location()
    d["city"]    = loc.get("city",    USER_CITY)
    d["state"]   = loc.get("state",   USER_STATE)
    d["country"] = loc.get("country", USER_COUNTRY)
    d["lat"]     = str(loc.get("lat", USER_LAT))
    d["lon"]     = str(loc.get("lon", USER_LON))
    return d

def _monitor():
    try:
        import psutil
    except:
        log.error("psutil missing — run: pip install psutil")
        return
    log.info("Real-time metrics monitor started")
    # Counters for staggered slow metrics
    _tick = 0
    _last_emitted = {}
    # Fields checked for meaningful change before we bother emitting.
    # Everything else (battery, disk, uptime, etc.) rides along whenever
    # one of these ticks, so the UI never goes more than FORCE_EVERY
    # ticks without a heartbeat even on a perfectly idle machine.
    DELTA_FIELDS = ("cpu", "ram", "net_dl", "net_ul")
    DELTA_PCT = 2.0      # emit if any tracked field moved >= 2 percentage/units
    FORCE_EVERY = 6      # ~30s at the 5s poll interval — guarantees a refresh
    while True:
        try:
            t0 = time.time()
            m  = _get_all_metrics(_tick)
            m["timestamp"] = datetime.now().isoformat()

            changed = not _last_emitted or _tick % FORCE_EVERY == 0
            if not changed:
                for f in DELTA_FIELDS:
                    if abs(float(m.get(f, 0)) - float(_last_emitted.get(f, 0))) >= DELTA_PCT:
                        changed = True
                        break

            if changed:
                socketio.emit("metrics", m)
                _last_emitted = {f: m.get(f, 0) for f in DELTA_FIELDS}
            _tick += 1
        except Exception as e:
            log.warning(f"Metrics err: {e}")
        # Poll every 5 s — reduces CPU/RAM load significantly
        time.sleep(max(0, 5.0 - (time.time()-t0)))

def get_command():  return _queue.pop(0) if _queue else None
def send_response(text, command=""):
    import re as _re, json as _json

    # Failsafe: if AI returned [ROUTE:image_search] re-route
    if text and '[ROUTE:image_search]' in text and command:
        try:
            from brain.router import route as _route
            text = _route(command)
        except Exception:
            pass

    # ── Sanitize agent JSON leakage ──────────────────────────
    # If response looks like raw agent JSON (starts with { or ```json),
    # try to extract the "answer" field; fall back to stripping fences.
    if text and text.strip().startswith(('{', '```')):
        clean = _re.sub(r'```[a-z]*\n?', '', text, flags=_re.M)
        clean = _re.sub(r'\n?```', '', clean, flags=_re.M).strip()
        # Try JSON parse
        for candidate in _re.findall(r'\{[\s\S]+?\}', clean + clean[::-1]):
            try:
                obj = _json.loads(candidate)
                if 'answer' in obj and obj['answer']:
                    text = obj['answer']
                    break
            except Exception:
                pass
        else:
            # Remove any remaining JSON blocks, keep prose
            text = _re.sub(r'\{[^{}]*\}', '', clean).strip() or text

    # Strip Ollama meta commentary
    text = _re.sub(r'After performing the action:?', '', text, flags=_re.I).strip()
    text = _re.sub(r'```[a-z]*\n?[\s\S]*?```', '', text, flags=_re.M).strip()

    # ── Safety net: Groq's gpt-oss reasoning-model bug ────────
    # Groq occasionally leaks the model's internal "thinking" straight
    # into the visible reply even with reasoning hidden at the API
    # level (see community.groq.com/t/670), producing text like:
    #   'KamaleshThe user asks "..." According to policy, ... Kamalesh.Kamalesh'
    # If we see Harmony-style channel control tokens, keep only what
    # follows the final channel. This is a last-resort net — the real
    # fix is the reasoning_format="hidden" param set in brain/ai_engine.py
    # and brain/cloud_router.py.
    if text and ('<|channel|>' in text or '<|start|>' in text or 'assistantfinal' in text):
        for _marker in ("<|start|>assistant<|channel|>final<|message|>",
                         "<|channel|>final<|message|>", "assistantfinal"):
            _idx = text.rfind(_marker)
            if _idx != -1:
                text = text[_idx + len(_marker):]
        text = _re.sub(r'<\|[a-z_]+\|>', '', text).strip()

    socketio.emit("response", {"response":text,"command":command,"timestamp":datetime.now().isoformat()})

def send_project_notify(text, command=""):
    """Send project build messages on a SEPARATE event so they never appear in CHAT tab."""
    # Strip [PROJECT] prefix — the frontend adds its own formatting
    clean = text.replace("[PROJECT]", "").strip()
    socketio.emit("project_update", {
        "text":      text,       # full text with [PROJECT] prefix (for PROJECT panel)
        "message":   clean,      # clean version
        "timestamp": datetime.now().isoformat(),
    })

def send_code_stream(filename: str, content: str, file_num: int = 0, total: int = 0):
    """Stream file content to HUD in chunks — creates the live typewriter effect."""
    import time
    # Send header first
    socketio.emit("code_stream_start", {
        "filename": filename,
        "file_num": file_num,
        "total":    total,
        "timestamp": datetime.now().isoformat(),
    })
    # Strip markdown fences before streaming (AI sometimes wraps code in ```)
    import re as _re
    content = _re.sub(r'^[ \t]*```[\w]*[ \t]*\n?', '', content, flags=_re.MULTILINE)
    content = _re.sub(r'\n?[ \t]*```[ \t]*$', '', content, flags=_re.MULTILINE).strip()

    # Stream content in lines (feels natural, like Claude typing)
    lines = content.split("\n")
    chunk = []
    for i, line in enumerate(lines):
        chunk.append(line)
        if len(chunk) >= 3 or i == len(lines) - 1:
            socketio.emit("code_stream_chunk", {
                "filename": filename,
                "lines":    chunk,
                "done":     i == len(lines) - 1,
            })
            chunk = []
            time.sleep(0.04)
    socketio.emit("code_stream_end", {"filename": filename, "lines": len(lines)})


@app.route('/api/health')
def api_health():
    """Self-healing agent status — used by HUD health indicator."""
    try:
        from brain.self_healing import get_status
        return jsonify(get_status())
    except Exception as e:
        return jsonify({"error": str(e), "running": False}), 500


@app.route('/api/extension/summary', methods=['GET'])
def api_extension_summary():
    """Return browser defense extension status and threat summary."""
    try:
        from plugins.browser_defense import get_defense_status_dict, get_browser_defense_summary
        status_dict = get_defense_status_dict()
        status_dict["textSummary"] = get_browser_defense_summary()
        return jsonify(status_dict)
    except Exception as e:
        return jsonify({"error": str(e), "ok": False}), 500


@app.route('/api/extension/sync', methods=['POST'])
def api_extension_sync():
    """Accept security events synced directly from the browser extension."""
    try:
        data = request.get_json(silent=True) or {}
        # Also sync to backend gateway if online
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://127.0.0.1:8787/api/sync",
                data=json.dumps(data).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=1.0)
        except Exception:
            pass
        return jsonify({"ok": True, "synced": True})
    except Exception as e:
        return jsonify({"error": str(e), "ok": False}), 400



@app.route('/api/project', methods=['GET','POST'])
@_api_auth_required
def api_project():
    from flask import request, jsonify
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        desc = data.get('request','').strip()
        if not desc or len(desc) < 10:
            return jsonify({'error': 'Request must be at least 10 characters'}), 400

        from brain.project_agent import run_requirements, load_state, PHASE_IDLE
        state = load_state()
        if state.get("phase") != PHASE_IDLE:
            return jsonify({
                'ok': False,
                'error': 'project_in_progress',
                'phase': state.get('phase'),
                'message': 'A project is already active. Please complete or reset it first.'
            }), 409

        resp, new_state = run_requirements(desc, notify_fn=send_project_notify)
        return jsonify({
            'status': 'requirements_pending',
            'phase': new_state.get('phase'),
            'message': resp,
            'approval_token': new_state.get('pending_approval_token')
        })
    return jsonify({'status': 'ready'})


@app.route('/api/project/pause', methods=['POST'])
@_api_auth_required
def api_project_pause():
    from brain.project_agent import toggle_pause, is_paused
    state = toggle_pause()
    return jsonify({'state': state, 'paused': is_paused()})

@app.route('/api/project/status', methods=['GET'])
def api_project_status():
    from brain.project_agent import is_paused, _build_active
    return jsonify({'paused': is_paused(), 'active': _build_active})

# ── Phase state ────────────────────────────────────────────────────
@app.route('/api/project/state', methods=['GET'])
def api_project_state():
    """Return current phase + label so HUD can update the phase indicator."""
    try:
        from brain.project_agent import load_state, get_phase_label
        state = load_state()
        return jsonify({
            'phase':       state.get('phase', 'idle'),
            'phase_label': get_phase_label(),
            'progress':    state.get('progress', 0),
            'request':     state.get('request', ''),
        })
    except Exception as e:
        log.error(f'/api/project/state 500: {e}', exc_info=True)
        return jsonify({
            'phase': 'idle', 'phase_label': 'READY',
            'progress': 0, 'request': '', 'error': str(e),
        }), 500

@app.route('/api/project/reset', methods=['POST'])
@_api_auth_required
def api_project_reset():
    """Reset project state so user can start a new project."""
    from brain.project_agent import reset_state
    reset_state()
    socketio.emit('project_phase', {'phase': 'idle', 'label': 'READY'})
    return jsonify({'status': 'reset'})

# ── Approve phase ──────────────────────────────────────────────────
@app.route('/api/project/approve', methods=['POST'])
@_api_auth_required
def api_project_approve():
    """User tapped Approve — advance the phase."""
    try:
        from brain.project_agent import (
            approve, run_architecture, run_layout,
            create_project_async, load_state, get_phase_label, PHASE_DEV
        )

        data = request.get_json(silent=True) or {}
        token = data.get('token') or data.get('approval_token')

        def _notify(text):
            try: send_project_notify(text)
            except Exception as _e: log.debug(f'approve _notify: {_e}')

        resp_text, state, next_action = approve(token=token, notify_fn=_notify)
        _notify(resp_text)

        if "⛔ Approval rejected:" in resp_text:
            return jsonify({'ok': False, 'error': resp_text}), 403

        try:
            socketio.emit('project_phase', {
                'phase': state.get('phase'),
                'label': get_phase_label(),
            })
        except Exception as _e:
            log.debug(f'approve phase emit: {_e}')

        if next_action == 'architecture':
            def _bg():
                try:
                    resp, st = run_architecture(notify_fn=_notify)
                    socketio.emit('project_phase', {'phase': st['phase'], 'label': get_phase_label()})
                    socketio.emit('project_plan', {'content': resp})
                except Exception as _e:
                    log.error(f'run_architecture bg: {_e}', exc_info=True)
                    _notify(f'❌ Architecture failed: {_e}')
            socketio.start_background_task(_bg)

        elif next_action == 'layout':
            def _bg():
                try:
                    resp, st = run_layout(notify_fn=_notify)
                    socketio.emit('project_phase', {'phase': st['phase'], 'label': get_phase_label()})
                    socketio.emit('project_plan', {'content': resp})
                except Exception as _e:
                    log.error(f'run_layout bg: {_e}', exc_info=True)
                    _notify(f'❌ Layout failed: {_e}')
            socketio.start_background_task(_bg)

        elif next_action == 'development':
            proj_request = state.get('request', '')
            dev_token = state.get('dev_auth_token')

            def sfn(event, sdata):
                try:
                    if event == 'stream_start':
                        socketio.emit('code_stream_start', {
                            'filename': sdata.get('file', 'unknown'),
                            'file_num': sdata.get('num', 0),
                            'total':    sdata.get('total', 0),
                            'lang':     sdata.get('lang', 'text'),
                        })
                    elif event == 'stream_chunk':
                        socketio.emit('code_stream_chunk', {
                            'filename': sdata.get('file', 'unknown'),
                            'lines':    sdata.get('chunk', '').split('\n'),
                            'done':     False,
                        })
                    elif event == 'stream_end':
                        socketio.emit('code_stream_end', {
                            'filename': sdata.get('file', 'unknown'),
                            'lines':    sdata.get('lines', 0),
                        })
                except Exception as _e:
                    log.debug(f'approve sfn: {_e}')

            create_project_async(proj_request, notify_fn=_notify, stream_fn=sfn, auth_token=dev_token)

        return jsonify({'status': 'ok', 'next': next_action})

    except Exception as e:
        log.error(f'/api/project/approve 500: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500


# ── Project chat (plan/debug/questions) ───────────────────────────
@app.route('/api/project/chat', methods=['POST'])
@_api_auth_required
def api_project_chat():
    """
    Handle all PROJECT tab text input — dispatches to:
    - run_requirements() for a new project description
    - project_chat() for questions, change requests, approvals
    """
    try:
        data = request.get_json(silent=True) or {}
        msg  = data.get('message', '').strip()
        if not msg:
            return jsonify({'error': 'Empty message'}), 400

        from brain.project_agent import (
            run_requirements, project_chat, load_state,
            get_phase_label, PHASE_IDLE
        )
        state = load_state()
        phase = state.get('phase', PHASE_IDLE)

        def _emit_phase(ph):
            try:
                socketio.emit('project_phase', {
                    'phase': ph,
                    'label': get_phase_label(),
                })
            except Exception as _e:
                log.debug(f'_emit_phase: {_e}')

        def _emit_plan(content):
            try:
                socketio.emit('project_plan', {'content': content})
            except Exception as _e:
                log.debug(f'_emit_plan: {_e}')

        def _notify(text):
            """Safe notify — never raises, works from background thread."""
            try:
                send_project_notify(text)
            except Exception as _e:
                log.debug(f'_notify: {_e}')

        if phase == PHASE_IDLE:
            # ── New project: run Phase 1 requirements analysis ──────
            def _bg_req():
                try:
                    resp, st = run_requirements(msg, notify_fn=_notify)
                    _emit_phase(st.get('phase', phase))
                    _emit_plan(resp)
                except Exception as _e:
                    log.error(f'run_requirements failed: {_e}', exc_info=True)
                    _notify(f'❌ Requirements analysis failed: {_e}')
            socketio.start_background_task(_bg_req)
            return jsonify({'status': 'started',
                            'message': '💠 Analysing your project...'})

        else:
            # ── In-progress: chat / approve / change request ─────────
            def _bg_chat():
                try:
                    resp, next_action = project_chat(msg, notify_fn=_notify)
                    _emit_phase(load_state().get('phase', phase))
                    _emit_plan(resp)

                    if next_action == 'architecture':
                        from brain.project_agent import run_architecture
                        resp2, st2 = run_architecture(notify_fn=_notify)
                        _emit_phase(st2.get('phase', phase))
                        _emit_plan(resp2)

                    elif next_action == 'layout':
                        from brain.project_agent import run_layout
                        resp2, st2 = run_layout(notify_fn=_notify)
                        _emit_phase(st2.get('phase', phase))
                        _emit_plan(resp2)

                    elif next_action == 'development':
                        from brain.project_agent import create_project_async, load_state as _ls

                        def sfn(event, sdata):
                            try:
                                if event == 'stream_start':
                                    socketio.emit('code_stream_start', {
                                        'filename': sdata.get('file', 'unknown'),
                                        'file_num': sdata.get('num', 0),
                                        'total':    sdata.get('total', 0),
                                        'lang':     sdata.get('lang', 'text'),
                                    })
                                elif event == 'stream_chunk':
                                    socketio.emit('code_stream_chunk', {
                                        'filename': sdata.get('file', 'unknown'),
                                        'lines':    sdata.get('chunk', '').split('\n'),
                                        'done':     False,
                                    })
                                elif event == 'stream_end':
                                    socketio.emit('code_stream_end', {
                                        'filename': sdata.get('file', 'unknown'),
                                        'lines':    sdata.get('lines', 0),
                                    })
                            except Exception as _e:
                                log.debug(f'sfn: {_e}')

                        create_project_async(
                            _ls().get('request', ''),
                            notify_fn=_notify,
                            stream_fn=sfn,
                            auth_token=_ls().get('dev_auth_token'),
                        )
                except Exception as _e:
                    log.error(f'project_chat bg failed: {_e}', exc_info=True)
                    _notify(f'❌ Error: {_e}')

            socketio.start_background_task(_bg_chat)
            return jsonify({'status': 'started', 'message': '⚙️ Processing...'})

    except Exception as e:
        log.error(f'/api/project/chat 500: {e}', exc_info=True)
        return jsonify({'error': str(e)}), 500



@app.route('/favicon.ico')
def favicon():
    return '', 204

def start_hud_server():
    threading.Thread(target=_monitor, daemon=True, name="Metrics").start()
    log.info(f"HUD → http://localhost:{HUD_PORT}")
    socketio.run(app, host=HUD_HOST, port=HUD_PORT, debug=False, allow_unsafe_werkzeug=True)
