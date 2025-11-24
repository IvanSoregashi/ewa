import typer
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from ewa.ui import print_table, print_success, print_error
from ewa.main import settings
from sqlitedict import SqliteDict

app = typer.Typer(help="Epub Scanner Plugin")

ts_to_dt = lambda x: datetime.fromtimestamp(x).strftime("%Y-%m-%d %H:%M:%S")
bt_to_mb = lambda x: f"{x / (1024 * 1024):.2f} mb"

def get_filepath_data(path: Path):
    path = path.absolute()
    stat = path.stat()
    return {
        "filepath": str(path),
        "filename": path.stem,
        "suffix": path.suffix,
        "size": bt_to_mb(stat.st_size),
        "mtime": ts_to_dt(stat.st_mtime),
        "ctime": ts_to_dt(stat.st_ctime),
    }

def reformat_filepath_data(data: dict[str, Any]) -> list[str]:
    result = []
    for k, v in data.items():
        match k:
            case "size":
                result.append(bt_to_mb(v))
            case "mtime":
                result.append(ts_to_dt(v))
            case "ctime":
                result.append(ts_to_dt(v))
            case _:
                result.append(str(v))
    return result


@app.callback()
def setup():
    """Initialize the database on first run."""
    print_success(f"setup callback called, settings:{settings.model_dump_json()}")


@app.command("scanf")
def scan_files(path: Path = typer.Argument(Path("../.."), help="Directory to scan")):
    """Scans a directory for .epub files."""
    path = settings.current_dir
    print_success(f"Scanning {path}...")
    db_file = settings.profile_dir / "epub.db"
    db_table = SqliteDict(db_file, "epub_file")
    count = 0
    start_time = time.time()
    # Simple recursive scan or just top level? User said "scan the current folder".
    # I'll do top level for now.
    total_len = len(list(path.rglob("*.epub")))
    if total_len == 0:
        print_success(f"[{time.time() - start_time:>7.2f}] 0 epub files fount, aborting scan")
        return
    print_success(f"[{time.time() - start_time:>7.2f}] start scanning {total_len} files")
    for file in path.rglob("*.epub"):
        pathdata = get_filepath_data(file)
        key = pathdata["filepath"]
        db_table[key] = pathdata
        count += 1
        if count % 100 == 0:
            db_table.commit()
            print_success(f"[{time.time() - start_time:>7.2f}] scanned {(count / total_len) * 100:>5.2f}%")
    db_table.commit()
    print_success(f"[{time.time() - start_time:>7.2f}] scanned {(count / total_len) * 100:>5.2f}%")
    print_success(f"[{time.time() - start_time:>7.2f}] Finished scanning. Added {count} books.")


@app.command("listf")
def list_scanned_files(limit: int = typer.Argument(default=100, help="Number of files to display")):
    """Lists all scanned books."""
    path = settings.current_dir
    print_success(f"Scanning {path}...")
    db_file = settings.profile_dir / "epub.db"
    db_table = SqliteDict(db_file, "epub_file")
    rows = list(map(lambda x: list(map(str, x.values())), db_table.values()))

    columns = ["filepath", "filename", "suffix", "size", "mtime", "ctime"]
    print_table("My Library", columns, rows[:limit])

    #books = list_books()
    #if not books:
    #    print_error("No books found in database.")
    #    return
    #
    #rows = [[str(b["id"]), b["title"], b["author"], b["filename"]] for b in books]
    #print_table("My Library", ["ID", "Title", "Author", "Filename"], rows)


# Entry point for the plugin loader
def plugin():
    return app
