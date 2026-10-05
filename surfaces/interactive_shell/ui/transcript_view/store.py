"""Width-independent transcript the full-screen shell redraws on every resize.

The shell used to print its transcript straight into terminal scrollback. Once
printed, the terminal owned those rows and re-wrapped them by its own rules on a
width change, so every resize repair was a guess about what the terminal did.
This store keeps the transcript as entries that render themselves at any width:
Rich renderables re-lay-out (wrapping, tables, panels), and captured ANSI text is
re-wrapped by Rich with its old-width padding removed.
"""

from __future__ import annotations

import io
import re
import threading
from collections import OrderedDict, deque
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from prompt_toolkit.formatted_text import ANSI, to_formatted_text
from rich.console import Console, RenderableType
from rich.style import Style
from rich.text import Text

Fragment = tuple[str, str]
Row = tuple[Fragment, ...]

# Keep the newest entries; older ones fall out of the full-screen view only.
_MAX_ENTRIES = 20_000
# A drag visits many widths; remember rows for the latest few per entry.
_WIDTH_CACHE_SIZE = 3

_CLEAR_SCREEN = re.compile(r"\x1b\[[23]J")
# OSC strings, CSI sequences, then any other ESC-led byte (or a lone ESC).
_ESCAPE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|\x1b[0-~]?")


def _keep_sgr(match: re.Match[str]) -> str:
    sequence = match.group(0)
    return sequence if sequence.startswith("\x1b[") and sequence.endswith("m") else ""


def sanitize_terminal_text(text: str) -> str:
    """Keep printable text and SGR styling; drop cursor, mode and OSC sequences."""
    text = _ESCAPE.sub(_keep_sgr, text.replace("\r\n", "\n"))
    return "".join(
        char for char in text if char in "\n\r\t\x1b" or (ord(char) >= 0x20 and char != "\x7f")
    )


def _resolve_carriage_returns(line: str) -> str:
    """Model a bare CR as an overwrite of the line so far, like a terminal row."""
    return line.rsplit("\r", 1)[-1] if "\r" in line else line


def _has_background(line: Text, offset: int) -> bool:
    style = line.style if isinstance(line.style, Style) else Style.parse(line.style or "none")
    if style.bgcolor is not None:
        return True
    for span in line.spans:
        if span.start <= offset < span.end:
            span_style = span.style if isinstance(span.style, Style) else Style.parse(span.style)
            if span_style.bgcolor is not None:
                return True
    return False


def trim_row_padding(line: Text) -> Text:
    """Drop trailing spaces a renderer added to fill its old width.

    Spaces painted with a background colour are content (a code block's bar),
    so they stay.
    """
    plain = line.plain
    content_end = len(plain.rstrip(" "))
    keep = content_end
    for offset in range(len(plain) - 1, content_end - 1, -1):
        if _has_background(line, offset):
            keep = offset + 1
            break
    return line if keep == len(plain) else line[:keep]


def ansi_renderable(text: str) -> Text:
    """Turn captured terminal text into a Rich text that re-wraps at any width."""
    lines = Text.from_ansi(text).split("\n", allow_blank=True)
    return Text("\n").join(trim_row_padding(line) for line in lines)


