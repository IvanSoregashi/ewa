from typer import Typer, Context, Option
from packages.plugins import discover_commands
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

app = Typer(help="EWA - Extensible CLI Framework")


@app.callback()
def callback(ctx: Context, debug: bool = Option(False, "--debug", "-d", help="Enable debug logging")):
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

#@app.command()
#def ls(ctx: Context, recursive: bool = Option(False, "--recursive", "-r")):
#    print(*map(lambda p: p.name, Path.cwd().glob("**/*" if recursive else "*")))

def main():
    for name, command in discover_commands():
        app.add_typer(command, name=name)
        #command.command("ls", help="List files in the current directory")(ls)
    
    app()

if __name__ == "__main__":
    main()

