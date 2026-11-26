"""Package version fallback."""

import importlib
from importlib import metadata
from importlib.metadata import PackageNotFoundError

import jaquette


def test_version_is_unknown_when_package_is_not_installed(monkeypatch):
    monkeypatch.setattr(
        metadata,
        "version",
        lambda name: (_ for _ in ()).throw(PackageNotFoundError(name)),
    )

    try:
        importlib.reload(jaquette)
        assert jaquette.__version__ == "unknown"
    finally:
        # Restores the package to its normal functionality and version.
        monkeypatch.undo()
        importlib.reload(jaquette)
