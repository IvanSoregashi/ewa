import importlib.metadata
import typer
from ewa.ui import print_success, print_error
import sys

PLUGIN_GROUP = "ewa.plugins"

def load_plugins(main_app: typer.Typer):
    """Discovers and mounts plugins to the main app."""
    # Python 3.10+ uses select()
    if hasattr(importlib.metadata, 'entry_points'):
        eps = importlib.metadata.entry_points()
        # Handle different python versions of entry_points return type
        if hasattr(eps, 'select'):
            plugins = eps.select(group=PLUGIN_GROUP)
        else:
            plugins = eps.get(PLUGIN_GROUP, [])
    else:
        plugins = []

    # DEBUG
    # sys.stderr.write(f"DEBUG: Found plugins: {plugins}\n")
    # sys.stderr.write(f"DEBUG: All entry points: {importlib.metadata.entry_points().keys()}\n")

    for entry_point in plugins:
        try:
            plugin_app = entry_point.load()
            # We assume the plugin exposes a Typer app or a function returning one
            if isinstance(plugin_app, typer.Typer):
                main_app.add_typer(plugin_app, name=entry_point.name)
                # print_success(f"Loaded plugin: {entry_point.name}") # Optional: verbose logging
            elif callable(plugin_app):
                # If it's a function, call it to get the app
                app_instance = plugin_app()
                if isinstance(app_instance, typer.Typer):
                    main_app.add_typer(app_instance, name=entry_point.name)
        except Exception as e:
            print_error(f"Failed to load plugin {entry_point.name}: {e}")
