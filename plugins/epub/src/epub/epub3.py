import logging
from pathlib import Path
from typer import Typer, Context, Option, Argument
from typer_shell import make_typer_shell
from epub import print_table
from epub import EPUB, EPUBUseCases

logger = logging.getLogger(__name__)

app: Typer = make_typer_shell(prompt="epub> ", obj=EPUBUseCases())


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
def collect(
    path: Path = Argument(..., help="Path to the directory containing the EPUB files"),
):
    """Move all EPUB files from path to the current directory"""
    pass


@app.command()
def chapters(ctx: Context):
    """Show chapters of the selected file"""
    use_cases: EPUBUseCases = ctx.obj
    if not use_cases.epub:
        logger.warning("No file selected")
        return
    # chapters = use_cases.epub.get_chapters()
    # zip_chapters = use_cases.epub.get_chapters_zip()
    # print(chapters)
    # print(zip_chapters)
    # images = use_cases.epub.get_images()
    # zip_images = use_cases.epub.get_images_zip()
    # print(images)
    # print(zip_images)
    images_zip_info = use_cases.epub.get_images_zip_info()
    print_table(images_zip_info)
    # print_table(chapters, title="Chapters")


@app.command()
def images(ctx: Context):
    """Show images of the selected file"""
    use_cases: EPUBUseCases = ctx.obj
    if not use_cases.epub:
        logger.warning("No file selected")
        return
    images = use_cases.epub.get_images()
    print_table(images, title="Images")


@app.command()
def analyze(ctx: Context):
    """Analyze the selected file"""
    use_cases: EPUBUseCases = ctx.obj
    use_cases.analyze_all_epubs()


@app.command()
def resize(ctx: Context):
    """Resize the selected file"""
    use_cases: EPUBUseCases = ctx.obj
    use_cases.resize_and_save_epub()
