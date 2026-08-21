# Glossary

| Term | Meaning |
|---|---|
| **CdS** | Codice della Strada — Italian Highway Code (Legislative Decree 30/04/1992 n.285). Scraped in full; one of three `source` values. |
| **CAP** | Codice delle Assicurazioni Private — Italian Private Insurance Code (Legislative Decree 07/09/2005 n.209). Only a subset of articles relevant to mandatory car-insurance liability (RCA) and driving licences is kept, not the full code. |
| **RCA** | Responsabilità Civile Auto — mandatory car-insurance liability; the reason only a CAP subset is scraped (only RCA/licence-relevant articles matter for exam prep). |
| **Regolamento** | Regolamento di esecuzione e di attuazione del nuovo codice della strada — DPR 16/12/1992 n.495, the CdS's implementing regulation; holds the normative descriptions of road signs the quiz bank tests. `source = "reg"` (spec 0003). Scraped in full (409 articles), no annexes (figures/tables). |
| **corpus normativo** | Collective term (used in code docstrings) for the CdS + CAP + Regolamento legal text, as opposed to the quiz bank. |
| **source** | The discriminator tag for which dataset a knowledge record belongs to: `"cds"`, `"cap"`, or `"reg"` (`Literal` type on `CleanedArticleModel`; plain `str` on the `ArticleEntity`/`ArticleCommaEntity` entities and `EmbeddableArticleComma`). Enters the data at the parsed→cleaned boundary (`ArticleMapper.from_parsed_to_cleaned`) and is propagated from there on, rather than being re-injected by each pipeline stage. The quiz bank is a separate pipeline and isn't tagged with this field. |
| **layer** (`parsed` / `cleaned` / `enriched`) | A pipeline data-maturity stage, mapped 1:1 to a `data/<layer>/` directory. `PipelineLayerConfig.input_layer`/`output_layer` select which directory a flow reads from / writes to. Not an architecture layer — a data stage on disk. For the knowledge corpus, `cleaned` is **per-element** (one file per article inside the directory — see `LayerResolverProvider.dir()`); `parsed` and the whole quiz pipeline stay monolithic (one file holding every element). The knowledge corpus has no `enriched` stage (removed, spec 0001 T-13) — the `enriched` layer name still exists in config, used only by the quiz pipeline (monolithic, not per-element). |
| **element id** | The stable, deterministic filename stem for a per-element layer file, computed by `commons.utils.element_id(*parts)` (a `uuid5` over a fixed namespace). For the knowledge corpus: `element_id(article.source, article.number)`. Same parts always yield the same id, so a re-run recognizes an article it already processed — see `docs/architecture.md`'s per-element layer description and `specs/0006-quiz-per-element-layers.md`. |
| **article** | One law article as scraped: number, title, and a structured `commas: list[ParsedComma]` (each `{number, text}`, spec 0001 T-1/T-5 — comma numbers are extracted, list-body items merged, note fragments discarded, all upstream in the scraper) (`ParsedArticleModel`/`CleanedArticleModel`). `CleanedArticleModel` (new at the parsed→cleaned boundary) adds `source` to the fields already on `ParsedArticleModel`, so from `cleaned` onward an article is self-identifying (its id no longer depends on which flow is processing it). At the storage boundary, an article is one `articles` row (`domain.entities.knowledge.ArticleEntity`) plus N `article_commas` rows (`ArticleCommaEntity`, one per comma, FK-linked) — see `docs/database.md` (spec 0001 T-7/T-8). |
| **comma** | One numbered (or note-only) subdivision of an article — Italian legal term, kept untranslated; the retrieval/embedding unit (spec 0001, replacing the earlier "chunk" terminology, now fully removed). Represented as `ParsedComma` (`{number, text}`, parsed/cleaned layers), `EmbeddableArticleComma` (embedding input; embedding text = article title + comma text only, composed declaratively at indexing time, no LLM context, AD-18), and `ArticleCommaEntity` (persisted entity, one row per comma in `article_commas`, FK to its `articles` row). Comma numbers are structured — extracted by the scraper (T-1) — never embedded in the comma's own text. |
| **quiz bank** | The full set of true/false quiz statements ingested from the official quiz PDF (`parse-domande` → `data/parsed/quiz-patente-ab/`), as opposed to the **corpus normativo**. Has its own pipeline (`orchestrators/quiz_flows.py`) and is persisted to `quiz_questions`; unlike knowledge records it is not tagged with a `source`. |
| **quiz item** | One flattened true/false statement to answer, after `FlatMap(QuizMapper.from_parsed_to_cleaned_all)` runs on a raw parsed quiz question (which may bundle multiple statements under one image). |
| **quiz question** | The persisted DB entity/table (`quiz_questions`) — the post-flatten, post-dedup unit that gets embedded and stored. |
| **answer-blind** (describer design) | Design property of `RoadSignDescriberAgent`: its request DTO never includes `correct_answer`, so the image description can't leak or be biased by the correct answer. Rule verification against the true/false statement is deferred to `NormReferenceDescriberAgent`, which does receive `correct_answer`. See `adr/` for the accepted decision. |
| **norm reference** | A citation from a quiz item back to a specific CdS/CAP article/comma, generated by `NormReferenceDescriberAgent`/`NormReferenceEnricherService` and stored in `QuizMetadata` for future RAG retrieval. |
| **vector_search_queries** | `QuizMetadata` field: phrases generated for semantic search over the CdS text. One of six inputs to the **variant** registry (`search_queries`, `combined`, `combined_description`); persisted as a `quiz_questions.vector_search_queries TEXT[]` column since spec 0008 Phase 1 (completing `adr/0002-flatten-quiz-metadata-columns.md`, which had originally excluded it as embedder-input-only). |
| **variant** | One named text-composition rule a quiz question's query vector can be built from, registered in `QUIZ_VARIANT_REGISTRY` (`services/quiz/quiz_variant_registry.py`, spec 0008 AD-7, entries typed as `services/quiz/quiz_variant_spec.py::QuizVariantSpec` — a local dataclass, not generalized into `commons/ai/embedding/`, ADR 0014 rejected): `text` (question text alone), `topic_text` (topic + text + image description when present), `search_queries`, `combined` (topic + text + search queries), `combined_description` (`combined` + image description), `image_description` (image questions only). Stored as a row in `quiz_question_embeddings` (`variant` column), never a column of its own — adding one costs an ingest run, not a schema change (AD-2). |
| **arm** | One `(variant, model_column)` pair the retrieval evaluation harness measures (spec 0008 Phase 2, FR-3) — the unit `MultiArmRetrievalEvaluator` enumerates, evaluates, and reports in `MultiArmEvaluationSummary.arms`. Labelled by variant alone when only one model column is populated, `variant::model_column` otherwise. The `search_queries` arm is the configured baseline; every other arm carries a `RankingDelta` against it. |
| **fusion arm** | The one arm with no stored vector: for each question with both a `topic_text` and a `text` variant row (`image_description` joining in when present), its constituent `dense_top_k` rankings are retrieved independently and fused by citation identity via Reciprocal Rank Fusion (`commons.ai.utils.reciprocal_rank_fusion`) — never a fused vector, per spec 0008 AD-3. |
| **embed_repealed** | Config flag (`IngestorConfig.embed_repealed`, default `False`) controlling whether repealed law articles get indexed/embedded at all. |
| **image_description** | The flat `f"{name}. {description}"` string on `EnrichedQuizModel`, one per distinct image (see **answer-blind**). Consumed downstream by `NormReferenceEnricherService`, the HTML review viewer, and `EmbeddedQuizModel`. |
| **image_analysis** | `ImageAnalysis` model (`visual_analysis`, `name`, `description`) — the full, structured `RoadSignDescriberAgent` output, persisted inline on `EnrichedQuizModel.image_analysis` for debugging only; not part of the embedding or DB path. `visual_analysis` is the agent's chain-of-thought observation of the image, ahead of the two other fields. |
| **retrieval judge** | The LLM-as-judge measurement in `src/retrieval_evaluation/`: for a sampled quiz question, `RetrievalJudgeAgent` decides whether its top-`k` `CorpusReadRepository.dense_top_k` commas clearly and unambiguously justify the correct answer (`is_clear: bool` + `rationale`). Distinct from the deterministic **retrieval evaluation harness** (spec 0007, `ingest evaluate retrieval`), which excludes an LLM judge as a Non-Goal — see `adr/0013-retrieval-judge-separate-module.md`. |
| **golden set** | The persisted, labeled ground-truth dataset produced by `label-golden-set` (`src/retrieval_evaluation/`, spec 0011 phase 2): for each labeled quiz question, which `article_commas` justify its correct answer, according to `CommaLabelerAgent`. Distinct from the **retrieval judge** above — that tool spot-checks and writes nothing; this one persists every verdict to three tables (`labeling_runs`/`quiz_labelings`/`quiz_comma_labels`, see `docs/database.md`), intended as ground truth for a future retrieval-metrics spec. |
| **labeling run** | One execution of `label-golden-set`, recorded as one `labeling_runs` row: the judge model, prompt version, candidate variant, both arm depths, shuffle seed, corpus commit, corpus comma count, and the requested `--limit` (`NULL` for a full pass). Reconstructing the exact candidate set and presentation order any labeling saw requires only the run's stored seed and depths, against the same corpus state (FR-11). |
| **candidate comma** | One `article_commas` row considered for a question during labeling, carrying its one-based rank within each retrieval arm that found it (`CandidateComma.dense_rank`/`text_rank`, at least one non-`None`) — built by `CandidateSetService.build` as the union of the dense and text arms, never truncated or fused into one score (AD-3). |
| **two-arm union** | The candidate set a labeling run presents to the judge: every comma returned by `dense_top_k` **or** `text_match_top_k` (configured depths, default 50 each), deduplicated by comma id, not intersected or reciprocal-rank-fused. Distinct from the retrieval evaluation harness's **fusion arm**, which *does* fuse by RRF — the golden set deliberately shows the judge everything either arm found. |
| **lexeme** | A stemmed, stop-word-filtered token as PostgreSQL's own `to_tsvector('italian', ...)` produces it — extracted via `CorpusReadRepository.extract_lexemes` from a question's configured text fields (`LabelingConfig.lexeme_fields`: `topic`/`text`/`image_description`) and fed back into `text_match_top_k`'s `to_tsquery`, so extraction and search always agree on the same dictionary (AD-9). |
| **judge_rank** | The comma labeler's own 1-based ordering of the (at most three) candidates it names as justifying an answer, most-justifying first — persisted on `quiz_comma_labels.judge_rank`, distinct from `dense_rank`/`text_rank` (which record each retrieval arm's position, not the judge's opinion). |
| **outcome (of a labeling)** | Whether a `quiz_labelings` row has any `quiz_comma_labels` children — **derived** by counting them, never stored as a column: zero children means "the corpus does not justify this question" (a real, meaningful result); no `quiz_labelings` row at all for a question means "never labeled" — a different thing entirely (AD-6). |

