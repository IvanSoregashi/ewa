import logging
import re
from pathlib import Path
import typer
from typer_shell import make_typer_shell
from ewa.utils.table import print_table
from ewa.use_cases.epub import EPUB, EPUBUseCases

logger = logging.getLogger(__name__)

class EpubCommands:
    def __init__(self, app: typer.Typer):
        """Initialize the EpubCommands class with a Typer app instance."""
        self.app = app
        self.register_commands()
        self.epub_use_cases = EPUBUseCases(Path.cwd())
    
    def register_commands(self):
        """Register all commands with the Typer app."""
        self.app.command()(self.list)
    
    def list(
        self,
        size: bool = typer.Option(False, "--size", "-s", help="Show size of each file"),
        path: Path = typer.Option(Path.cwd(), "--path", "-p", help="Path to search for epub files"),
        recursive: bool = typer.Option(False, "--recursive", "-r", help="Search recursively for epub files"),
        chapters: bool = typer.Option(False, "--chapters", "-c", help="Parse name for chapters for each file"),
    ):
        """List all epub files in the current directory"""
        if path != Path.cwd():
            self.epub_use_cases.set_path(path)
        files = self.epub_use_cases.form_table(recursive, size, chapters)
        print_table(files, title="EPUB Files")


# Create the Typer app and initialize commands
#app = typer.Typer(help="epub helper application")
app = make_typer_shell(prompt="epub> ")
EpubCommands(app) 