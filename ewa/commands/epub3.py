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
    use_cases: EPUBUseCases = ctx.obj
    if path: use_cases.set_path(path)
    files = use_cases.form_table(recursive, size, chapters)
    file_count = len(files)
    logger.debug(f"located {file_count} files")
    print_table(files, title="EPUB Files")


@app.command()
def select(ctx: Context, n: int = Argument(..., help="Number of the file to select")):
    """Select an epub file"""
    use_cases: EPUBUseCases = ctx.obj
    epub: EPUB | None = use_cases.select_epub(n)
    if epub:
        logger.info(epub.get_metadata())
    else:
        logger.warning("No file selected")

@app.command()
def collect(path: Path = Argument(..., help="Path to the directory containing the EPUB files")):
    """Move all EPUB files from path to the current directory"""
    pass

@app.command()
def chapters(ctx: Context):
    """Show chapters of the selected file"""
    use_cases: EPUBUseCases = ctx.obj
    if not use_cases.epub:
        logger.warning("No file selected")
        return
    #chapters = use_cases.epub.get_chapters()
    #zip_chapters = use_cases.epub.get_chapters_zip()
    #print(chapters)
    #print(zip_chapters)
    #images = use_cases.epub.get_images()
    #zip_images = use_cases.epub.get_images_zip()
    #print(images)
    #print(zip_images)
    images_zip_info = use_cases.epub.get_images_zip_info()
    print_table(images_zip_info)
    #print_table(chapters, title="Chapters")

@app.command()
def images(ctx: Context):
    """Show images of the selected file"""
    use_cases: EPUBUseCases = ctx.obj
    if not use_cases.epub:
        logger.warning("No file selected")
        return
    images = use_cases.epub.get_images()
    print_table(images, title="Images")


