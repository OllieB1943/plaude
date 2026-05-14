import json
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, request

from . import drive, detector, tunnel, bridge

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global state set at startup
_config: dict = {}
_processed_ids: set = set()
_ids_lock = threading.Lock()
_file_count: int = 0
_channel_id: str | None = None
_channel_expiry: int = 0
_changes_page_token: str | None = None


# ── Config ────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    config_path = Path(__file__).parent.parent / "config.json"
    return json.loads(config_path.read_text())


# ── Drive webhook registration ────────────────────────────────────────────────

def _get_drive_service():
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = Path(__file__).parent.parent / "token.json"
    creds = Credentials.from_authorized_user_file(
        str(token_path), ["https://www.googleapis.com/auth/drive.readonly"]
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def register_webhook(folder_id: str, public_url: str) -> None:
    global _channel_id, _channel_expiry, _changes_page_token
    import uuid

    try:
        service = _get_drive_service()

        # Get a start page token for the changes feed
        token_resp = service.changes().getStartPageToken().execute()
        _changes_page_token = token_resp.get("startPageToken")

        channel_id = str(uuid.uuid4())
        resp = (
            service.changes()
            .watch(
                pageToken=_changes_page_token,
                body={
                    "id": channel_id,
                    "type": "web_hook",
                    "address": f"{public_url}/webhook",
                },
            )
            .execute()
        )
        _channel_id = channel_id
        _channel_expiry = int(resp.get("expiration", 0)) // 1000  # ms → s
        logger.info(f"Drive changes webhook registered (channel {channel_id})")
    except Exception as e:
        logger.warning(f"Could not register Drive webhook (will rely on polling): {e}")


def maybe_renew_webhook(folder_id: str, public_url: str) -> None:
    if _channel_expiry and time.time() > _channel_expiry - 300:
        logger.info("Renewing Drive webhook channel...")
        register_webhook(folder_id, public_url)


# ── Core processing ───────────────────────────────────────────────────────────

def check_for_new_files() -> None:
    global _file_count
    with _ids_lock:
        known = set(_processed_ids)

    new_files = drive.list_new_files(_config["drive_folder_id"], known)
    _file_count = len(known) + len(new_files)

    for f in new_files:
        fid = f["id"]
        name = f["name"]
        mime = f.get("mimeType", "")
        logger.info(f"New file detected: {name} ({fid})")

        text = drive.download_file(fid, mime_type=mime, name=name)
        if not text:
            logger.warning(f"Empty content for {name}, skipping")
            with _ids_lock:
                _processed_ids.add(fid)
            drive.save_processed_ids(_processed_ids, _config["processed_ids_file"])
            continue

        triggered = detector.has_trigger(text, _config["trigger_phrases"])
        if triggered:
            project_dir = detector.find_project_dir(text, _config["projects_root"])
            if project_dir:
                bridge.dispatch(text, name, project_dir, _config)
            else:
                bridge.write_fallback_md(text, name)
        else:
            logger.info(f"No trigger found in {name}")

        with _ids_lock:
            _processed_ids.add(fid)
        drive.save_processed_ids(_processed_ids, _config["processed_ids_file"])


# ── Flask endpoints ───────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    threading.Thread(target=check_for_new_files, daemon=True).start()
    return "", 200


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


# ── Polling loop ──────────────────────────────────────────────────────────────

def poll_loop(interval: int, folder_id: str, public_url: str) -> None:
    while True:
        time.sleep(interval)
        try:
            current_count = len(
                drive.list_new_files(folder_id, set(_processed_ids))
            )
            if current_count > 0:
                check_for_new_files()
            maybe_renew_webhook(folder_id, public_url)
        except Exception as e:
            logger.error(f"Poll error: {e}")


# ── Startup banner ────────────────────────────────────────────────────────────

def print_banner(folder_id: str, projects_root: str, tunnel_url: str) -> None:
    print("╔══════════════════════════════════════════════════════╗")
    print("║   Plaude Code  v1.0                                  ║")
    print("╠══════════════════════════════════════════════════════╣")
    print(f"║  Drive folder:  {folder_id[:36]:<36}  ║")
    print(f"║  Projects root: {projects_root:<36}  ║")
    print(f"║  Tunnel:        {tunnel_url[:36]:<36}  ║")
    print("║  Status:        Watching...                          ║")
    print("╚══════════════════════════════════════════════════════╝")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    global _config, _processed_ids

    _config = load_config()
    _processed_ids = drive.load_processed_ids(_config["processed_ids_file"])

    public_url = tunnel.start()

    register_webhook(_config["drive_folder_id"], public_url)

    print_banner(
        _config["drive_folder_id"],
        _config["projects_root"],
        public_url,
    )

    poll_thread = threading.Thread(
        target=poll_loop,
        args=(
            _config["poll_interval_seconds"],
            _config["drive_folder_id"],
            public_url,
        ),
        daemon=True,
    )
    poll_thread.start()

    def handle_exit(sig, frame):
        print("\nShutting down Plaude Code...")
        tunnel.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    app.run(host="0.0.0.0", port=5000, threaded=True)


if __name__ == "__main__":
    main()
