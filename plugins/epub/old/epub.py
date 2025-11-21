import logging

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from library.epub.epub import EPUB
from library.settings import config


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