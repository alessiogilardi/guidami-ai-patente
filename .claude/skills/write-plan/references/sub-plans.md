# Sub-piani (piani lunghi)

Se un piano supera la soglia `XL` di effort (vedi ## Effort — calibrazione) o copre aree distinte, va suddiviso:

1. Crea una sotto-cartella con lo stesso formato data-slug: `docs/plans/YYYY-MM-DD--<topic>/`
2. Crea un file `_index.md` dentro la sotto-cartella che descrive il *ragionamento* del breakdown:
    - testo discorsivo
    - Evitare un elenco meccanico
3. I file dei sub-piani seguono lo stesso formato: `YYYY-MM-DD--step-<N>-<sub-slug>.md`.
4. Lo script `generate_index.py` tratta la sotto-cartella come una singola voce nell'indice root (non elenca i sub-piani individualmente).

```markdown
docs/plans/
  _index.md                                 ← generato
  2026-07-01--ingest-quiz-enrichment/
    _index.md                               ← scritto a mano, descrive il breakdown
    2026-07-01--step-01-normalization.md
    2026-07-01--step-02-keyword-tagging.md
```
