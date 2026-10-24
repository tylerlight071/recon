"""Instantiate QML components headless and collect every warning they raise."""

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import SIGNAL, QEventLoop, QObject, QPointF, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine, QQmlError
from PySide6.QtQuick import QQuickItem, QQuickWindow

UI_DIR = Path(__file__).resolve().parents[2] / "recon" / "ui"
COMPONENTS_DIR = UI_DIR / "components"
THEME_DIR = UI_DIR / "theme"
_app: QGuiApplication | None = None


@dataclass
class Loaded:
    """A component instance inside a shown offscreen window, plus what the engine said."""

    engine: QQmlEngine
    window: QQuickWindow
    root: QQuickItem
    warnings: list[str] = field(default_factory=list)

    def find(self, name: str) -> QObject:
        """The object with `objectName` == name (the subject is "subject")."""
        found = self.root.findChild(QObject, name)
        if found is None:
            msg = f"no object named {name!r}"
            raise LookupError(msg)
        return found

    @property
    def subject(self) -> QObject:
        """The component under test."""
        return self.find("subject")

    @property
    def theme(self) -> QObject:
        """The Theme singleton this engine uses."""
        theme = self.root.property("theme")
        assert isinstance(theme, QObject)
        return theme


def app() -> QGuiApplication:
    """The process's QGuiApplication, created once and kept alive."""
    global _app  # noqa: PLW0603 - one app per process; keep it from being garbage-collected
    existing = QGuiApplication.instance()
    if isinstance(existing, QGuiApplication):
        return existing
    _app = QGuiApplication([])
    return _app


def wait(ms: int) -> None:
    """Run the event loop for `ms` milliseconds."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(condition: Callable[[], bool], timeout_ms: int = 2000) -> bool:
    """Run the event loop until `condition()` holds or the timeout passes.

    Returns:
        Whether the condition held in time.
    """
    waited = 0
    while not condition() and waited < timeout_ms:
        wait(10)
        waited += 10
    return condition()


def load(body: str, *, reduce_motion: bool = True, size: tuple[int, int] = (480, 360)) -> Loaded:
    """Instantiate `body` (QML using the components) inside a shown offscreen window.

    Args:
        body: QML for the content, e.g. `Button { objectName: "subject"; text: "Go" }`.
        reduce_motion: Turn animations off so property changes apply at once.
        size: Window size in pixels.

    Returns:
        The loaded tree. Warnings from the engine are in `.warnings`.

    Raises:
        RuntimeError: The QML didn't compile.
        TypeError: The root object isn't an Item.
    """
    app()
    engine = QQmlEngine()
    warnings: list[str] = []

    def collect(errors: list[QQmlError]) -> None:
        warnings.extend(error.toString() for error in errors)

    engine.warnings.connect(collect)
    source = (
        "import QtQuick\n"
        f'import "{COMPONENTS_DIR.as_uri()}"\n'
        f'import "{THEME_DIR.as_uri()}"\n'
        "Item {\n"
        f"  width: {size[0]}; height: {size[1]}\n"
        "  property QtObject theme: Theme\n"
        f"  Component.onCompleted: Theme.reduceMotion = {'true' if reduce_motion else 'false'}\n"
        f"  {body}\n"
        "}\n"
    )
    component = QQmlComponent(engine)
    component.setData(source.encode(), QUrl.fromLocalFile(str(UI_DIR / "harness.qml")))
    root = component.create()
    if root is None:
        errors = "; ".join(error.toString() for error in component.errors())
        msg = f"QML didn't load: {errors}"
        raise RuntimeError(msg)
    if not isinstance(root, QQuickItem):
        msg = "harness root isn't an Item"
        raise TypeError(msg)
    window = QQuickWindow()
    window.resize(*size)
    root.setParentItem(window.contentItem())
    root.setParent(window)
    window.show()
    wait(50)
    return Loaded(engine, window, root, warnings)


class SignalCounter:
    """Counts emissions of a signal, including signals declared in QML."""

    def __init__(self, sender: QObject, signature: str) -> None:
        """Start counting `signature` (e.g. "clicked()") on `sender`."""
        self.count = 0
        QObject.connect(sender, SIGNAL(signature), self._hit)

    def _hit(self, *_args: object) -> None:
        self.count += 1


def centre(item: QObject) -> QPointF:
    """Scene position of an item's centre, for mouse clicks."""
    assert isinstance(item, QQuickItem)
    return item.mapToScene(QPointF(item.width() / 2, item.height() / 2))
