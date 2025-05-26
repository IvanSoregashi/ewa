import typer
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

app = typer.Typer(help="EWA - Extensible CLI Framework")

def main():
    for name, command in discover_commands():
        app.add_typer(command, name=name)
    
    app()

if __name__ == "__main__":
    main() 