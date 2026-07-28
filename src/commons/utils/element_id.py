import uuid

# Fixed project namespace, deliberately NOT configurable: changing it renames
# every generated file and resets the resumability filter (see the plan's Risks).
_NAMESPACE = uuid.UUID("3f2b8c14-9d47-5e6a-b0c1-7a8d9e2f4b60")
_SEPARATOR = ":"


def element_id(*parts: str) -> str:
    """Build a deterministic uuid5 from the given parts.

    The same parts always yield the same id, so the value is safe to use as a
    stable filename across runs.

    Args:
        *parts: Ordered identity components (e.g. source and article number).

    Returns:
        The uuid5 as a string.

    Note:
        Parts are joined with ``":"``, so ``("a:b", "c")`` and ``("a", "b:c")``
        collide. Unreachable with current inputs (source in {cds, cap}, number
        like "2-bis"), but relevant if the keyer is reused elsewhere.
    """
    return str(uuid.uuid5(_NAMESPACE, _SEPARATOR.join(parts)))
