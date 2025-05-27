import logging
from pathlib import Path
import typer
from ewa.utils.table import print_table

logger = logging.getLogger(__name__)

app = typer.Typer(help="epub helper application")

@app.command()
def list(
    size: bool = typer.Option(False, "--size", "-s", help="Show size of each file"),
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Path to search for epub files"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search recursively for epub files"),
    ):
    """List all epub files in the current directory"""
    files = []
    for file in path.glob(f"{'**/' if recursive else ''}*.epub"):
        file_info = {"Filename": file.name}
        if size:
            file_info["Size"] = f"{file.stat().st_size / 1024 / 1024:.1f}Mb"
        files.append(file_info)
    
    print_table(files, title="EPUB Files")
