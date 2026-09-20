from pathlib import Path

from library.utils import verify_destination


def test_destination_parent_created_by_another_worker(tmp_path, monkeypatch):
    destination = tmp_path / "output" / "book.epub"
    mkdir = Path.mkdir

    def concurrent_mkdir(path, *args, **kwargs):
        if path == destination.parent and not path.exists():
            mkdir(path)
        return mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", concurrent_mkdir)
    assert verify_destination(destination, "book.epub") == destination
    assert destination.parent.is_dir()
    assert not destination.exists()
