import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def has_trigger(text: str, trigger_phrases: list[str]) -> bool:
    lower = text.lower()
    for phrase in trigger_phrases:
        if phrase.lower() in lower:
            return True
    if re.search(r"\bclaude\s+\w+", lower):
        return True
    return False


def find_project_dir(text: str, projects_root: str) -> Path | None:
    root = Path(projects_root).expanduser()
    if not root.exists():
        logger.warning(f"Projects root does not exist: {root}")
        return None

    dirs = [d for d in root.iterdir() if d.is_dir()]
    lower_text = text.lower()

    # PRIMARY: fuzzy name match — find earliest occurrence in text
    best: tuple[int, Path] | None = None
    for d in dirs:
        name_lower = d.name.lower()
        idx = lower_text.find(name_lower)
        if idx != -1:
            if best is None or idx < best[0]:
                best = (idx, d)
    if best is not None:
        logger.info(f"Matched project dir by name: {best[1]}")
        return best[1]

    # FALLBACK: explicit keyword patterns
    patterns = [
        r'working in\s+["\']?([\w\-\.]+)["\']?',
        r'in the\s+([\w\-]+)\s+(?:folder|directory|project|repo)',
    ]
    for pattern in patterns:
        match = re.search(pattern, lower_text, re.IGNORECASE)
        if match:
            folder_name = match.group(1)
            candidate = root / folder_name
            if candidate.exists():
                logger.info(f"Matched project dir by keyword: {candidate}")
                return candidate

    logger.info("No project directory matched")
    return None
