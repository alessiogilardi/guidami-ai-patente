def normalize_term(term: str) -> str:
    """Uppercases `term`, so the same word extracted from either marker form collides."""
    return term.upper()


def capitalize_definition(definition: str) -> str:
    """Uppercases only `definition`'s first character, leaving the rest verbatim."""
    return definition[:1].upper() + definition[1:]
