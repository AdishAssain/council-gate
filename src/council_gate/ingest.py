"""Load an artifact from disk into review-ready text.

Plain-text formats (md, diff, source code, etc.) are read verbatim so diff
syntax and code fences survive untouched. Office formats (docx, pdf, pptx,
xlsx, html) are converted to markdown via MarkItDown.
"""
from pathlib import Path

_BINARY_DOC_SUFFIXES = frozenset({
    ".docx", ".doc", ".pdf", ".pptx", ".ppt", ".xlsx", ".xls",
    ".odt", ".rtf", ".epub",
})

# Suffixes we know we don't support yet — give a clean message instead of a stack trace.
_UNSUPPORTED_SUFFIXES = {
    ".pages": "Apple Pages files aren't supported. Open in Pages and File → Export To → Word (.docx).",
    ".numbers": "Apple Numbers files aren't supported. Open in Numbers and File → Export To → Excel (.xlsx).",
    ".key": "Keynote files aren't supported. Open in Keynote and File → Export To → PowerPoint (.pptx).",
    ".gdoc": "Google Doc shortcuts aren't supported. In Google Docs: File → Download → .docx.",
}


class IngestError(Exception):
    """User-facing artifact load failure. The message is safe to print verbatim."""


def load_artifact(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in _UNSUPPORTED_SUFFIXES:
        raise IngestError(_UNSUPPORTED_SUFFIXES[suffix])

    if suffix in _BINARY_DOC_SUFFIXES:
        _validate_magic(path, suffix)
        return _convert_with_markitdown(path, suffix)

    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return _convert_with_markitdown(path, suffix)


def _convert_with_markitdown(path: Path, suffix: str) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as e:
        raise IngestError(
            "Document conversion library (markitdown) isn't installed. "
            "Reinstall council-gate: `council-gate update`"
        ) from e

    try:
        result = MarkItDown(enable_plugins=False).convert(str(path))
    except FileNotFoundError as e:
        raise IngestError(f"File not found: {path}") from e
    except PermissionError as e:
        raise IngestError(
            f"Can't read {path.name} — permission denied. "
            "Is the file open in another app? Close it and try again."
        ) from e
    except Exception as e:
        kind = suffix.lstrip(".") or "file"
        hint = _hint_for(suffix)
        raise IngestError(
            f"Couldn't read this {kind}. {hint} (technical reason: {type(e).__name__})"
        ) from e

    text = result.text_content or ""
    if not text.strip():
        raise IngestError(
            f"{path.name} converted to an empty document — is it password-protected, "
            f"a scanned image, or an empty file?"
        )
    return text


_ZIP_BASED = {".docx", ".pptx", ".xlsx", ".odt", ".epub"}


def _validate_magic(path: Path, suffix: str) -> None:
    """Catch mis-named files (e.g. a .pages renamed to .docx) before markitdown
    silently treats them as plain text."""
    try:
        head = path.read_bytes()[:8]
    except OSError as e:
        raise IngestError(f"Can't open {path.name}: {e}") from e
    if not head:
        raise IngestError(f"{path.name} is empty.")
    if suffix in _ZIP_BASED and not head.startswith(b"PK\x03\x04"):
        raise IngestError(
            f"{path.name} doesn't look like a real {suffix} file (wrong file signature). "
            "It may be renamed from another format — open it in its source app and re-export."
        )
    if suffix == ".pdf" and not head.startswith(b"%PDF"):
        raise IngestError(
            f"{path.name} doesn't look like a real PDF (missing %PDF header). "
            "Re-export it from the source app."
        )


def _hint_for(suffix: str) -> str:
    if suffix in {".docx", ".doc"}:
        return "If it's open in Word, close it and rerun. If it's a .doc (old format), open it in Word and Save As .docx."
    if suffix == ".pdf":
        return "If the PDF is scanned (images, not text), council-gate can't read it — export the source as .docx or .md instead."
    if suffix in {".pptx", ".ppt"}:
        return "Try exporting the deck as .pdf or .docx and rerun."
    if suffix in {".xlsx", ".xls"}:
        return "If the spreadsheet is open in Excel, close it and rerun."
    return "Try opening the file and re-saving it, or convert it to .md or .docx."
