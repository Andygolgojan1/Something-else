"""Prompt-aware stdout proxy that keeps background output above the composer."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TextIO, cast

from prompt_toolkit.application import Application, run_in_terminal
from prompt_toolkit.patch_stdout import StdoutProxy

from surfaces.interactive_shell.ui.input_prompt.synchronized import synchronized_output
from surfaces.interactive_shell.ui.transcript_view import TranscriptStore

# In-band markers queued with the text so the flush thread sees them in order.
_TRANSIENT_START = "\x00opensre-transient-start\x00"
_TRANSIENT_END = "\x00opensre-transient-end\x00"


class _AppBoundStdoutProxy(StdoutProxy):
    """Run proxy flushes in the active prompt application's context.

    With a transcript, output is recorded there and the full-screen app redraws
    it; it reaches the terminal directly only while the app is not on screen.
    """

    def __init__(
        self,
        app: Application[str],
        *,
        raw: bool,
        transcript: TranscriptStore | None = None,
    ) -> None:
        self._target_app = app
        self._redraw_lock = asyncio.Lock()
        self._transcript = transcript
        # Read and written only by the flush thread.
        self._transient = False
        # Repaint sooner than the inline default: a full-screen redraw is cheap.
        super().__init__(sleep_between_writes=0.05 if transcript else 0.2, raw=raw)

    def begin_transient_output(self) -> None:
        """Paint what follows (an inline menu) without recording it."""
        self.flush()
        self._flush_queue.put(_TRANSIENT_START)

    def end_transient_output(self) -> None:
        """Resume recording output into the transcript."""
        self.flush()
        self._flush_queue.put(_TRANSIENT_END)

    def _get_app_loop(self) -> asyncio.AbstractEventLoop | None:
        if not self._target_app.is_running:
            return None
        return self._target_app.loop

    def _write_and_flush(
        self,
        loop: asyncio.AbstractEventLoop | None,
        text: str,
    ) -> None:
        if self._transcript is None:
            self._write_to_terminal(loop, text)
            return
        for segment in _split_markers(text):
            if segment == _TRANSIENT_START:
                self._transient = True
            elif segment == _TRANSIENT_END:
                self._transient = False
            elif self._transient:
                self._write_to_terminal(loop, segment)
            elif loop is None:
                # The full-screen app is off screen (startup, a picker): the
                # text lands in scrollback now and joins the transcript too.
                self._write_to_terminal(None, segment)
                self._transcript.append_text(segment, on_normal_screen=True)
            else:
                self._transcript.append_text(segment)

    def _write_to_terminal(self, loop: asyncio.AbstractEventLoop | None, text: str) -> None:
        def write_and_flush() -> None:
            self._output.enable_autowrap()
            if self.raw:
                self._output.write_raw(text)
            else:
                self._output.write(text)
            self._output.flush()

        async def write_above_prompt() -> None:
            # VT terminals keep the erase, write, and redraw transaction
            # off-screen until the composer is complete. Native Win32 runs
            # the same transaction without DEC private-mode bytes.
            async with self._redraw_lock:
                with synchronized_output(self._output):
                    await run_in_terminal(write_and_flush, in_executor=False)

        if loop is None:
            write_and_flush()
            return

        def write_in_app_context() -> None:
            context = self._target_app.context
            if context is None or not self._target_app.is_running:
                write_and_flush()
                return
            context.copy().run(
                self._target_app.create_background_task,
                write_above_prompt(),
            )

        loop.call_soon_threadsafe(write_in_app_context)


def _split_markers(text: str) -> Iterator[str]:
    """Yield text segments and transient markers in their original order."""
    while text:
        positions = [
            (index, marker)
            for marker in (_TRANSIENT_START, _TRANSIENT_END)
            if (index := text.find(marker)) >= 0
        ]
        if not positions:
            yield text
            return
        index, marker = min(positions)
        if index:
            yield text[:index]
        yield marker
        text = text[index + len(marker) :]


@contextmanager
def patch_prompt_stdout(
    app: Application[str],
    *,
    raw: bool = False,
    transcript: TranscriptStore | None = None,
) -> Iterator[None]:
    """Redirect stdout/stderr while preserving the active prompt on redraw."""
    with _AppBoundStdoutProxy(app, raw=raw, transcript=transcript) as proxy:
        original_stdout = sys.stdout
        original_stderr = sys.stderr
        sys.stdout = cast(TextIO, proxy)
        sys.stderr = cast(TextIO, proxy)
        try:
            yield
        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr


__all__ = ["patch_prompt_stdout"]
