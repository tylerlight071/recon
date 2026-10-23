"""Hard rule: only services/ollama.py may touch the network."""

import ast
from pathlib import Path

RECON_SRC = Path(__file__).resolve().parents[1] / "recon"
ALLOWED = {Path("services/ollama.py")}
NETWORK_MODULES = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "httpcore",
    "aiohttp",
    "websockets",
    "ollama",
    "PySide6.QtNetwork",
    "PySide6.QtWebSockets",
}


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _is_network(module: str) -> bool:
    return any(module == banned or module.startswith(f"{banned}.") for banned in NETWORK_MODULES)


def test_detector_catches_each_import_form() -> None:
    sources = [
        "import socket",
        "import urllib.request",
        "from http import client",
        "from PySide6 import QtNetwork",
        "import httpx as h",
    ]
    for source in sources:
        assert any(_is_network(m) for m in _imported_modules(source)), source


def test_no_module_outside_ollama_service_imports_networking() -> None:
    offenders = {
        f"{path.relative_to(RECON_SRC)}: {module}"
        for path in RECON_SRC.rglob("*.py")
        if path.relative_to(RECON_SRC) not in ALLOWED
        for module in _imported_modules(path.read_text(encoding="utf-8"))
        if _is_network(module)
    }

    assert offenders == set()


def test_no_dynamic_imports_in_recon() -> None:
    offenders = [
        str(path.relative_to(RECON_SRC))
        for path in RECON_SRC.rglob("*.py")
        if "__import__(" in path.read_text(encoding="utf-8")
        or "importlib.import_module" in path.read_text(encoding="utf-8")
    ]

    assert offenders == []
