import typer
import time
from pathlib import Path
from ewa.ui import print_table, print_success
from ewa.main import settings
from ewa.sqlmodel_storage import SQLModelTable
from epub.tables import EpubContentData, EpubFileData

app = typer.Typer(help="Epub Plugin")


@app.callback()
def setup():
    """Initialize the database on first run."""
    print_success(f"setup callback called, settings:{settings.model_dump_json()}")


@app.command("scanf")
def scan_files(path: Path = typer.Argument(Path("../.."), help="Directory to scan")):
    """Scans a directory for .epub files."""
    path = settings.current_dir
    print_success(f"Scanning {path}...")
    start_time = time.time()
    total_len = len(list(path.rglob("*.epub")))
    if total_len == 0:
        print_success(
            f"[{time.time() - start_time:>7.2f}] 0 epub files fount, aborting scan"
        )
        return
    print_success(
        f"[{time.time() - start_time:>7.2f}] start scanning {total_len} files"
    )
    table = SQLModelTable(EpubFileData)
    table.write(
        map(EpubFileData.from_path, path.rglob("*.epub")),
        batch=1000,
        on_conflict=table.OnConflict.UPDATE,
    )
    print_success(f"[{time.time() - start_time:>7.2f}] Finished scanning.")


@app.command()
def scan_contents():
    """Scans a directory for .epub files, reads contents of epub files."""
    pass
    # table = SQLModelTable(EpubContentData)
    # start_time = time.time()
    #
    # def scan_dir_for_epubs(dir: Path):
    #     def analyze(path: Path):
    #         try:
    #             epub = EPUB(path)
    #             file_content = epub.collect_file_info()
    #             opf_file = [file["filename"] for file in file_content if file["suffix"] == ".opf"][0]
    #             file_details = epub.file_info(opf_file=opf_file)
    #
    #         except Exception as e:
    #             print(path, e)
    #             return []
    #
    #     with ThreadPoolExecutor(max_workers=4) as exec:
    #         results = list(exec.map(analyze, dir.rglob("*.epub")))
    #         df = pd.DataFrame(item for result in results for item in result)


@app.command()
def test():
    table = SQLModelTable(EpubFileData, echo=False)
    # q = Queue()
    # Thread(target=lambda: list(map(q.put, itertools.chain(map(EpubFileData.from_path, settings.current_dir.rglob("*.epub")), (None,))))).start()
    start_time = time.time()
    # table.write_from_queue(q, on_conflict=table.OnConflict.UPDATE)
    print_success(f"{table.count_rows()} total rows")
    print_success(f"[{time.time() - start_time:>7.2f}] write finished")


@app.command()
def count(
    files: bool = typer.Option(False, "-f", "--files"),
    rows: bool = typer.Option(False, "-r", "--rows"),
):
    if files:
        print_success(f"Counting epub files in {settings.current_dir}...")
        count = len(tuple(Path(settings.current_dir).rglob("*.epub")))
        print_success(f"{count} epub files found")
    if rows:
        table = SQLModelTable(EpubFileData, echo=False)
        print_success(
            f"Counting epub file records in {table.table_model.__tablename__} SQL table..."
        )
        print_success(f"{table.count_rows()} total rows found")


@app.command()
def drop(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
):
    if files:
        table = SQLModelTable(EpubFileData)
        table.drop()
        print_success(f"dropped table {table.table_model.__tablename__}")
    if contents:
        table = SQLModelTable(EpubContentData)
        table.drop()
        print_success(f"dropped table {table.table_model.__tablename__}")


@app.command("listf")
def list_scanned_files(
    files: bool = typer.Option(False, "-f", "--files"),
    contents: bool = typer.Option(False, "-c", "--contents"),
):
    """Lists all scanned books."""
    if files:
        table = SQLModelTable(EpubFileData)
        raw_rows = table.read_rows(limit=10)
        columns = list(raw_rows[0].as_dict().keys())
        print_table("My Library", columns, list(map(lambda x: x.as_list(), raw_rows)))
    if contents:
        print_success("Not Implemented")


# Entry point for the plugin loader
def plugin():
    return app
