"""Hard rule 1: only local Ollama at runtime. Nothing else in recon/ may reach the network.

Static guards over recon/ (Python and QML), each with a self-test proving the
detector catches the bypass forms found by the Phase 0 audit (F-04):

- network modules may be imported only by the one module allowed to use them;
- dynamic imports (`importlib.import_module`, `__import__`) are banned;
- things that open URLs or run programs (`QDesktopServices`, `webbrowser`,
  `subprocess`) are limited to named modules;
- QML may not contain remote URLs, XMLHttpRequest or openUrlExternally.

The runtime half (a QQmlNetworkAccessManagerFactory refusing non-local
schemes, and Whisper loading with local_files_only) lands with the app code
in tasks 1.3 and 5.1.
"""

import ast
import re
from pathlib import Path

import pytest

RECON_SRC = Path(__file__).resolve().parents[1] / "recon"

# Module prefix -> the only recon/ files allowed to import it.
RESTRICTED: dict[str, frozenset[str]] = {
    **dict.fromkeys(
        (
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
        ),
        frozenset({"services/ollama.py"}),
    ),
    # Hugging Face downloads at runtime unless told not to (audit F-04, issue #30).
    **dict.fromkeys(("faster_whisper", "huggingface_hub"), frozenset({"services/whisper.py"})),
    # QML's network access manager factory, which refuses every non-local scheme.
    "PySide6.QtNetwork": frozenset({"services/qml_network.py"}),
    # D-Bus (a local Unix socket, ADR 0003/0009): desktop notifications and the shortcut portal.
    "jeepney": frozenset({"services/notifications.py", "services/portal.py"}),
    # Running programs: only from modules CLAUDE.md allows (KWin reload, etc.).
    "subprocess": frozenset({"services/kwin.py"}),
    # Banned everywhere in recon/.
    **dict.fromkeys(
        (
            "asyncio",
            "smtplib",
            "ftplib",
            "poplib",
            "imaplib",
            "nntplib",
            "telnetlib",
            "xmlrpc",
            "socketserver",
            "multiprocessing.connection",
            "webbrowser",
            "PySide6.QtWebEngine",
            "PySide6.QtWebEngineCore",
            "PySide6.QtWebEngineWidgets",
            "PySide6.QtWebEngineQuick",
            "PySide6.QtWebView",
            "PySide6.QtWebSockets",
            "PySide6.QtHttpServer",
        ),
        frozenset[str](),
    ),
}
# Names (classes, functions) that open URLs, and where they may be used.
RESTRICTED_NAMES: dict[str, frozenset[str]] = {
    # "Open in Obsidian" needs obsidian:// links; one module will own that, refusing http(s).
    "QDesktopServices": frozenset({"services/open_url.py"}),
    "openUrlExternally": frozenset(),
    "import_module": frozenset(),
    "__import__": frozenset(),
}
QML_FORBIDDEN = re.compile(
    r"\b(?:https?|ftp|wss?)://|XMLHttpRequest|openUrlExternally|import\s+QtWeb", re.IGNORECASE
)


def _imports(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
            modules.update(f"{node.module}.{alias.name}" for alias in node.names)
    return modules


def _names(tree: ast.AST) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            found.add(node.id)
        elif isinstance(node, ast.Attribute):
            found.add(node.attr)
        elif isinstance(node, ast.alias):
            found.add(node.name.rsplit(".", 1)[-1])
    return found


def _matches(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def python_offenders(source: str, relative: str) -> list[str]:
    """Network-capable imports and names this file isn't allowed to use.

    Args:
        source: Python source text.
        relative: The file's path relative to recon/, e.g. "engine/link.py".

    Returns:
        One entry per violation, e.g. "socket" or "name QDesktopServices".
    """
    tree = ast.parse(source)
    offenders = [
        module
        for module in sorted(_imports(tree))
        for prefix, allowed in RESTRICTED.items()
        if _matches(module, prefix) and relative not in allowed
    ]
    offenders += [
        f"name {name}"
        for name, allowed in RESTRICTED_NAMES.items()
        if name in _names(tree) and relative not in allowed
    ]
    return offenders


def qml_offenders(source: str) -> list[str]:
    """Remote URLs and network APIs in QML source."""
    return [match.group(0) for match in QML_FORBIDDEN.finditer(source)]


@pytest.mark.parametrize(
    "source",
    [
        "import socket",
        "import urllib.request",
        "from http import client",
        "from PySide6 import QtNetwork",
        "from PySide6.QtNetwork import QNetworkAccessManager",
        "import httpx as h",
        "import asyncio",
        "import smtplib",
        "import ftplib",
        "import xmlrpc.client",
        "import socketserver",
        "from multiprocessing import connection",
        "import webbrowser",
        "import subprocess",
        "from subprocess import run",
        "from PySide6.QtWebEngineCore import QWebEnginePage",
        "from PySide6 import QtHttpServer",
        "import faster_whisper",
        "from huggingface_hub import snapshot_download",
        "from importlib import import_module",
        "import importlib\nimportlib.import_module('socket')",
        "__import__('socket')",
        "builtins.__import__ ('socket')",
        "from PySide6.QtGui import QDesktopServices",
        "QtGui.QDesktopServices.openUrl(url)",
    ],
)
def test_detector_catches_each_bypass_form(source: str) -> None:
    assert python_offenders(source, "engine/link.py"), source


@pytest.mark.parametrize(
    ("source", "relative"),
    [
        ("import ollama\nimport httpx", "services/ollama.py"),
        ("import faster_whisper", "services/whisper.py"),
        ("import subprocess", "services/kwin.py"),
        ("from PySide6.QtGui import QDesktopServices", "services/open_url.py"),
        ("from importlib import resources\nimport importlib.metadata", "engine/render.py"),
        ("from PySide6.QtQml import QQmlApplicationEngine", "app.py"),
        ("import json, pathlib, sqlite3", "db/rooms.py"),
    ],
)
def test_detector_allows_permitted_uses(source: str, relative: str) -> None:
    assert python_offenders(source, relative) == []


def test_asyncio_is_banned_even_in_the_ollama_service() -> None:
    assert python_offenders("import asyncio", "services/ollama.py") == ["asyncio"]


@pytest.mark.parametrize(
    "source",
    [
        'Image { source: "https://example.com/x.png" }',
        "var x = new XMLHttpRequest()",
        'Qt.openUrlExternally("http://tryhackme.com")',
        "import QtWebEngine",
        'FontLoader { source: "HTTP://fonts.example/x.ttf" }',
        'WebSocket { url: "wss://example.com" }',
    ],
)
def test_qml_detector_catches_network_use(source: str) -> None:
    assert qml_offenders(source), source


def test_qml_detector_allows_local_resources() -> None:
    source = (
        "import QtQuick\n"
        'Image { source: "qrc:/icons/tick.svg" }\n'
        'FontLoader { source: "fonts/Inter.ttf" }'
    )

    assert qml_offenders(source) == []


def test_no_python_in_recon_uses_the_network_outside_its_allowed_module() -> None:
    offenders = [
        f"{path.relative_to(RECON_SRC)}: {offender}"
        for path in RECON_SRC.rglob("*.py")
        for offender in python_offenders(
            path.read_text(encoding="utf-8"), path.relative_to(RECON_SRC).as_posix()
        )
    ]

    assert offenders == []


def test_no_qml_in_recon_reaches_the_network() -> None:
    offenders = [
        f"{path.relative_to(RECON_SRC)}: {offender}"
        for path in RECON_SRC.rglob("*.qml")
        for offender in qml_offenders(path.read_text(encoding="utf-8"))
    ]

    assert offenders == []
