import time

from mentor.adapters.telegram.fake import FakeChat
from mentor.usecases.progress import LIMIT, Progress


class _Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def _progress(tmp_path=None, interval=3600):
    clock = _Clock()
    chat = FakeChat()
    path = tmp_path / "steps.md" if tmp_path else None
    return Progress(chat, "Fix <tests>", "coding · claude sonnet · effort high", path, interval, clock), chat, clock


def test_running_then_finished(tmp_path):
    progress, chat, clock = _progress(tmp_path)
    progress.start()
    progress.step("ran `npm test` & more")
    clock.t = 190
    running = progress.render()
    assert running == ("⏳ Fix &lt;tests&gt;\ncoding · claude sonnet · effort high · 3m 10s\n"
                       "<blockquote>ran `npm test` &amp; more</blockquote>")
    progress.finish("done", "All <b>green</b>", "\n\nFiles:\n- a.md")
    (msg_id, final), = chat.html_edits
    assert msg_id == 1 and chat.html_sent == ["⏳ Fix &lt;tests&gt;\ncoding · claude sonnet · effort high · 0s"]
    assert final.startswith("✅ Done: Fix &lt;tests&gt;\n")
    assert "<blockquote expandable>✓ ran `npm test` &amp; more</blockquote>\nAll &lt;b&gt;green&lt;/b&gt;\n\nFiles:" in final
    assert "ran `npm test` & more" in (tmp_path / "steps.md").read_text()


def test_long_log_keeps_newest_and_long_brief_is_cut():
    progress, chat, _ = _progress()
    for i in range(500):
        progress.step(f"step {i} " + "x" * 50)
    progress.finish("failed", "y" * 5000)
    final = chat.html_sent[-1]
    assert len(final) <= LIMIT and "earlier steps in steps.md)" in final and "step 499" in final
    assert final.endswith("y…") and "step 0 " not in final


def test_ticker_edits_with_elapsed_time_and_survives_edit_errors():
    progress, chat, clock = _progress(interval=0.01)
    calls = []

    def flaky_edit(id, text):
        calls.append(text)
        raise OSError("telegram down")

    chat.edit_html = flaky_edit
    progress.start()
    clock.t = 75
    deadline = time.monotonic() + 2
    while not calls and time.monotonic() < deadline:
        time.sleep(0.01)
    progress.finish("done")
    assert calls and "1m 15s" in calls[0]
