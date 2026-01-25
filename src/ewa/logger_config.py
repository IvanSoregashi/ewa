import logging
from rich.logging import RichHandler


def setup_logging(level: int = logging.INFO):
    """
    Configures the root logger to use RichHandler.
    """
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)],
    )
