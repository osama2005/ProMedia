"""Failed Downloads Center test: persistence + retry wiring.

Run from the project root:  python tests/failed_center_test.py
"""
import os
import sys
import tempfile
import traceback
from dataclasses import asdict
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from app.config import ConfigManager
        from app.core.failures import FailureStore
        from app.core.history import HistoryStore
        from app.core.models import DownloadRequest

        with tempfile.TemporaryDirectory() as tmp:
            store = FailureStore(path=Path(tmp) / "failures.json", limit=50)
            entry = store.add(
                title="clip", url="https://x.example/1", error_key="err_network",
                error_detail="timed out", request={"url": "https://x.example/1"},
                attempt=1, priority=2,
            )
            store.add(
                title="clip", url="https://x.example/1", error_key="err_network",
                request={"url": "https://x.example/1"}, attempt=2,
            )
            if len(store.entries()) != 1:
                raise AssertionError("same URL should update, not duplicate")
            if store.entries()[0]["attempt"] != 2:
                raise AssertionError("attempt count did not advance")
            if store.stats()["total"] != 1 or store.stats()["transient"] != 1:
                raise AssertionError("stats mismatch")
            reloaded = FailureStore(path=Path(tmp) / "failures.json")
            if len(reloaded.entries()) != 1:
                raise AssertionError("failures did not persist across reload")
            reloaded.clear()
            if reloaded.entries():
                raise AssertionError("clear failed")
            print("[ok] FailureStore: dedup, attempts, stats, persistence, clear")

            import customtkinter as ctk
            from app.ui.app import MediaDownloaderApp

            ctk.set_appearance_mode("dark")
            config = ConfigManager(path=Path(tmp) / "config.json")
            app = MediaDownloaderApp(
                config=config,
                history=HistoryStore(path=Path(tmp) / "history.json"),
                failures=FailureStore(path=Path(tmp) / "failures-ui.json"),
            )
            app.update()

            request = DownloadRequest(url="https://y.example/v", title="video")
            payload = {
                "id": "task-1", "title": "video", "status": "error",
                "error_key": "err_network", "error_detail": "connection reset",
                "attempt": 1, "priority": 0, "request": asdict(request),
            }
            app._handle_event("failed", payload)
            if len(app.failures.entries()) != 1:
                raise AssertionError("failed event was not recorded")
            if "1" not in app.failed_count_label.cget("text"):
                raise AssertionError("failed badge did not update")
            print("[ok] failed event recorded + badge updated")

            enqueued: list[tuple] = []

            def fake_enqueue(req, priority=0, delay_seconds=0, attempt=1):
                enqueued.append((req.url, delay_seconds, attempt, priority))

            # Transient error with auto-retry enabled -> delayed re-enqueue.
            app.settings.auto_retry_failed = True
            with mock.patch.object(app.manager, "enqueue", fake_enqueue):
                app._handle_event("failed", payload)
            if not enqueued or enqueued[-1][1:] != (10, 2, 0):
                raise AssertionError(f"auto-retry parameters wrong: {enqueued!r}")
            print("[ok] auto-retry: network error re-scheduled after 10s (attempt 2)")

            # Non-transient error -> no automatic retry.
            enqueued.clear()
            hard = dict(payload, error_key="err_private")
            with mock.patch.object(app.manager, "enqueue", fake_enqueue):
                app._handle_event("failed", hard)
            if enqueued:
                raise AssertionError("private-video error must not auto-retry")
            print("[ok] non-transient error skipped by auto-retry")

            # Manual retry from the center removes the entry and re-enqueues.
            entry_id = app.failures.entries()[0]["id"]
            enqueued.clear()
            with mock.patch.object(app.manager, "enqueue", fake_enqueue):
                ok = app.retry_failure(entry_id)
            if not ok or not enqueued or enqueued[0][2] != 2:
                raise AssertionError(f"manual retry failed: {ok!r}, {enqueued!r}")
            if app.failures.entries():
                raise AssertionError("retried failure should be removed")
            print("[ok] manual retry re-enqueued with attempt 2 and cleared entry")

            app.failures.add(
                title="a", url="https://a.example/1", error_key="err_network",
                request={"url": "https://a.example/1"},
            )
            app._open_failed_center()
            if getattr(app, "_failed_center_dialog", None) is None:
                raise AssertionError("failed center dialog did not open")
            print("[ok] failed center dialog opens")

            try:
                app._failed_center_dialog.destroy()
            except Exception:
                pass
            app.destroy()
            print("[ok] destroyed cleanly")
            return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
