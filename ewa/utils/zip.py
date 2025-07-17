import logging
import time
from pathlib import Path
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

logger = logging.getLogger(__name__)

class Zip:
    def __init__(self, path: Path):
        self.path = self.confirm_path(path)

    def __getattribute__(self, name: str) -> Any:
        #logger.warning(f"Getting attribute: {name}")
        if "path" in object.__getattribute__(self, "__dict__") and object.__getattribute__(self, "path") is None:
            raise ValueError("Zip file is corrupted")
        return super().__getattribute__(name)

    def confirm_path(self, path: Path):
        try:
            with ZipFile(path) as zip_file:
                start = time.time()
                #if not zip_file.testzip():
                #    end = time.time()
                #    logger.warning(f"Zip file confirmed in {end - start} seconds")
                return path
                #else:
                #    logger.error("Zip file is corrupted")
        except Exception as e:
            logger.error(f"Error confirming path: {e}")

    
    def extract_all(self, path: Path):
        """Extract all files from the zip file to the given path"""
        if not path.is_dir():
            logger.error("Path is not a directory")
            return
        with ZipFile(self.path) as zip_file:
            zip_file.extractall(path)


    def iterate(self):
        with ZipFile(self.path) as zip_file:
            for info in zip_file.infolist():
                yield info
