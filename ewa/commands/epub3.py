import logging
import re
from pathlib import Path
from typer import Typer, Context, Option, Argument
from typer_shell import make_typer_shell
from ewa.utils.table import print_table
from ewa.use_cases.epub import EPUB, EPUBUseCases

logger = logging.getLogger(__name__)

app: Typer = make_typer_shell(prompt="epub> ", obj=EPUBUseCases())

@app.command()
def list(
    ctx: Context,
    size: bool = Option(False, "--size", "-s", help="Show size of each file"),
    path: Path = Argument(None, help="Path to search for epub files"),
    recursive: bool = Option(False, "--recursive", "-r", help="Search recursively for epub files"),
    chapters: bool = Option(False, "--chapters", "-c", help="Parse name for chapters for each file"),
    ):
    """List all epub files in the current directory"""
    path = path or ctx.obj.path
    files = [EPUB(epub).to_dict(size, chapters) for epub in path.glob(f"{'**/' if recursive else ''}*.epub")]
    file_count = len(files)
    logger.debug(f"located {file_count} files")
    files = [{"N": n, **f} for n, f in enumerate(files)]
    print_table(files, title="EPUB Files")


@app.command()
def collect(path: Path = Argument(..., help="Path to the directory containing the EPUB files")):
    """Move all EPUB files from path to the current directory"""
    pass
