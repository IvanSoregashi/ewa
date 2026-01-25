import typer
import shlex
from ewa.ui import console
from ewa.loader import load_plugins
from ewa.config import Settings
from ewa.logger_config import setup_logging

app = typer.Typer(name="ewa", help="Ewa CLI")
settings = Settings()
setup_logging(level=settings.log_level)


@app.command()
def repl(ctx: typer.Context):
    """Starts the interactive shell mode."""
    console.print("[bold blue]Starting ewa shell...[/bold blue]")
    console.print("Type 'exit' to quit.")

    while True:
        try:
            command = console.input("[bold green]ewa>[/bold green] ")
            if command.strip().lower() in ["exit", "quit"]:
                break
            if not command.strip():
                continue

            args = shlex.split(command)
            # Invoke the app with the parsed arguments.
            # standalone_mode=False prevents SystemExit on error/completion.
            app(args, standalone_mode=False)

        except typer.Exit:
            pass
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")


def main():
    load_plugins(app)
    app()


if __name__ == "__main__":
    main()
