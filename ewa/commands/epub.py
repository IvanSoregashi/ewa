import logging
import re
from pathlib import Path
import typer
#from typer_shell import make_typer_shell
from ewa.utils.table import print_table
from ewa.use_cases.epub import EPUB, EPUBUseCases

logger = logging.getLogger(__name__)

app = typer.Typer(help="epub helper application")
#app = make_typer_shell(prompt="epub> ")


@app.command()
def list(
    size: bool = typer.Option(False, "--size", "-s", help="Show size of each file"),
    path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Path to search for epub files"),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Search recursively for epub files"),
    chapters: bool = typer.Option(False, "--chapters", "-c", help="Parse name for chapters for each file"),
    ):
    """List all epub files in the current directory"""
    files = []
    for file in path.glob(f"{'**/' if recursive else ''}*.epub"):
        file_info = {"Filename": file.name}
        if chapters:
            file_info["Chapters"] = re.search(r"(\d+\s*-\s*\d+)", file.name).group(1) or "N/A"
        if size:
            file_info["Size"] = f"{file.stat().st_size / 1024 / 1024:.0f} Mb"
        files.append(file_info)
    
    print_table(files, title="EPUB Files")


@app.command()
def collect(path: Path = typer.Argument(..., help="Path to the directory containing the EPUB files")):
    """Move all EPUB files from path to the current directory"""
    pass
