#!/usr/bin/env python3
"""Plaude Code — one-time setup wizard."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def check_only() -> None:
    """Import all src modules and exit — used by CI / --check flag."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from src import drive, detector, tunnel, bridge, watcher  # noqa: F401
    print("✓ All imports OK")
    sys.exit(0)


def banner(text: str) -> None:
    print(f"\n{'─' * 50}")
    print(f"  {text}")
    print(f"{'─' * 50}")


def require_python() -> None:
    banner("Checking Python version")
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        print(f"✗ Python 3.10+ required. You have {major}.{minor}.")
        sys.exit(1)
    print(f"✓ Python {major}.{minor}")


def check_tool(name: str, install_hint: str) -> None:
    if shutil.which(name):
        print(f"✓ {name} found")
    else:
        print(f"⚠  {name} not found. {install_hint}")


def require_credentials() -> Path:
    banner("Google OAuth setup")
    creds_path = PROJECT_ROOT / "credentials.json"

    if not creds_path.exists():
        print("You need a Google OAuth 2.0 credentials file.")
        print()
        print("Steps:")
        print("  1. Go to https://console.cloud.google.com/")
        print("  2. Create or select a project")
        print("  3. Enable the Google Drive API")
        print("  4. Go to APIs & Services → Credentials")
        print("  5. Create credentials → OAuth 2.0 Client ID → Desktop app")
        print("  6. Download the JSON and save it as:")
        print(f"     {creds_path}")
        print()
        input("Press Enter once credentials.json is in place...")

    if not creds_path.exists():
        print("✗ credentials.json still not found. Exiting.")
        sys.exit(1)

    print("✓ credentials.json found")
    return creds_path


def run_oauth(creds_path: Path) -> None:
    token_path = PROJECT_ROOT / "token.json"
    if token_path.exists():
        print("✓ token.json already exists — skipping OAuth flow")
        return

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("✗ google-auth-oauthlib not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    print("Starting OAuth flow — a browser window will open...")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    print("✓ token.json saved")


def ask_folder_id() -> str:
    banner("Google Drive folder")
    print("Open Google Drive in your browser and navigate to the folder")
    print("where your Plaud transcripts are saved.")
    print("Copy the folder ID from the URL:")
    print("  https://drive.google.com/drive/folders/<FOLDER_ID>")
    print()

    while True:
        folder_id = input("Paste folder ID: ").strip()
        if not folder_id:
            print("Folder ID cannot be empty.")
            continue

        print(f"Verifying access to folder {folder_id}...")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_path = PROJECT_ROOT / "token.json"
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            service = build("drive", "v3", credentials=creds)
            service.files().get(fileId=folder_id).execute()
            print("✓ Folder accessible")
            return folder_id
        except Exception as e:
            print(f"✗ Could not access folder: {e}")
            retry = input("Try a different folder ID? [y/N]: ").strip().lower()
            if retry != "y":
                sys.exit(1)


def ask_projects_root() -> str:
    banner("Projects root directory")
    print("Where are your local project directories?")
    print("Example: ~/projects  or  ~/code  or  /Users/you/dev")
    print()

    while True:
        raw = input("Projects root [~/projects]: ").strip() or "~/projects"
        path = Path(raw).expanduser()
        if path.exists() and path.is_dir():
            print(f"✓ Directory exists: {path}")
            return str(raw)
        create = input(f"Directory not found. Create it? [y/N]: ").strip().lower()
        if create == "y":
            path.mkdir(parents=True)
            print(f"✓ Created {path}")
            return str(raw)


def write_config(folder_id: str, projects_root: str) -> None:
    banner("Writing config.json")
    config_path = PROJECT_ROOT / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    config["drive_folder_id"] = folder_id
    config["projects_root"] = projects_root
    config_path.write_text(json.dumps(config, indent=2))
    print(f"✓ config.json updated")


def print_summary(folder_id: str, projects_root: str) -> None:
    banner("Setup complete!")
    print(f"  Drive folder:   {folder_id}")
    print(f"  Projects root:  {projects_root}")
    print()
    print("Next steps:")
    print("  1. Make sure cloudflared is installed")
    print("     brew install cloudflare/cloudflare/cloudflared")
    print("  2. Make sure Claude Code CLI is installed")
    print("     npm install -g @anthropic-ai/claude-code")
    print("  3. Start the bridge:")
    print("     ./start.sh")
    print()
    print("Say 'send to claude' in your next Plaud recording and watch it go!")


def main() -> None:
    if "--check" in sys.argv:
        check_only()

    print()
    print("╔════════════════════════════════════╗")
    print("║   Plaude Code — Setup Wizard        ║")
    print("╚════════════════════════════════════╝")

    sys.path.insert(0, str(PROJECT_ROOT))

    require_python()

    banner("Checking required tools")
    check_tool("claude", "Install: npm install -g @anthropic-ai/claude-code")
    check_tool("cloudflared", "Install: brew install cloudflare/cloudflare/cloudflared")

    creds_path = require_credentials()
    run_oauth(creds_path)
    folder_id = ask_folder_id()
    projects_root = ask_projects_root()
    write_config(folder_id, projects_root)
    print_summary(folder_id, projects_root)


if __name__ == "__main__":
    main()
