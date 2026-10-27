"""Secure local pattern-lock storage for E.D.I.T.H. two-factor access."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path


PATTERN_FILE = Path(__file__).resolve().parent / "pattern_lock.json"
ITERATIONS = 310_000


def _normalize(pattern) -> str:
    if isinstance(pattern, str):
        values = [int(c) for c in pattern if c.isdigit()]
    elif isinstance(pattern, list):
        values = [int(value) for value in pattern]
    else:
        raise ValueError("Pattern must be a list of points.")
    if len(values) < 4:
        raise ValueError("Connect at least four points.")
    if any(value < 1 or value > 9 for value in values):
        raise ValueError("Pattern points must be between 1 and 9.")
    if len(set(values)) != len(values):
        raise ValueError("A point cannot be used twice.")
    return "-".join(str(value) for value in values)


def is_configured() -> bool:
    return PATTERN_FILE.is_file()


def configure(pattern, overwrite: bool = False) -> None:
    if is_configured() and not overwrite:
        raise RuntimeError("Pattern lock is already configured.")
    normalized = _normalize(pattern)
    salt = secrets.token_bytes(24)
    digest = hashlib.pbkdf2_hmac("sha256", normalized.encode(), salt, ITERATIONS)
    payload = {"version": 1, "algorithm": "pbkdf2-sha256", "iterations": ITERATIONS,
               "salt": salt.hex(), "digest": digest.hex()}
    temp = PATTERN_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temp, PATTERN_FILE)


def replace(pattern) -> None:
    """Replace the credential after the caller has authenticated the session."""
    configure(pattern, overwrite=True)


def change(current_pattern, new_pattern) -> bool:
    """Verify current pattern before replacing with new pattern.
    Returns True on success, False if current_pattern does not match.
    Raises ValueError on invalid pattern syntax.
    """
    if not is_configured():
        raise RuntimeError("Pattern lock is not configured.")
    if not verify(current_pattern):
        return False
    configure(new_pattern, overwrite=True)
    return True


def verify(pattern) -> bool:
    if not is_configured():
        return False
    normalized = _normalize(pattern)
    payload = json.loads(PATTERN_FILE.read_text(encoding="utf-8"))
    salt = bytes.fromhex(payload["salt"])
    expected = bytes.fromhex(payload["digest"])
    actual = hashlib.pbkdf2_hmac("sha256", normalized.encode(), salt,
                                 int(payload.get("iterations", ITERATIONS)))
    return hmac.compare_digest(actual, expected)
