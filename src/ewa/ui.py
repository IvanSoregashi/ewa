from rich.console import Console
from rich.prompt import Prompt, Confirm


console = Console()


def ask_user(question: str, default: str = None) -> str:
    """Asks the user for input."""
    return Prompt.ask(question, default=default)


def confirm_user(question: str, default: bool = True) -> bool:
    """Asks the user for confirmation."""
    return Confirm.ask(question, default=default)


def print_success(message: str):
    console.print(f"[bold green]Success:[/bold green] {message}")


def print_error(message: str):
    console.print(f"[bold red]Error:[/bold red] {message}")
