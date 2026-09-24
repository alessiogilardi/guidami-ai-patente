# Agent config files — language-specific agents carry the language in the file name

An agent whose prompt and output are specific to **one target language** (today: every
agent that translates or explains *into Russian*) has its YAML config named
`<agent_name>.<lang>.yaml`, with `<lang>` an ISO 639-1 code:

```
configs/agents/
├── explanation_translator.ru.yaml   # IT → RU translation
├── explanation_writer.yaml          # Italian output: the project's base language, unsuffixed
├── question_explainer.yaml          # Italian output: base language, unsuffixed (spec 0020)
├── comma_labeler.yaml               # language-agnostic
└── retrieval_judge.yaml             # language-agnostic
```

An agent that produces Italian and is merely *followed*, at the API layer, by a
separate on-demand translation of its output (`POST /explanations/translate`, spec
0018) is not itself language-specific — it stays unsuffixed. Only an agent whose own
prompt targets one language as its output carries the suffix.

## Rules

- **Language-specific → suffixed; everything else → bare.** Italian is the project's
  base language, so an agent that writes Italian (`explanation_writer`) and every
  language-agnostic agent (judge, labeler, describers) stays unsuffixed. Only a target
  language *other than* Italian appears in a file name.
- **The suffix is part of the name passed to the loader.** `AgentConfigRepository.load`
  builds `f"{name}.yaml"`, so the agent's module-level constant is the dotted name:
  `_AGENT_NAME = "explanation_translator.ru"`. No loader change is needed.
- **The class name does not carry the language.** `ExplanationTranslatorAgent` stays as
  is: the language lives in the config file (prompt), not in code structure. A second
  language would add a second config file, and only then decide whether the agent needs
  a language parameter.
- **A rename is a refactor commit**, separate from feature work. It changes the file
  name and the `_AGENT_NAME` constant. The caller recorded in `llm_call_logs` is
  determined by the YAML's own `name:` field (independent of the filename) and does
  not change unless the YAML is also edited.
