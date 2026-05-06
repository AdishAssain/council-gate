from pathlib import Path

import pytest

from council_gate.ingest import IngestError, load_artifact


def test_plain_markdown_read_verbatim(tmp_path: Path) -> None:
    p = tmp_path / "spec.md"
    body = "# Title\n\n- bullet\n\n```py\nx = 1\n```\n"
    p.write_text(body, encoding="utf-8")
    assert load_artifact(p) == body


def test_diff_preserved_verbatim(tmp_path: Path) -> None:
    p = tmp_path / "change.diff"
    body = "--- a/foo\n+++ b/foo\n@@ -1 +1 @@\n-old\n+new\n"
    p.write_text(body, encoding="utf-8")
    assert load_artifact(p) == body


def test_unknown_extension_read_as_text(tmp_path: Path) -> None:
    p = tmp_path / "notes"
    p.write_text("hello world", encoding="utf-8")
    assert load_artifact(p) == "hello world"


def test_docx_converted_via_markitdown(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    p = tmp_path / "proposal.docx"
    doc = docx.Document()
    doc.add_heading("Proposal", level=1)
    doc.add_paragraph("We will build a thing.")
    doc.save(str(p))

    out = load_artifact(p)
    assert "Proposal" in out
    assert "We will build a thing." in out


def test_binary_fallback_to_markitdown(tmp_path: Path) -> None:
    # A .txt with invalid utf-8 should fall through to markitdown rather than crash.
    p = tmp_path / "weird.txt"
    p.write_bytes(b"hello \xff\xfe world")
    try:
        out = load_artifact(p)
    except UnicodeDecodeError:
        pytest.fail("UnicodeDecodeError should be caught and routed to markitdown")
    except IngestError:
        pass
    else:
        assert isinstance(out, str)


def test_pages_file_gives_friendly_message(tmp_path: Path) -> None:
    p = tmp_path / "proposal.pages"
    p.write_bytes(b"PK\x03\x04fakeishpages")
    with pytest.raises(IngestError) as exc:
        load_artifact(p)
    assert "Pages" in str(exc.value)
    assert ".docx" in str(exc.value)


def test_corrupt_docx_gives_friendly_message(tmp_path: Path) -> None:
    p = tmp_path / "broken.docx"
    p.write_bytes(b"this is not a real docx")
    with pytest.raises(IngestError) as exc:
        load_artifact(p)
    msg = str(exc.value)
    assert "doesn't look like a real" in msg or "Couldn't read" in msg or "empty" in msg
    assert "Traceback" not in msg


def test_empty_file_gives_friendly_message(tmp_path: Path) -> None:
    p = tmp_path / "empty.docx"
    p.write_bytes(b"")
    with pytest.raises(IngestError):
        load_artifact(p)
