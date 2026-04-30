"""NAS availability check + auto-remount via mount-nas.sh.

Loud logging on every state change so post-reboot self-heal is obvious in
the run log.
"""
from __future__ import annotations

import logging
import subprocess

import config

logger = logging.getLogger(__name__)


def _nas_available() -> bool:
    """Return True iff config.NAS_ROOT exists and looks like a directory.

    Verbatim copy of event-aggregator/writers/file_writer.py:_nas_available
    (the same defensive helper event-aggregator uses for its own NAS writes).
    Cheap; doesn't hit the network.
    """
    return config.NAS_ROOT.exists() and config.NAS_ROOT.is_dir()


def ensure_mounted() -> bool:
    """If NAS isn't reachable at NAS_ROOT, run mount-nas.sh to self-heal.

    Returns True iff after this call the NAS is available. False = bail-out
    signal for the caller (skip this watcher tick; try again next tick).
    """
    if _nas_available():
        return True

    if not config.MOUNT_HELPER.exists():
        logger.error(
            "nas-intake: NAS unavailable at %s and mount helper missing at %s — skipping tick",
            config.NAS_ROOT, config.MOUNT_HELPER,
        )
        return False

    logger.warning(
        "nas-intake: NAS unavailable at %s — running %s to self-heal",
        config.NAS_ROOT, config.MOUNT_HELPER,
    )
    try:
        result = subprocess.run(
            ["bash", str(config.MOUNT_HELPER)],
            capture_output=True, text=True,
            timeout=config.MOUNT_HELPER_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        logger.error("nas-intake: mount-nas.sh timed out after %ss — skipping tick", config.MOUNT_HELPER_TIMEOUT_S)
        return False
    except Exception as exc:
        logger.error("nas-intake: mount-nas.sh failed to invoke: %s — skipping tick", exc)
        return False

    if result.returncode != 0:
        logger.error(
            "nas-intake: mount-nas.sh exited %s — stdout=%s stderr=%s",
            result.returncode, result.stdout.strip(), result.stderr.strip(),
        )
        return False

    if _nas_available():
        logger.info("nas-intake: NAS remounted via mount-nas.sh; resuming")
        return True

    logger.error(
        "nas-intake: mount-nas.sh exited 0 but NAS still unavailable at %s — skipping tick",
        config.NAS_ROOT,
    )
    return False
