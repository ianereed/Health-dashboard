"""
Shared Google OAuth2 credential helper.

Token storage priority:
  1. macOS Keychain via keyring (survives reboots, no plaintext on disk)
  2. JSON token file (fallback, always gitignored)

Both are kept in sync on every refresh or new authorization.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import keyring
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "home-tools-event-aggregator"
_HERE = Path(__file__).parent.parent  # event-aggregator/


def _resolve(path_str: str) -> Path:
    """Resolve a path relative to event-aggregator/ if not absolute."""
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else _HERE / p


def _is_headless() -> bool:
    """Detect contexts where a browser-based OAuth flow can't complete.

    Under launchd (and most non-interactive contexts) stdin is not a tty.
    `EVENT_AGG_OAUTH_INTERACTIVE=1` forces interactive even when no tty;
    `EVENT_AGG_HEADLESS=1` forces headless even on a workstation.
    """
    if os.environ.get("EVENT_AGG_OAUTH_INTERACTIVE") == "1":
        return False
    if os.environ.get("EVENT_AGG_HEADLESS") == "1":
        return True
    try:
        return not sys.stdin.isatty()
    except (ValueError, AttributeError):
        return True


def get_credentials(
    scopes: list[str],
    token_path: str,
    credentials_path: str,
    keyring_key: str,
) -> Credentials:
    """
    Load or acquire OAuth2 credentials for the given scopes.

    Tries (in order):
      1. Keyring entry for keyring_key
      2. JSON token file at token_path
      3. Refreshes if expired
      4. Runs the OAuth2 browser flow if no valid token exists

    Args:
        scopes: OAuth2 scopes to request.
        token_path: Path to token JSON file (relative to event-aggregator/ or absolute).
        credentials_path: Path to client secrets JSON from Google Cloud Console.
        keyring_key: Key name in macOS Keychain (e.g. "gmail_token", "gcal_token").

    Returns:
        Valid Credentials object.

    Raises:
        FileNotFoundError: If credentials_path doesn't exist (setup not complete).
    """
    token_file = _resolve(token_path)
    creds_file = _resolve(credentials_path)
    creds: Credentials | None = None

    # Source priority: try BOTH stores, accept the first one that yields valid
    # (or refreshable) creds. JSON file is tried first because it's the
    # load-bearing copy in our deploy pattern (scp from a workstation after
    # re-auth). The keyring is a best-effort cache that can lag — notably,
    # keyring entries are scoped to launchd's audit session and can hold a
    # stale token that's invisible from an SSH session. If we picked the
    # keyring's stale value first, refresh would fail with invalid_grant and
    # we'd never try the fresh JSON. _persist() syncs both stores on success.
    candidates: list[Credentials] = []
    if token_file.exists():
        try:
            candidates.append(Credentials.from_authorized_user_file(str(token_file), scopes))
        except Exception as exc:
            logger.debug("token file invalid for %s, ignoring: %s", keyring_key, exc)
    stored = keyring.get_password(_KEYRING_SERVICE, keyring_key)
    if stored:
        try:
            candidates.append(Credentials.from_authorized_user_info(json.loads(stored), scopes))
        except Exception as exc:
            logger.debug("keyring token invalid for %s, ignoring: %s", keyring_key, exc)

    for cand in candidates:
        if cand.valid:
            _persist(cand, token_file, keyring_key)  # sync stores
            return cand
        if cand.expired and cand.refresh_token:
            try:
                cand.refresh(Request())
            except Exception as exc:
                logger.debug("refresh failed for %s (%s), trying next source", keyring_key, exc)
                continue
            _persist(cand, token_file, keyring_key)
            return cand

    # 4. Run the OAuth2 browser flow (first-time setup or refresh failure)
    if not creds_file.exists():
        raise FileNotFoundError(
            f"Google client secrets file not found: {creds_file}\n"
            "Download it from Google Cloud Console (OAuth2 client credentials)\n"
            "and place it at that path."
        )
    if _is_headless():
        # Source name for the user — gmail_token → gmail
        source_name = keyring_key.split("_")[0]
        raise RuntimeError(
            f"Cannot start interactive Google OAuth flow for {keyring_key} in a "
            f"headless context (no tty). Re-authenticate from a workstation, then "
            f"copy credentials/{source_name}_token.json to the server. "
            f"Set EVENT_AGG_OAUTH_INTERACTIVE=1 to override."
        )
    logger.info(
        "Running Google OAuth2 flow for %s — a browser window will open", keyring_key
    )
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), scopes)
    creds = flow.run_local_server(port=0)
    _persist(creds, token_file, keyring_key)
    return creds


def _persist(creds: Credentials, token_file: Path, keyring_key: str) -> None:
    """Save credentials to both keyring and JSON file."""
    token_json = creds.to_json()
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token_json)
        token_file.chmod(0o600)
    except OSError as exc:
        logger.warning("could not write token file %s: %s", token_file, exc)
    try:
        keyring.set_password(_KEYRING_SERVICE, keyring_key, token_json)
    except Exception as exc:
        logger.warning("could not save token to keyring: %s", exc)
