# CLAUDE.md — Plaude Code Build Instructions

You are building **Plaude Code** — a local automation bridge that watches a Google Drive
folder for Plaud transcripts, detects a trigger phrase, and automatically writes a CLAUDE.md
into the correct project directory then launches Claude Code in that directory.

Read every section before writing a single line of code. Build the entire project end-to-end.

---

## Project Structure

Build exactly this structure:

```
plaude-code/
├── CLAUDE.md                   ← this file (do not modify)
├── config.json                 ← user config (create with defaults)
├── requirements.txt            ← all Python dependencies
├── start.sh                    ← single boot script
├── setup.py                    ← one-time Google OAuth + config setup wizard
├── docs/
│   └── index.html              ← install guide landing page (self-contained)
└── src/
    ├── watcher.py              ← main loop: Drive polling + trigger detection
    ├── tunnel.py               ← cloudflared tunnel manager + webhook re-registration
    ├── drive.py                ← Google Drive API client (file listing, download, watch)
    ├── detector.py             ← trigger phrase detection + project directory matching
    └── bridge.py               ← CLAUDE.md writer + claude CLI launcher
```

---

## What Each File Must Do

### `config.json`
Default config. User edits this after running setup.py.

```json
{
  "drive_folder_id": "",
  "projects_root": "~/projects",
  "trigger_phrases": [
    "send to claude",
    "send this to claude",
    "claude should",
    "claude execute",
    "claude fix",
    "claude finish",
    "claude do this",
    "want this to go to claude",
    "go to claude",
    "for claude",
    "claude code this",
    "claude handle"
  ],
  "claude_cmd": "claude",
  "auto_launch": true,
  "poll_interval_seconds": 10,
  "processed_ids_file": "~/.plaude_processed.json"
}
```

---

### `requirements.txt`
```
google-auth>=2.0.0
google-auth-oauthlib>=1.0.0
google-api-python-client>=2.0.0
flask>=3.0.0
requests>=2.31.0
watchdog>=4.0.0
python-dotenv>=1.0.0
```

---

### `setup.py`
Interactive one-time setup wizard. Must:
1. Check Python version >= 3.10, exit with clear message if not
2. Check `claude` CLI is installed (`which claude`), warn if not found
3. Check `cloudflared` is installed (`which cloudflared`), warn if not found
4. Walk user through Google OAuth:
   - Print clear instructions to go to Google Cloud Console
   - Tell them exactly what to enable: Google Drive API
   - Tell them to create OAuth 2.0 credentials, download as `credentials.json`
   - Detect when `credentials.json` exists in project root
   - Run the OAuth flow, save `token.json`
5. Ask user for their Google Drive folder ID (paste from Drive URL)
   - Validate it's accessible
6. Ask user for their projects root directory
   - Validate it exists
7. Write all values to `config.json`
8. Print success summary with next steps

Must be runnable as: `python setup.py`

---

### `src/drive.py`
Google Drive API client. Must:
1. Load credentials from `token.json` (refresh if expired)
2. `list_new_files(folder_id, known_ids)` → returns list of new file metadata dicts
   - Each dict: `{id, name, mimeType, createdTime, webViewLink}`
   - Only returns files not in `known_ids` set
   - Supports txt, md, srt, json, docx mimetypes
3. `download_file(file_id)` → returns plain text content as string
   - Handle Google Docs (export as plain text)
   - Handle .txt/.md/.srt (download directly)
   - Handle .json (download and parse transcript field)
   - Handle .srt (strip timestamps, return clean text)
4. `load_processed_ids()` / `save_processed_ids(ids)` → persist to processed_ids_file
5. Never crash on a single bad file — log error and continue

---

### `src/detector.py`
Trigger detection and project directory matching. Must:

**Trigger detection:**
1. Load trigger phrases from config
2. Check all phrases (case-insensitive) against transcript text
3. Also match regex pattern: `r'\bclaude\s+\w+'` as a catch-all for "claude [any verb]"
4. Return `True` if any match found

