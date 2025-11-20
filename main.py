import hashlib
from pathlib import Path
import pandas as pd
from ewa.utils.epub.epub import EPUB
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import time


def analyze(path: Path):
    return {"path":path, "size":path.stat().st_size, "hash": hashlib.md5(path.read_bytes()).hexdigest()}

if __name__ == "__main__":
    mw = 2
    with ThreadPoolExecutor(max_workers=mw) as exec:
        start = time.time()
        results = pd.DataFrame(list(exec.map(analyze, Path(r"C:\Users\Ivan\Books\SerenePanda").rglob("*.epub"))))
        print(f"{time.time() - start:.2f}s with {mw} workers")
        results.to_csv("serene_hashes.csv", index=False)
