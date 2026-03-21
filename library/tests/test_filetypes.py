from pathlib import Path
import pytest
from library.filetypes import guess_file_type

@pytest.mark.parametrize("filepath, expected", [
    # -----------------------------------------------------
    # 1. CORE EPUB STRUCTURE
    # -----------------------------------------------------
    ("mimetype", "text/plain"),
    ("content.opf", "application/oebps-package+xml"),
    ("toc.ncx", "application/x-dtbncx+xml"),
    ("nav.xhtml", "application/xhtml+xml"),
    ("style.css", "text/css"),
    ("book.epub", "application/epub+zip"),

    # -----------------------------------------------------
    # 2. MEDIA_TYPE.PY (Categorical explicit mentions)
    # -----------------------------------------------------
    # Images
    ("image.gif", "image/gif"),
    ("image.png", "image/png"),
    ("image.jpeg", "image/jpeg"),
    ("image.jpg", "image/jpeg"),
    ("legacy.bmp", "image/bmp"),
    ("image.svg", "image/svg+xml"),
    ("image.webp", "image/webp"),
    # Audio
    ("audio.mp3", "audio/mpeg"),
    ("audio.m4a", "audio/mp4"),
    ("audio.ogg", "audio/ogg"),
    # Style/Script
    ("script.js", "text/javascript"),
    # Ext/Types
    ("animation.smil", "application/smil+xml"),
    
    # -----------------------------------------------------
    # 3. FONT/TYPOGRAPHY TYPES
    # -----------------------------------------------------
    # Testing both modern standard endpoints and legacy fallback coercion
    ("font.ttf", "font/ttf"),
    ("font.otf", "font/otf"),
    ("font.woff", "font/woff"),
    ("font.woff2", "font/woff2"),
    ("font.sfnt", "font/sfnt"),
    ("font.eot", "application/vnd.ms-fontobject"),

    # -----------------------------------------------------
    # 4. COMMON OS/WEB FILETYPES
    # -----------------------------------------------------
    # Documents
    ("document.pdf", "application/pdf"),
    ("text.txt", "text/plain"),
    ("data.csv", "text/csv"),
    ("data.json", "application/json"),
    ("data.xml", "application/xml"),
    ("markup.md", "text/markdown"),
    ("sheet.xls", "application/vnd.ms-excel"),
    ("sheet.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ("word.doc", "application/msword"),
    ("word.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ("config.toml", "application/toml"),
    ("config.yaml", "application/yaml"),
    ("config.ini", "text/plain"),
    ("code.py", "text/x-python"),
    ("notebook.ipynb", "application/x-ipynb+json"),
    ("web.html", "text/html"),
    
    # Images/Video/Photo
    ("photo.heic", "image/heic"),
    ("photo.heif", "image/heif"),
    ("image.avif", "image/avif"),
    ("video.avi", "video/x-msvideo"),
    
    # Archives / Executables / Binaries
    ("archive.zip", "application/zip"),
    ("archive.rar", "application/vnd.rar"),
    ("archive.7z", "application/x-7z-compressed"),
    ("disk.iso", "application/x-iso9660-image"),
    ("program.exe", "application/vnd.microsoft.portable-executable"),
    ("library.dll", "application/vnd.microsoft.portable-executable"),
    ("file.torrent", "application/x-bittorrent"),
    ("object.bin", "application/octet-stream"),

    # -----------------------------------------------------
    # 5. PATH OBJECTS
    # -----------------------------------------------------
    (Path("some/dir/file.opf"), "application/oebps-package+xml"),
    (Path("/tmp/readme.md"), "text/markdown"),
    (Path("C:\\Windows\\System32\\file.ncx"), "application/x-dtbncx+xml"),
])
def test_guess_file_type(filepath, expected):
    """Test strict adherence to latest standardized mappings without conditions"""
    assert guess_file_type(filepath) == expected
