import typer

app = typer.Typer(help="Hello command example")

@app.callback(invoke_without_command=True)
def hello(name: str = typer.Argument(..., help="Name to greet")):
    """Say hello to someone."""
    typer.echo(f"Hello, {name}!")