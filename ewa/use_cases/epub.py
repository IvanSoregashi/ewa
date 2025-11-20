import logging
import sqlite3
import zipfile
import json
import re
import tempfile

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from sqlitedict import SqliteDict
import pandas as pd
import ebooklib
from ebooklib.epub import EpubBook, read_epub

from ewa.utils.epub.epub import EPUB, UnpackedEPUB
from ewa.settings import config


logger = logging.getLogger(__name__)


def scan_dir_for_epubs(dir: Path):
    def analyze(path: Path):
        try:
            epub = EPUB(path)
            file_content = epub.collect_file_info()
            opf_file = [file["filename"] for file in file_content if file["suffix"] == ".opf"][0]
            file_details = epub.file_info(opf_file=opf_file)

        except Exception as e:
            print(path, e)
            return []

    with ThreadPoolExecutor(max_workers=4) as exec:
        results = list(exec.map(analyze, dir.rglob("*.epub")))
        df = pd.DataFrame(item for result in results for item in result)

    # save file contents to fc table
    config.epub.epubs_db

    # save file info to fi table