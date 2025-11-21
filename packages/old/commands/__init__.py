from typing import Protocol, runtime_checkable
import importlib
import pkgutil
from pathlib import Path
import typer
import time
import logging

logger = logging.getLogger("ewa.commands")

@runtime_checkable
class Command(Protocol):
    """Base protocol that all command modules must implement."""
    app: typer.Typer

def discover_commands() -> list[tuple[str, typer.Typer]]:
    """Discover and load all command modules from the commands directory."""
    start_time = time.perf_counter()
    commands = []
    commands_dir = Path(__file__).parent
    
    modules = list(pkgutil.iter_modules([str(commands_dir)]))
    
    for module_info in modules:
        if module_info.name.startswith('_'):
            continue
            
        try:
            module = importlib.import_module(f"ewa.commands.{module_info.name}")
            
            if isinstance(module, Command):
                commands.append((module_info.name, module.app))
        except Exception as e:
            logger.error(f"Failed to load command module {module_info.name}: {e}")
    
    total_time = time.perf_counter() - start_time
    logger.info(f"Loaded {len(commands)} modules in {total_time*1000:.0f}ms")
    return commands