"""Link Inbox test: URL extraction + batch enqueue wiring.

Run from the project root:  python tests/link_inbox_test.py
"""
import os
import sys
import traceback
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from app.utils.helpers import extract_urls

        pasted = "\n".join(
            [
                "https://a.example/watch?v=1",
                "www.b.example/clip/22",
                "https://c.example/x, https://d.example/y?z=1",
                "this is not a link",
                "https://a.example/watch?v=1",  # duplicate
            ]
        )
        urls = extract_urls(pasted)
        expected = [
            "https://a.example/watch?v=1",
            "https://www.b.example/clip/22",
            "https://c.example/x",
            "https://d.example/y?z=1",
        ]
        if urls != expected:
            raise AssertionError(f"extract_urls mismatch: {urls!r}")
        if extract_urls("") or extract_urls("hello world"):
            raise AssertionError("plain text should yield no links")
        print(f"[ok] extract_urls: {len(urls)} unique links, dedup + bare domain + multi-per-line")

        import customtkinter as ctk
        from app.ui.app import MediaDownloaderApp

        ctk.set_appearance_mode("dark")
        app = MediaDownloaderApp()
        app.update()

        app.settings.link_inbox = "https://saved.example/1"
        enqueued: list[str] = []

        def fake_enqueue(request, priority=0, delay_seconds=0):
            enqueued.append(request.url)

        with mock.patch.object(app.config, "save"), \
                mock.patch.object(app.manager, "enqueue", fake_enqueue), \
                mock.patch.object(app.history, "find_by_url", lambda url: None):
            app._open_link_inbox()
            dialog = app._link_inbox_dialog
            if "saved.example" not in dialog._text():
                raise AssertionError("dialog did not load the saved inbox text")
            dialog.textbox.delete("1.0", "end")
            dialog.textbox.insert("1.0", "https://x.example/1\nhttps://y.example/2")
            dialog._add()

        if enqueued != ["https://x.example/1", "https://y.example/2"]:
            raise AssertionError(f"unexpected enqueue batch: {enqueued!r}")
        if app.settings.link_inbox != "":
            raise AssertionError("inbox text was not cleared after a successful add")
        print(f"[ok] batch enqueue: {len(enqueued)} links added, inbox cleared")

        try:
            dialog.destroy()
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