*Last updated: 2026-08-01 — verified against commit `3cce407`; added
**Regolamento** entry and widened **CdS**/**corpus normativo**/**source** to
three sources (`cds`/`cap`/`reg`) for spec 0003 Phase 1.*

*Last updated: 2026-08-06 — verified against commit `91c4fe7`; the **element id**
entry's dead `docs/plans/2026-07-17--per-element-knowledge-layers.md` citation
(removed by commit `0a18903`) replaced with a pointer to `docs/architecture.md`
and `specs/0006-quiz-per-element-layers.md`.*

*Last updated: 2026-08-06 — verified against commit `91c4fe7`; added **retrieval
judge**, the new `src/retrieval_evaluation/` LLM-as-judge module (ADR 0013).*

*Last updated: 2026-08-07 — verified against commit `bbbb291`; spec 0008 landed in full.
**vector_search_queries** corrected — it is persisted (Phase 1), not excluded.
**embedded_text** corrected — the quiz side dropped the pattern (Phase 2, AD-9). Added
**variant**, **arm**, and **fusion arm** for the new multi-representation embedding and
multi-arm evaluation vocabulary (Phase 2, AD-2/AD-3/AD-7).*

*Last updated: 2026-08-07 — verified against commit `bbec1a0` (working tree ahead of it,
uncommitted on `feat/ingestion`); updated `LayerResolver` → `LayerResolverProvider` (**layer**
entry) and `NormReferenceEnricher` → `NormReferenceEnricherService` (**norm reference**,
**image_description** entries) for the `services/`/`providers/` restructuring.*

