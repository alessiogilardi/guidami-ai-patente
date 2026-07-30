from rich.console import Console
from rich.markup import escape
from rich.panel import Panel


def render_dry_run(console: Console, command: str, steps: list[str]) -> None:
    """Prints the step chain `command` would execute, with no side effects taken.

    Each step is markup-escaped: free-form text built from config values (sources,
    flags, ...) must never be interpreted as Rich markup -- e.g. a literal `[...]`
    substring would otherwise be silently swallowed as an (invalid) style tag.
    """
    body = "\n".join(f"- {escape(step)}" for step in steps)
    console.print(
        Panel(
            body,
            title=f"[bold yellow]DRY RUN[/bold yellow] ingest {command}",
            subtitle="no filesystem writes, no LLM calls, no DB access",
        )
    )
