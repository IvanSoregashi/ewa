import typer

app = typer.Typer(help="command example")

@app.command()
def hello(name: str = typer.Argument(..., help="Name to greet")):
    """Say hello to someone."""
    typer.echo(f"Hello, {name}!")