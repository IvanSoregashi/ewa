import typer
from commands import discover_commands

app = typer.Typer(help="EWA - Extensible CLI Framework")

def main():
    # Discover and add all command modules
    for command in discover_commands():
        app.add_typer(command)
    
    app()

if __name__ == "__main__":
    main()
