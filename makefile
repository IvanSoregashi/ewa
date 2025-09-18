
clean:
	uv run python -c "import shutil, pathlib; [shutil.rmtree(path) for path in pathlib.Path('.').rglob('__pycache__') if path.is_dir()]"

lint:
	uv run ruff check --fix
	uv run ruff format