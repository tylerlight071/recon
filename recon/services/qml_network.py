"""QML may only load local resources (hard rule 1, audit F-04).

Qt Quick fetches remote URLs (an `Image` source, `XMLHttpRequest`, a font)
through the engine's QNetworkAccessManager. This factory gives the engine a
manager that refuses every scheme except file:, qrc: and data:, so even a
mistaken URL in QML can't reach the network. It's the only module allowed to
import QtNetwork (tests/test_network_imports.py).
"""

import logging
from typing import Final, override

from PySide6.QtCore import QIODevice, QObject, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtQml import QQmlNetworkAccessManagerFactory

from recon.logging_setup import Safe

LOCAL_SCHEMES: Final = frozenset({"file", "qrc", "data"})

_log = logging.getLogger(__name__)


class _LocalOnlyManager(QNetworkAccessManager):
    def __init__(self, factory: "LocalOnlyNetworkFactory", parent: QObject | None) -> None:
        super().__init__(parent)
        self._factory = factory

    @override
    def createRequest(
        self,
        op: QNetworkAccessManager.Operation,
        request: QNetworkRequest,
        outgoingData: QIODevice | None = None,
    ) -> QNetworkReply:
        scheme = request.url().scheme().lower()
        if scheme not in LOCAL_SCHEMES:
            self._factory.blocked += 1
            _log.warning("blocked a qml request using scheme %s", Safe(scheme or "none"))
            # An empty URL fails at once with "protocol unknown"; nothing is sent.
            request = QNetworkRequest(QUrl())
        return super().createRequest(op, request, outgoingData)


class LocalOnlyNetworkFactory(QQmlNetworkAccessManagerFactory):
    """Creates network managers that only load local resources.

    Keep a reference for as long as the engine lives: the engine doesn't own it.
    """

    def __init__(self) -> None:
        """Start with nothing blocked."""
        super().__init__()
        self.blocked = 0
        """How many remote requests were refused (for tests and logs)."""

    @override
    def create(self, parent: QObject) -> QNetworkAccessManager:
        return _LocalOnlyManager(self, parent)
