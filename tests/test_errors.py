"""Every deliberate error derives from ReconError and carries kind, plain copy."""

import inspect
import re

import pytest

from recon import errors

ERROR_CLASSES = [
    obj
    for _, obj in inspect.getmembers(errors, inspect.isclass)
    if issubclass(obj, BaseException) and obj.__module__ == errors.__name__
]
BLAMING = re.compile(r"\byou (forgot|failed|didn't|did not|broke)\b", re.IGNORECASE)


def test_hierarchy_has_the_named_areas() -> None:
    names = {cls.__name__ for cls in ERROR_CLASSES}

    assert {"ReconError", "OllamaUnavailable", "ApplyConflict", "VaultMissing"} <= names


@pytest.mark.parametrize("cls", ERROR_CLASSES, ids=lambda c: c.__name__)
def test_every_error_is_a_recon_error(cls: type[BaseException]) -> None:
    assert issubclass(cls, errors.ReconError)


@pytest.mark.parametrize("cls", ERROR_CLASSES, ids=lambda c: c.__name__)
def test_user_message_is_plain_and_kind(cls: type[errors.ReconError]) -> None:
    message = cls.user_message

    assert message.endswith(".")
    assert "Traceback" not in message
    assert not BLAMING.search(message)
    assert "!" not in message


def test_subclasses_override_the_generic_message() -> None:
    generic = errors.ReconError.user_message
    for cls in ERROR_CLASSES:
        if cls is not errors.ReconError:
            assert cls.user_message != generic, cls.__name__
