"""
ZIP builder utility — creates in-memory ZIP archives using Python's zipfile module.
"""
import io
import zipfile


def build_zip_buffer(entries):
    """
    Build a ZIP file in memory from a list of entries.
    Each entry is a dict: {"name": "filename.txt", "content": "file content string or bytes"}
    Returns a bytes buffer ready for discord.File.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for entry in entries:
            name = entry["name"]
            content = entry["content"]
            if isinstance(content, str):
                content = content.encode("utf-8")
            zf.writestr(name, content)
    buf.seek(0)
    return buf
