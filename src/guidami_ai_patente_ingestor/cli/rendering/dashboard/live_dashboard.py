import logging
from types import TracebackType

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, TaskID
from rich.text import Text

from .log_panel_handler import LogPanelHandler

_PROGRESS_REGION_SIZE = 3
_LOGS_REGION_SIZE = 17  # 15 records + 2 border lines (PD-9)


class LiveDashboard:
    """Single `rich.Live` owning the flow/step/item bars and the bordered log panel.

    Renders through one `Live(get_renderable=...)`, never a static renderable, so the
    log panel re-reads `LogPanelHandler`'s deque on the `Live` refresh thread (AD-6):
    every method below only mutates `Progress` state, no terminal I/O happens outside
    the refresh thread.
    """

    def __init__(self, console: Console, handler: LogPanelHandler) -> None:
        """Injects the console to render on and the log handler feeding the panel."""
        self._handler = handler
        self._progress = Progress(console=console)
        self._layout = Layout()
        self._layout.split_column(
            Layout(name="progress", size=_PROGRESS_REGION_SIZE),
            Layout(name="logs", size=_LOGS_REGION_SIZE),
        )
        self._live = Live(get_renderable=self._render, console=console, refresh_per_second=4)

        self._flow_task: TaskID | None = None
        self._step_task: TaskID | None = None
        self._items_task: TaskID | None = None
        self._flow_index = 0
        self._flow_total = 0
        self._step_index = 0

    @property
    def log_handler(self) -> LogPanelHandler:
        """The handler feeding the log panel, attached to the root logger on `__enter__`."""
        return self._handler

    def __enter__(self) -> "LiveDashboard":
        """Attaches the log handler to the root logger and starts the `Live` display."""
        logging.getLogger().addHandler(self._handler)
        self._live.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Stops the `Live` display and detaches/closes the log handler.

        Never suppresses an exception (FR-5): always returns `None`, and always tears
        down before the caller's exception, if any, propagates further.
        """
        self._live.stop()
        logging.getLogger().removeHandler(self._handler)
        self._handler.close()

    def _render(self) -> Layout:
        """Builds the current frame: the progress bars plus the bordered log panel."""
        self._layout["progress"].update(self._progress)
        self._layout["logs"].update(Panel(Text("\n".join(self._handler.snapshot())), title="Log"))
        return self._layout

    # -- ProgressReporter --------------------------------------------------

    def begin_run(self, total_flows: int) -> None:
        """Starts the flow bar for a run of `total_flows` flows."""
        self._flow_total = total_flows
        self._flow_index = 0
        self._flow_task = self._progress.add_task("", total=total_flows, completed=0)

    def begin_flow(self, name: str) -> None:
        """Advances the flow index and relabels the flow bar."""
        self._flow_index += 1
        assert self._flow_task is not None
        self._progress.update(
            self._flow_task, description=f"{self._flow_index}/{self._flow_total} {name}"
        )

    def end_flow(self) -> None:
        """Closes any open item track and advances the flow bar to the current index.

        The step bar is intentionally left in place at its final position: the next
        flow's `begin_step` relabels and resets it (FR-2 criterion 2 stays observable).
        """
        self._remove_items_task()
        assert self._flow_task is not None
        self._progress.update(self._flow_task, completed=self._flow_index)

    def begin_step(self, name: str, index: int, total: int) -> None:
        """Relabels the step bar to position `index` of `total`, one task for the run."""
        self._step_index = index
        if self._step_task is None:
            self._step_task = self._progress.add_task("", total=total, completed=0)
        self._progress.update(
            self._step_task,
            total=total,
            completed=index - 1,
            description=f"{index}/{total} {name}",
        )

    def end_step(self) -> None:
        """Closes any open item track (FR-3 criterion 5), then advances the step bar."""
        self._remove_items_task()
        assert self._step_task is not None
        self._progress.update(self._step_task, completed=self._step_index)

    def begin_items(self, label: str, total: int) -> None:
        """Opens a new item bar, removing any bar already open (FR-3 criterion 4)."""
        self._remove_items_task()
        self._items_task = self._progress.add_task(label, total=total, completed=0)

    def advance_item(self) -> None:
        """Advances the open item bar by one. No-op if none is open."""
        if self._items_task is not None:
            self._progress.advance(self._items_task)

    def end_items(self) -> None:
        """Removes the open item bar. No-op if none is open."""
        self._remove_items_task()

    def _remove_items_task(self) -> None:
        if self._items_task is not None:
            self._progress.remove_task(self._items_task)
            self._items_task = None
