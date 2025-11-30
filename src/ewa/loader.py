import importlib.metadata
import typer
from ewa.ui import print_success, print_error

PLUGIN_GROUP = "ewa.plugins"


def load_plugins(main_app: typer.Typer):
    """Discovers and mounts plugins to the main app."""
    if hasattr(importlib.metadata, "entry_points"):
        eps = importlib.metadata.entry_points()
        plugins = eps.select(group=PLUGIN_GROUP)
    else:
        plugins = []

    for entry_point in plugins:
        try:
            plugin_app = entry_point.load()
            if isinstance(plugin_app, typer.Typer):
                main_app.add_typer(plugin_app, name=entry_point.name)
                print_success(f"{entry_point.name} loaded as app")
            elif callable(plugin_app):
                app_instance = plugin_app()
                if isinstance(app_instance, typer.Typer):
                    main_app.add_typer(app_instance, name=entry_point.name)
                print_success(f"{entry_point.name} loaded as callable")
        except Exception as e:
            print_error(f"Failed to load plugin {entry_point.name}: {e}")
