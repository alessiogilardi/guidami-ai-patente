# pywire — Spring-style DI, scoped to `src/guidami_ai_patente/` only

`pywire` (git dependency, see `pyproject.toml`) is a Spring Boot-style IoC container:
`@component`/`@service`/`@repository`/`@client`/`@agent` decorators (all aliases of the
same registration, `pywire/decorators.py`) register a class on the process-wide default
container (`get_default_container()`); fields annotated `Autowired[T]` are populated by
the container after instantiation (`Container._instrument`, `pywire/container.py`).

## Scope — does not apply to the ingestion pipeline

This pattern applies **only** to the FastAPI app under `src/guidami_ai_patente/`
(routers, services, repositories, mappers, configs). It does **not** apply to
`src/guidami_ai_patente_ingestor/` or `src/commons/`, which keep manual constructor
injection per [`dependency-injection.md`](./dependency-injection.md) unchanged. The two
packages intentionally use different DI styles — do not "harmonize" one into the other.

## Convention — pure field injection, Spring style

- Every service/repository/client/router-dependency class in `src/guidami_ai_patente/`
  is decorated with the role-appropriate pywire decorator (`@service` for
  `services/`, `@repository` for `repositories/`, `@client` for `clients/`, `@component`
  otherwise) — mirrors the `@Service`/`@Repository`/`@Component` split in Spring.
- Dependencies are declared as class-level `Autowired[T]` fields, **not** as constructor
  parameters:

  ```python
  from pywire import Autowired, service

  @service
  class QuizAnswerChecker:
      repository: Autowired[QuizQuestionRepository]

      def check(self, question_id: int, answer: str) -> bool:
          question = self.repository.get(question_id)
          return question.correct_answer == answer
  ```

- This intentionally **overrides**, within this package only, the general
  `dependency-injection.md` rule (constructor args, deps last) and the
  `rules/python/architecture.md` "DI over global state" guidance — the pywire default
  container is deliberately the app's composition root, resolved once at startup.
- Do not hand-instantiate a `@service`/`@repository`/`@client` class directly
  (`QuizAnswerChecker()`); resolve it from the container
  (`get_default_container().get(QuizAnswerChecker)`), typically only at the FastAPI
  wiring boundary (dependency-injected into a router via `Depends`, or resolved once in
  `main.py`/`api/app.py`).
- `AppConfig` (`configs/app_config.py`) is data, not a component: it is loaded once at
  the entry point (`main.py`, per `rules/python/architecture.md`) and, if a component
  needs it, exposed to the container as a registered instance/provider — it is not
  autowired as if it were itself a `@component`.
