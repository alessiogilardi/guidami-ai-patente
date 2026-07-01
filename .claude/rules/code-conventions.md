# Convenzioni di codice

Convenzioni specifiche di questo progetto. Le regole generali Python (tipizzazione,
stile PEP 8, import relativi/assoluti, SOLID, pattern di configurazione) sono in
`~/.claude/rules/python/`.

## Pydantic

Le classi di configurazione (qualsiasi file sotto `configs/`) devono impostare
`model_config = ConfigDict(frozen=True)`.

## PostgresClient — cast vettoriale

`PostgresClient` richiede il cast esplicito `%s::vector` per i parametri vettoriali:
psycopg adatta `list[float]` al tipo `array` di Postgres, incompatibile con
l'operatore `<=>` di pgvector.

```python
# WRONG
cursor.execute("SELECT ... WHERE embedding <=> %s", [vector])

# RIGHT
cursor.execute("SELECT ... WHERE embedding <=> %s::vector", [vector])
```

## Test — marker di integrazione

`@pytest.mark.integration` marca i test che richiedono servizi esterni (Postgres,
download di modelli). `uv run pytest` senza flag li salta automaticamente.