**Project directory matching:**
1. PRIMARY — Fuzzy name match:
   - List all directories in `projects_root`
   - Lowercase all folder names
   - Check if any folder name appears anywhere in the transcript text (case-insensitive)
   - If multiple matches, pick the one that appears earliest in the text
   - Return the full `Path` to matched directory
2. FALLBACK — Explicit keyword:
   - Regex: `r'working in\s+["\']?([\w\-\.]+)["\']?'` (case-insensitive)
   - Also match: `r'in the\s+([\w\-]+)\s+(?:folder|directory|project|repo)'`
   - Extract folder name, look it up in projects_root
   - Return full `Path` if found
3. If neither matches, return `None`

---

### `src/tunnel.py`
Cloudflare Tunnel manager. Must:
1. Start `cloudflared tunnel --url http://localhost:5000` as a subprocess
2. Parse stdout to extract the assigned `*.trycloudflare.com` URL
   - Regex: `r'https://[\w\-]+\.trycloudflare\.com'`
3. Return the public URL once detected (timeout after 30s, raise if not found)
4. `get_public_url()` → returns current tunnel URL
5. `stop()` → terminate the subprocess cleanly
6. Log the URL clearly on startup: `"✓ Tunnel active: https://xxx.trycloudflare.com"`

---

### `src/bridge.py`
CLAUDE.md writer and claude CLI launcher. Must:

**`write_claude_md(transcript_text, source_filename, project_dir)`:**
Generate a `CLAUDE.md` in `project_dir` with this exact structure:

```markdown
# Claude Code Instructions
> Auto-generated by Plaude Code
> Source: {source_filename}
> Generated: {timestamp}
> Project: {project_dir}

---

## Task

The following is a voice transcript describing work to be done in this directory.
Read it carefully. Infer what needs to be built, fixed, or continued.
Execute it completely. Do not stop halfway.

**Rules:**
- Work entirely within this directory
- Find existing files before assuming they don't exist
- Make reasonable implementation decisions where the transcript is ambiguous
- After completing all tasks, write a brief DONE.md summarising every change made

---

## Transcript

{transcript_text}

---
*End of auto-generated instructions.*
```

**`launch_claude(project_dir)`:**
1. Check `claude` CLI exists, raise clear error if not
2. Run: `subprocess.Popen(["claude"], cwd=str(project_dir))`
3. Log: `"✓ Claude Code launched in {project_dir}"`
4. Do not block the watcher loop

**`write_fallback_md(transcript_text, source_filename)`:**
- Called when no project directory is detected
- Write CLAUDE.md to `~/Desktop/plaude-unmatched/{timestamp}/`
- Include a note at top: "⚠️ Project directory not detected. Move this file to the correct project and run `claude` manually."

---

### `src/watcher.py`
Main loop. Must:

1. Load config
2. Load processed IDs from disk
3. Start the tunnel (import from tunnel.py), get public URL
4. Register Google Drive push notification webhook to that URL at `/webhook` endpoint
   - Use Drive API `files.watch()` on the folder
   - Store the channel ID and expiry
5. Start a Flask server on port 5000 in a background thread:
   - `POST /webhook` → when Drive push arrives, call `check_for_new_files()`
   - `GET /health` → return `{"status": "ok"}`
6. Also run a **fallback poll every 10 seconds** checking file count:
   - If file count changed → call `check_for_new_files()`
   - This ensures nothing is missed if the webhook fires late or fails
7. `check_for_new_files()`:
   - Call `drive.list_new_files()`
   - For each new file: download text, run detector, if triggered: write CLAUDE.md + launch
   - Save processed IDs after each file
8. Handle `KeyboardInterrupt` cleanly: stop tunnel, stop observer, print goodbye
9. Renew the Drive webhook channel before it expires (channels expire after 24h max)