*Last updated: 2026-08-08 — verified against commit `8d85a0bc` (working tree ahead of it,
uncommitted). **variant** entry corrected — `QuizVariantSpec` was *not* deleted/generalized:
ADR 0014 (moving the dedup/omission/fan-out mechanics into `commons/ai/embedding/` as
`VariantSpec[T]`) was rejected, see `docs/adr/0014-embedding-composition-layer.md`.
`QuizVariantSpec` is now a local frozen dataclass (`services/quiz/quiz_variant_spec.py`) whose
`text_composer` field is typed `commons.ai.embedding.OptionalTextComposer[EmbeddedQuizModel]`
(`compose_or_none(model) -> str | None`) — see `docs/patterns.md`. **embedded_text** entry
removed — `EmbeddableArticleComma.embedded_text` (the computed property) is deleted, the term
no longer exists in code; the knowledge side now composes the same title+text join
declaratively, inline in `orchestrators/knowledge_flows.py`'s `EmbedCommasStep` wiring, see
`docs/patterns.md`.*

*Last updated: 2026-08-21 — verified against commit `e4977a94` (working tree ahead: spec
0011 phase 2). Added **golden set**, **labeling run**, **candidate comma**, **two-arm
union**, **lexeme**, **judge_rank**, and **outcome (of a labeling)** for the new
`label-golden-set` entry point and its three persisted tables.*
