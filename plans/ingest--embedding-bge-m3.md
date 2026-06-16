# ❌ ARCHIVIATO — Migrazione embedder → bge-m3 (locale, 1024)

> **Stato: SUPERSEDED / non implementato.** La decisione è stata **ribaltata**: il
> progetto **resta** su `text-embedding-3-small` (cloud, via litellm → OpenRouter,
> **1536 dim**), che è già il default implementato nel codice. La migrazione a
> bge-m3 locale descritta in questo file **non viene eseguita**.
>
> - Decisione attiva sull'embedder: [tech-stack.md](tech-stack.md), sezione
>   *Embeddings*.
> - L'unica parte di questo piano che **sopravvive** è l'embedding **offline** dei
>   quiz (precompute per il giudice), ora a 1536 dim e indipendente dall'embedder:
>   spostata in [ingest--quiz-embeddings.md](ingest--quiz-embeddings.md).
>
> Il contenuto storico (rationale bge-m3, generalizzazione del client locale,
> recreate volume a 1024, ecc.) resta nella history git di questo file. Non
> aggiungere qui nuova pianificazione: questo documento è chiuso.
