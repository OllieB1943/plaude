#!/usr/bin/env python3
"""Plaude — one-time setup wizard."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
WHITE  = "\033[97m"
BG_DARK = "\033[48;5;235m"

def c(text, *codes): return "".join(codes) + text + RESET
def ok(msg):   print(f"  {c('✓', GREEN, BOLD)} {msg}")
def warn(msg): print(f"  {c('⚠', YELLOW, BOLD)} {msg}")
def err(msg):  print(f"  {c('✗', RED, BOLD)} {msg}")
def info(msg): print(f"  {c('→', CYAN)} {msg}")
def dim(msg):  print(c(f"  {msg}", DIM))


def clear_line(): print("\033[F\033[K", end="")


def print_logo() -> None:
    print()
    print(c("  ██████╗ ██╗      █████╗ ██╗   ██╗██████╗ ███████╗", CYAN, BOLD))
    print(c("  ██╔══██╗██║     ██╔══██╗██║   ██║██╔══██╗██╔════╝", CYAN, BOLD))
    print(c("  ██████╔╝██║     ███████║██║   ██║██║  ██║█████╗  ", CYAN, BOLD))
    print(c("  ██╔═══╝ ██║     ██╔══██║██║   ██║██║  ██║██╔══╝  ", CYAN, BOLD))
    print(c("  ██║     ███████╗██║  ██║╚██████╔╝██████╔╝███████╗", CYAN, BOLD))
    print(c("  ╚═╝     ╚══════╝╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝", CYAN, BOLD))
    print()
    print(c("  Voice → Claude. Say it. It builds it.", DIM))
    print()
    print(c("  " + "─" * 54, DIM))
    print(c("  Setup Wizard", BOLD, WHITE) + c("  ·  v1.0", DIM))
    print(c("  " + "─" * 54, DIM))
    print()


def section(title: str, step: int, total: int) -> None:
    print()
    print(c(f"  Step {step}/{total}", DIM) + "  " + c(title, BOLD, WHITE))
    print(c("  " + "─" * 40, DIM))


def spinner(msg: str, duration: float = 0.8) -> None:
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end = time.time() + duration
    i = 0
    while time.time() < end:
        print(f"\r  {c(frames[i % len(frames)], CYAN)} {msg}", end="", flush=True)
        time.sleep(0.08)
        i += 1
    print("\r" + " " * (len(msg) + 6) + "\r", end="")


def check_only() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from src import drive, detector, tunnel, bridge, watcher  # noqa: F401
    ok("All imports OK")
    sys.exit(0)


def require_python() -> None:
    major, minor = sys.version_info[:2]
    if major < 3 or (major == 3 and minor < 10):
        err(f"Python 3.10+ required — you have {major}.{minor}")
        info("Install via: brew install python@3.13")
        sys.exit(1)
    ok(f"Python {major}.{minor}")


def check_tool(name: str, install_hint: str) -> bool:
    if shutil.which(name):
        ok(f"{name}")
        return True
    else:
        warn(f"{name} not found")
        dim(f"   Install: {install_hint}")
        return False


def require_credentials() -> Path:
    creds_path = PROJECT_ROOT / "credentials.json"

    if not creds_path.exists():
        print()
        print(c("  credentials.json not found.", YELLOW))
        print()
        print(c("  Follow these steps:", BOLD))
        print()
        info("Go to https://console.cloud.google.com/")
        info("Select your project (or create one)")
        info("Search for 'Google Drive API' → Enable it")
        info("Go to APIs & Services → Credentials")
        info("Click Create Credentials → OAuth 2.0 Client ID")
        info("Application type → Desktop app → Create")
        info("Click Download JSON → save as  credentials.json")
        info(f"Move the file to:  {creds_path}")
        print()
        input(c("  Press Enter once credentials.json is in place…", DIM))
        print()

    if not creds_path.exists():
        err("credentials.json still not found. Exiting.")
        sys.exit(1)

    ok("credentials.json")
    return creds_path


def run_oauth(creds_path: Path) -> None:
    token_path = PROJECT_ROOT / "token.json"
    if token_path.exists():
        ok("token.json already exists — skipping OAuth")
        return

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        err("google-auth-oauthlib not installed")
        info("Run: pip install -r requirements.txt")
        sys.exit(1)

    print()
    info("A browser window will open for Google sign-in…")
    print()
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    ok("Authenticated — token.json saved")


def ask_folder_id() -> str:
    print()
    print(c("  Find your Plaud Drive folder ID:", BOLD))
    print()
    info("Open Google Drive → find the folder Plaud syncs to")
    info("Click the folder — copy the ID from the URL:")
    dim("   https://drive.google.com/drive/folders/  ← this part →")
    print()

    while True:
        folder_id = input(c("  Folder ID: ", CYAN)).strip()
        if not folder_id:
            warn("Folder ID cannot be empty")
            continue

        spinner(f"Verifying folder access…")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            token_path = PROJECT_ROOT / "token.json"
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            service = build("drive", "v3", credentials=creds)
            meta = service.files().get(fileId=folder_id, fields="name").execute()
            ok(f"Folder found: \"{meta.get('name', folder_id)}\"")
            return folder_id
        except Exception as e:
            err(f"Could not access folder: {e}")
            retry = input(c("  Try a different ID? [y/N]: ", DIM)).strip().lower()
            if retry != "y":
                sys.exit(1)


def ask_projects_root() -> str:
    print()
    print(c("  Where are your local project folders?", BOLD))
    dim("   This is the directory that contains all your repos/projects.")
    dim("   Example: ~/code  ~/projects  ~/dev  ~/work")
    print()

    while True:
        raw = input(c("  Projects root [~/code]: ", CYAN)).strip() or "~/code"
        path = Path(raw).expanduser()
        if path.exists() and path.is_dir():
            count = sum(1 for p in path.iterdir() if p.is_dir())
            ok(f"{path}  ({count} directories found)")
            return str(raw)
        create = input(c(f"  {path} doesn't exist. Create it? [y/N]: ", YELLOW)).strip().lower()
        if create == "y":
            path.mkdir(parents=True)
            ok(f"Created {path}")
            return str(raw)


def write_config(folder_id: str, projects_root: str) -> None:
    config_path = PROJECT_ROOT / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    config["drive_folder_id"] = folder_id
    config["projects_root"] = projects_root
    config_path.write_text(json.dumps(config, indent=2))
    ok("config.json saved")


def print_summary(folder_id: str, projects_root: str) -> None:
    print()
    print(c("  " + "─" * 54, DIM))
    print()
    print(c("  ✓ Setup complete!", GREEN, BOLD))
    print()
    print(c("  Config", DIM))
    dim(f"   Drive folder:   {folder_id}")
    dim(f"   Projects root:  {projects_root}")
    print()
    print(c("  Next steps", BOLD))
    print()
    info("Start Plaude:")
    print(c("     ./start.sh", CYAN, BOLD))
    print()
    info("Then make a Plaud recording and say:")
    print(c('     "send to claude — fix the auth bug in my-app"', CYAN))
    print()
    print(c("  " + "─" * 54, DIM))
    print()


def main() -> None:
    if "--check" in sys.argv:
        check_only()

    print_logo()

    sys.path.insert(0, str(PROJECT_ROOT))
    TOTAL = 5

    section("Environment check", 1, TOTAL)
    require_python()
    check_tool("claude", "npm install -g @anthropic-ai/claude-code")
    check_tool("cloudflared", "brew install cloudflare/cloudflare/cloudflared")

    section("Google OAuth credentials", 2, TOTAL)
    creds_path = require_credentials()

    section("Google sign-in", 3, TOTAL)
    run_oauth(creds_path)

    section("Google Drive folder", 4, TOTAL)
    folder_id = ask_folder_id()

    section("Projects root", 5, TOTAL)
    projects_root = ask_projects_root()

    write_config(folder_id, projects_root)
    print_summary(folder_id, projects_root)


if __name__ == "__main__":
    main()
