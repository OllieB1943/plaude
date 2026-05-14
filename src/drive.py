import json
import logging
import re
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import io

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
SUPPORTED_MIMETYPES = {
    "text/plain",
    "text/markdown",
    "application/json",
    "application/vnd.google-apps.document",
    "application/x-subrip",
}
SUPPORTED_EXTENSIONS = {".txt", ".md", ".srt", ".json", ".docx"}

_service = None


def _get_service():
    global _service
    if _service is not None:
        return _service

    token_path = Path(__file__).parent.parent / "token.json"
    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())

    _service = build("drive", "v3", credentials=creds)
    return _service


def list_new_files(folder_id: str, known_ids: set) -> list[dict]:
    results = []
    try:
        service = _get_service()
        query = f"'{folder_id}' in parents and trashed = false"
        response = (
            service.files()
            .list(
                q=query,
                fields="files(id,name,mimeType,createdTime,webViewLink)",
                orderBy="createdTime desc",
                pageSize=50,
            )
            .execute()
        )
        for f in response.get("files", []):
            if f["id"] in known_ids:
                continue
            ext = Path(f["name"]).suffix.lower()
            mime = f.get("mimeType", "")
            if mime in SUPPORTED_MIMETYPES or ext in SUPPORTED_EXTENSIONS:
                results.append(f)
    except Exception as e:
        logger.error(f"Error listing Drive files: {e}")
    return results


def download_file(file_id: str, mime_type: str = "", name: str = "") -> str:
    try:
        service = _get_service()
        ext = Path(name).suffix.lower() if name else ""

        if mime_type == "application/vnd.google-apps.document":
            response = (
                service.files()
                .export(fileId=file_id, mimeType="text/plain")
                .execute()
            )
            return response.decode("utf-8") if isinstance(response, bytes) else response

        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        content = buf.getvalue().decode("utf-8", errors="replace")

        if ext == ".json" or mime_type == "application/json":
            return _extract_json_transcript(content)
        if ext == ".srt":
            return _strip_srt_timestamps(content)

        return content
    except Exception as e:
        logger.error(f"Error downloading file {file_id}: {e}")
        return ""


def _extract_json_transcript(content: str) -> str:
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            for key in ("transcript", "text", "content", "body"):
                if key in data and isinstance(data[key], str):
                    return data[key]
        return content
    except json.JSONDecodeError:
        return content


def _strip_srt_timestamps(content: str) -> str:
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if re.match(r"^\d+$", line):
            continue
        if re.match(r"\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}", line):
            continue
        lines.append(line)
    return "\n".join(l for l in lines if l).strip()


def load_processed_ids(processed_ids_file: str) -> set:
    path = Path(processed_ids_file).expanduser()
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text()))
    except Exception as e:
        logger.error(f"Error loading processed IDs: {e}")
        return set()


def save_processed_ids(ids: set, processed_ids_file: str) -> None:
    path = Path(processed_ids_file).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(list(ids)))
    except Exception as e:
        logger.error(f"Error saving processed IDs: {e}")