def render_rows(renderable: RenderableType, width: int) -> tuple[Row, ...]:
    """Render ``renderable`` at ``width`` into prompt-toolkit fragment rows."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=max(1, width),
        force_terminal=True,
        color_system="truecolor",
        highlight=False,
        legacy_windows=False,
        soft_wrap=False,
    )
    console.print(renderable, overflow="fold")
    rendered = buffer.getvalue()
    if rendered.endswith("\n"):
        rendered = rendered[:-1]
    rows: list[Row] = []
    for line in rendered.split("\n"):
        rows.append(tuple((style, chunk) for style, chunk, *_ in to_formatted_text(ANSI(line))))
    return tuple(rows)


@dataclass(eq=False)
class TranscriptEntry:
    """One printed block; ``on_normal_screen`` once it is in terminal scrollback."""

    renderable: RenderableType
    on_normal_screen: bool = False
    _rows: OrderedDict[int, tuple[Row, ...]] = field(default_factory=OrderedDict, repr=False)

    def rows(self, width: int) -> tuple[Row, ...]:
        cached = self._rows.get(width)
        if cached is not None:
            self._rows.move_to_end(width)
            return cached
        rows = render_rows(self.renderable, width)
        self._rows[width] = rows
        if len(self._rows) > _WIDTH_CACHE_SIZE:
            self._rows.popitem(last=False)
        return rows


class TranscriptStore:
    """Thread-safe transcript: writers append, the full-screen view reads the tail."""

    def __init__(self, *, max_entries: int = _MAX_ENTRIES) -> None:
        self._entries: deque[TranscriptEntry] = deque(maxlen=max(1, max_entries))
        self._pending = ""
        self._pending_on_normal_screen = False
        self._generation = 0
        self._lock = threading.RLock()
        self.on_change: Callable[[], None] | None = None

    @property
    def generation(self) -> int:
        """Increments on every change; lets the view keep its scroll anchor."""
        return self._generation

    def append_renderable(
        self, renderable: RenderableType, *, on_normal_screen: bool = False
    ) -> None:
        """Add a block that is re-rendered at the current width on every paint."""
        with self._lock:
            self._close_pending_line()
            self._entries.append(TranscriptEntry(renderable, on_normal_screen=on_normal_screen))
            self._changed()

    def append_text(self, text: str, *, on_normal_screen: bool = False) -> None:
        """Add terminal output; a clear-screen sequence empties the transcript first."""
        clear_at = max((match.end() for match in _CLEAR_SCREEN.finditer(text)), default=None)
        with self._lock:
            if clear_at is not None:
                self._clear_locked()
                text = text[clear_at:]
            text = sanitize_terminal_text(text)
            if not text:
                if clear_at is not None:
                    self._changed()
                return
            combined = self._pending + text
            complete, newline, rest = combined.rpartition("\n")
            if newline:
                lines = [_resolve_carriage_returns(line) for line in complete.split("\n")]
                # A line started off-screen is only in scrollback if all of it is.
                written = on_normal_screen and (self._pending_on_normal_screen or not self._pending)
                self._entries.append(
                    TranscriptEntry(ansi_renderable("\n".join(lines)), on_normal_screen=written)
                )
            self._pending = rest
            self._pending_on_normal_screen = on_normal_screen
            self._changed()

    def clear(self) -> None:
        """Forget every entry (``/clear``, ``/new``)."""
        with self._lock:
            self._clear_locked()
            self._changed()

    def tail_rows(self, width: int, count: int) -> tuple[list[Row], bool]:
        """Return the newest ``count`` rows at ``width`` and whether older rows exist."""
        with self._lock:
            entries = list(self._entries)
            pending = _resolve_carriage_returns(self._pending)
        rows: list[Row] = []
        if pending:
            rows = list(render_rows(ansi_renderable(pending), width))
        for entry in reversed(entries):
            if len(rows) >= count:
                return rows[-count:], True
            rows[:0] = entry.rows(width)
        return rows[-count:] if len(rows) > count else rows, len(rows) > count

    def take_unflushed(self) -> list[TranscriptEntry]:
        """Return entries not yet in terminal scrollback, marking them as written."""
        with self._lock:
            self._close_pending_line()
            unflushed = [entry for entry in self._entries if not entry.on_normal_screen]
            for entry in unflushed:
                entry.on_normal_screen = True
            return unflushed

    def _close_pending_line(self) -> None:
        if self._pending:
            line = _resolve_carriage_returns(self._pending)
            self._entries.append(
                TranscriptEntry(
                    ansi_renderable(line), on_normal_screen=self._pending_on_normal_screen
                )
            )
            self._pending = ""

    def _clear_locked(self) -> None:
        self._entries.clear()
        self._pending = ""

    def _changed(self) -> None:
        self._generation += 1
        callback = self.on_change
        if callback is not None:
            callback()


def render_for_scrollback(entries: Iterable[TranscriptEntry], width: int) -> str:
    """Render entries as terminal text for the normal screen (CRLF line ends)."""
    buffer = io.StringIO()
    console = Console(
        file=buffer,
        width=max(1, width),
        force_terminal=True,
        color_system="truecolor",
        highlight=False,
        legacy_windows=False,
    )
    for entry in entries:
        console.print(entry.renderable, overflow="fold")
    return buffer.getvalue().replace("\r\n", "\n").replace("\n", "\r\n")


__all__ = [
    "Row",
    "TranscriptEntry",
    "TranscriptStore",
    "ansi_renderable",
    "render_for_scrollback",
    "render_rows",
    "sanitize_terminal_text",
    "trim_row_padding",
]
