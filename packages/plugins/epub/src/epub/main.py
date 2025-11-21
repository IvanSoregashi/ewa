import typer
from pathlib import Path
from ewa.ui import print_table, print_success, print_error
#from ewa.common.db import init_db, save_book, list_books
#from ewa.plugins.epub_scanner.scanner import get_epub_metadata

app = typer.Typer(help="Epub Scanner Plugin")

@app.callback()
def setup():
    """Initialize the database on first run."""
    init_db()

@app.command()
def scan(path: Path = typer.Argument(Path("../.."), help="Directory to scan")):
    """Scans a directory for .epub files."""
    print_success(f"Scanning {path.absolute()}...")
    count = 0
    # Simple recursive scan or just top level? User said "scan the current folder".
    # I'll do top level for now.
    for file in path.glob("*.epub"):
        title, author = get_epub_metadata(file)
        if title:
            save_book(file.name, str(file.absolute()), title, author)
            print_success(f"Found: {title} by {author}")
            count += 1
        else:
            print_error(f"Could not parse {file.name}")
    
    print_success(f"Finished scanning. Added {count} books.")

@app.command()
def list():
    """Lists all scanned books."""
    books = list_books()
    if not books:
        print_error("No books found in database.")
        return
    
    rows = [[str(b["id"]), b["title"], b["author"], b["filename"]] for b in books]
    print_table("My Library", ["ID", "Title", "Author", "Filename"], rows)

# Entry point for the plugin loader
def plugin():
    return app
