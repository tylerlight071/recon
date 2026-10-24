"""QML can only load local resources (hard rule 1, audit F-04)."""

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QUrl
from PySide6.QtNetwork import QNetworkReply, QNetworkRequest
from PySide6.QtQml import QQmlComponent

from recon.app import create_engine
from recon.services.qml_network import LOCAL_SCHEMES, LocalOnlyNetworkFactory
from tests.ui.qml_harness import app, wait_until

# Image.status values (QtQuick): Ready = 1, Error = 3.
READY, ERROR = 1, 3


def _load_image(source: str, folder: Path) -> tuple[int, int]:
    """Load an Image from `source`; return its final status and how many requests were blocked."""
    app()
    qml = create_engine()
    component = QQmlComponent(qml.engine)
    component.setData(
        (
            f'import QtQuick\nImage {{ property int statusCode: status; source: "{source}" }}\n'
        ).encode(),
        QUrl.fromLocalFile(str(folder / "probe.qml")),
    )
    image = component.create()
    assert image is not None
    wait_until(lambda: image.property("statusCode") in {READY, ERROR}, 3000)
    status = image.property("statusCode")
    blocked = qml.network.blocked
    image.deleteLater()
    return (status if isinstance(status, int) else -1), blocked


@pytest.mark.parametrize(
    "url",
    ["http://127.0.0.1:9/x.png", "https://tryhackme.com/logo.png", "ftp://127.0.0.1/x.png"],
)
def test_remote_images_are_refused(tmp_path: Path, url: str) -> None:
    status, blocked = _load_image(url, tmp_path)

    assert status == ERROR
    assert blocked == 1


def test_local_images_still_load(tmp_path: Path) -> None:
    from PySide6.QtGui import QColor, QImage  # noqa: PLC0415 - only this test draws an image

    picture = QImage(4, 4, QImage.Format.Format_RGB32)
    picture.fill(QColor("#0b0c0e"))
    path = tmp_path / "tick.png"
    picture.save(str(path))

    status, blocked = _load_image(path.as_uri(), tmp_path)

    assert status == READY
    assert blocked == 0


def test_only_local_schemes_are_allowed() -> None:
    assert frozenset({"file", "qrc", "data"}) == LOCAL_SCHEMES


_PARENTS: list[QObject] = []
"""Keeps managers' parents alive; a parent garbage-collected early deletes its manager."""


def _get(url: QUrl) -> tuple[QNetworkReply, LocalOnlyNetworkFactory]:
    app()
    factory = LocalOnlyNetworkFactory()
    _PARENTS.append(QObject())
    manager = factory.create(_PARENTS[-1])
    reply = manager.get(QNetworkRequest(url))
    wait_until(reply.isFinished, 3000)
    return reply, factory


@pytest.mark.parametrize("url", ["http://127.0.0.1:9/x", "https://tryhackme.com/", "HTTPS://x.y/"])
def test_manager_refuses_remote_urls_directly(url: str) -> None:
    reply, factory = _get(QUrl(url))

    assert reply.error() != QNetworkReply.NetworkError.NoError
    assert reply.url().isEmpty()  # the original URL was never requested
    assert factory.blocked == 1


def test_manager_reads_local_files_directly(tmp_path: Path) -> None:
    path = tmp_path / "data.txt"
    path.write_text("local")

    reply, factory = _get(QUrl.fromLocalFile(str(path)))

    assert reply.error() == QNetworkReply.NetworkError.NoError
    assert bytes(reply.readAll().data()) == b"local"
    assert factory.blocked == 0
