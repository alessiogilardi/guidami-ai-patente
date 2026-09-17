"""`container.resolve` prefers the container bound in `bot_data`, else pywire's default."""

from types import SimpleNamespace

import pytest

from guidami_ai_patente_bot import container


class _Marker:
    """A type resolved only to check, by identity, which container answered the call."""


class _StubContainer:
    def __init__(self, instance: object) -> None:
        self._instance = instance

    def resolve(self, target_type: type) -> object:
        assert target_type is _Marker
        return self._instance


def test_resolve_prefers_the_container_bound_in_bot_data() -> None:
    bound = _Marker()
    context = SimpleNamespace(bot_data={container.BOT_DATA_CONTAINER_KEY: _StubContainer(bound)})

    resolved = container.resolve(context, _Marker)

    assert resolved is bound


def test_resolve_falls_back_to_the_pywire_default_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_instance = _Marker()
    monkeypatch.setattr(
        container, "get_default_container", lambda: _StubContainer(fallback_instance)
    )
    context = SimpleNamespace(bot_data={})

    resolved = container.resolve(context, _Marker)

    assert resolved is fallback_instance
