from __future__ import annotations

import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree

TEXT_EXTENSIONS: set[str] = {
    ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml",
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss", ".less",
    ".sh", ".bash", ".zsh", ".fish", ".env", ".gitignore", ".dockerignore",
    ".ini", ".cfg", ".conf", ".toml", ".lock", ".log",
    ".sql", ".rb", ".go", ".rs", ".java", ".kt", ".swift", ".c", ".cpp", ".h",
    ".vue", ".svelte", ".astro", ".mjs", ".cjs",
}


def _parse_docx(content: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "word/document.xml" not in z.namelist():
                return None
            xml_bytes = z.read("word/document.xml")
            root = ElementTree.fromstring(xml_bytes)
            paragraphs: list[str] = []
            for p in root.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"):
                texts: list[str] = []
                for t in p.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"):
                    if t.text:
                        texts.append(t.text)
                if texts:
                    paragraphs.append("".join(texts))
            return "\n".join(paragraphs) if paragraphs else None
    except Exception:
        return None


def _parse_xlsx(content: bytes) -> str | None:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            if "xl/sharedStrings.xml" not in z.namelist() and "xl/worksheets/sheet1.xml" not in z.namelist():
                return None
            rows: list[list[str]] = []

            # Read shared strings (if exists)
            shared_strings: list[str] = []
            if "xl/sharedStrings.xml" in z.namelist():
                try:
                    xml_bytes = z.read("xl/sharedStrings.xml")
                    root = ElementTree.fromstring(xml_bytes)
                    for si in root.iter("si"):
                        texts: list[str] = []
                        for t in si.iter("t"):
                            if t.text:
                                texts.append(t.text)
                        if texts:
                            shared_strings.append("".join(texts))
                except Exception:
                    pass

            # Read first sheet
            sheet_path = "xl/worksheets/sheet1.xml"
            if sheet_path in z.namelist():
                xml_bytes = z.read(sheet_path)
                root = ElementTree.fromstring(xml_bytes)

                for row in root.iter("row"):
                    row_data: list[str] = []
                    for cell in row.iter("c"):
                        cell_type = cell.get("t")  # 's' = shared string, 'str' = formula string
                        value = ""
                        for v in cell.iter("v"):
                            if v.text:
                                if cell_type == "s" and v.text.isdigit():
                                    idx = int(v.text)
                                    value = shared_strings[idx] if idx < len(shared_strings) else ""
                                else:
                                    value = v.text
                        # Also check for inline string
                        if not value:
                            for is_ in cell.iter("is"):
                                for t in is_.iter("t"):
                                    if t.text:
                                        value = t.text
                        row_data.append(value)
                    if row_data:
                        rows.append(row_data)

            if not rows:
                return None

            # Convert to CSV-like format
            lines: list[str] = []
            for r in rows:
                lines.append(",".join(f'"{cell}"' for cell in r))

            result = "\n".join(lines)
            if len(result) > 200000:
                result = result[:200000] + f"\n[truncated: showing first 200000 of {len(result)} characters]"
            return result
    except Exception:
        return None


def _parse_doc(content: bytes) -> str | None:
    import importlib.util
    if importlib.util.find_spec("olefile") is None:
        return None
    return None


def parse_file(filename: str, content: bytes) -> str:
    ext = Path(filename).suffix.lower()
    name = Path(filename).name
    print(f"DEBUG parse_file: filename={filename}, ext={ext}, size={len(content)}")

    if ext in TEXT_EXTENSIONS:
        try:
            text = content.decode("utf-8")
            if len(text) > 200000:
                text = text[:200000] + f"\n[truncated: file too long, showing first 200000 of {len(text)} characters]"
            return text
        except UnicodeDecodeError as e:
            print(f"DEBUG UTF-8 decode error for {filename}: {e}")
            return f"[Binary file: {name}, {len(content)} bytes - decode error: {e}]"

    if ext == ".docx":
        parsed = _parse_docx(content)
        if parsed:
            if len(parsed) > 200000:
                parsed = parsed[:200000] + f"\n[truncated: file too long, showing first 200000 of {len(parsed)} characters]"
            return parsed
        return f"[Could not parse .docx file: {name}, {len(content)} bytes]"

    if ext == ".xlsx":
        parsed = _parse_xlsx(content)
        if parsed:
            if len(parsed) > 200000:
                parsed = parsed[:200000] + f"\n[truncated: file too long, showing first 200000 of {len(parsed)} characters]"
            return parsed
        return f"[Could not parse .xlsx file: {name}, {len(content)} bytes]"

    if ext == ".xls":
        return f"[Legacy .xls file: {name}, {len(content)} bytes - convert to .xlsx]"

    if ext == ".doc":
        parsed = _parse_doc(content)
        if parsed:
            return parsed
        return f"[Legacy .doc file: {name}, {len(content)} bytes - use 'textutil' or 'pandoc' to convert]"

    if ext in {".pdf"}:
        return f"[PDF file: {name}, {len(content)} bytes - include a text extraction tool like PyMuPDF to parse]"

    return f"[Binary file: {name}, {len(content)} bytes]"