Print clean startup summary:
```
╔══════════════════════════════════════════╗
║   Plaude Code  v1.0                      ║
╠══════════════════════════════════════════╣
║  Drive folder:  [folder name]            ║
║  Projects root: ~/projects               ║  
║  Tunnel:        https://xxx.trycloudflare.com ║
║  Status:        Watching...              ║
╚══════════════════════════════════════════╝
```

---

### `start.sh`
```bash
#!/bin/bash
# Plaude Code — start everything
set -e

cd "$(dirname "$0")"

# Check config exists
if [ ! -f config.json ]; then
  echo "No config.json found. Run: python setup.py"
  exit 1
fi

# Check token exists
if [ ! -f token.json ]; then
  echo "Not authenticated. Run: python setup.py"
  exit 1
fi

echo "Starting Plaude Code..."
python src/watcher.py
```

Make executable: `chmod +x start.sh`

---

### `docs/index.html`
A clean, self-contained install guide landing page. Requirements:

**Design:**
- Olivander Technologies brand palette exactly:
  - Background: `#F6F5F1` (Base)
  - Text/headings: `#1C2128` (Ink)
  - Accent/buttons: `#6E56CF` (Action violet)
  - Muted text: `#889096`
  - Success indicators: `#2B7A4B`
  - Code blocks: dark background `#1C2128`, light text
- Apple-esque, clean, minimalist — OpenAI-product aesthetic
- No external dependencies — zero CDN links, pure HTML/CSS/JS
- Mobile responsive
- No captions anywhere

**Content — exactly these sections in order:**

1. **Hero**: "Plaude Code" as title, subtitle: "Voice-to-Claude automation. Say it. It builds it."

2. **Prerequisites** (numbered list with status indicators):
   - Python 3.10+
   - Claude Code CLI (`npm install -g @anthropic-ai/claude-code`)
   - cloudflared (`brew install cloudflare/cloudflare/cloudflared` / winget)
   - A Google account
   - A Plaud device with Google Drive sync enabled

3. **Step-by-step install** (large numbered steps, each with exact terminal commands in styled code blocks):
   - Step 1: Clone the repo
   - Step 2: Install dependencies (`pip install -r requirements.txt`)
   - Step 3: Run setup wizard (`python setup.py`)
   - Step 4: Configure Plaud to sync to Drive (link to Plaud docs)
   - Step 5: Start the bridge (`./start.sh`)

4. **How it works** (3-column visual flow):
   `Record on Plaud` → `Say "send to claude"` → `Claude Code executes`

5. **Trigger phrases** — list of all supported phrases in a clean tag/pill UI

6. **Troubleshooting** — collapsible FAQ items:
   - "cloudflared not found"
   - "Google auth failed"  
   - "Project directory not detected"
   - "claude command not found"

7. **Footer**: Olivander Technologies, small

---

## Build Order

Execute in this order:
1. Create all directories and empty files
2. Write `requirements.txt`
3. Write `config.json`
4. Write `src/drive.py`
5. Write `src/detector.py`
6. Write `src/tunnel.py`
7. Write `src/bridge.py`
8. Write `src/watcher.py`
9. Write `setup.py`
10. Write `start.sh` and chmod +x
11. Write `docs/index.html`
12. Write `DONE.md` summarising every file created

---

## Quality Checks

After building, verify:
- [ ] `python setup.py --check` runs without import errors
- [ ] `python -c "from src import drive, detector, tunnel, bridge, watcher"` succeeds
- [ ] `docs/index.html` opens in browser with no broken layout
- [ ] All files exist at correct paths
- [ ] `start.sh` is executable

---

## Important Constraints

- All file I/O uses `pathlib.Path`, never raw string concatenation
- All Drive API calls wrapped in try/except, errors logged not raised
- Config loaded once at startup, not re-read on every poll
- No hardcoded paths — everything comes from config.json
- Python 3.10+ features are fine (match statements, `Path | None` types)
- Do not add any dependencies not in requirements.txt
- The Flask server and the polling loop run in separate threads — use threading, not asyncio
- cloudflared subprocess must be killed cleanly on exit (atexit or signal handler)
