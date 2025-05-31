from typer import Typer, Context
from typer_shell import make_typer_shell
from ewa.commands import discover_commands
from rich.console import Console
from rich.logging import RichHandler
import logging

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[RichHandler(console=console, show_time=False)]
)
logger = logging.getLogger("ewa")

def launch(ctx: Context):
    for name, command in discover_commands():
        app.add_typer(command, name=name)
    print(f"Hello, world! and ctx: {ctx}")

app: Typer = make_typer_shell(prompt="ewa> ", launch=launch)


