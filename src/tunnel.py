import atexit
import logging
import re
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

_proc: subprocess.Popen | None = None
_public_url: str | None = None


def start() -> str:
    global _proc, _public_url

    _proc = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:5000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    atexit.register(stop)

    deadline = time.time() + 30
    url_pattern = re.compile(r"https://[\w\-]+\.trycloudflare\.com")

    for line in _proc.stdout:
        match = url_pattern.search(line)
        if match:
            _public_url = match.group(0)
            logger.info(f"✓ Tunnel active: {_public_url}")
            # Drain stdout in background so the process doesn't block
            threading.Thread(target=_drain, daemon=True).start()
            return _public_url
        if time.time() > deadline:
            break

    raise RuntimeError("cloudflared did not produce a tunnel URL within 30 seconds")


def _drain():
    if _proc and _proc.stdout:
        for _ in _proc.stdout:
            pass


def get_public_url() -> str | None:
    return _public_url


def stop():
    global _proc
    if _proc is not None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()
        _proc = None
        logger.info("Tunnel stopped")
