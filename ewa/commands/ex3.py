import typer

app = typer.Typer(help="Hello command example")

@app.callback(invoke_without_command=True)
def hello():
    """Say hello to someone."""
    typer.echo(f"Hello, World!")