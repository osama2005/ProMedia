"""Library favorites/tags/sorting test.

Run from the project root:  python tests/library_favorites_test.py
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from app.config import ConfigManager
        from app.core.failures import FailureStore
        from app.core.history import HistoryStore

        with tempfile.TemporaryDirectory() as tmp:
            hist = HistoryStore(path=Path(tmp) / "history.json", limit=50)
            specs = [
                ("Alpha", "https://a.example/1", "a.mp4", 1000, "2026-01-01T00:00:00"),
                ("Beta", "https://b.example/2", "b.mp3", 5000, "2026-02-01T00:00:00"),
                ("Gamma", "https://c.example/3", "c.mp4", 3000, "2026-03-01T00:00:00"),
            ]
            ids = {}
            for title, url, filename, size, stamp in specs:
                entry = hist.add(title, url, filename, size, "example")
                ids[title] = entry["id"]
            with hist._lock:
                for item, spec in zip(hist._items, reversed(specs)):
                    item["timestamp"] = spec[4]

            if any(e["favorite"] or e["tags"] for e in hist.entries()):
                raise AssertionError("new entries must start unfavorited and untagged")

            if hist.toggle_favorite(ids["Beta"]) is not True:
                raise AssertionError("toggle_favorite should return the new state")
            hist.set_tags(ids["Beta"], ["work", "important", "work"])
            if hist.favorite_count() != 1:
                raise AssertionError("favorite count mismatch")
            if hist.entries()[1]["tags"] != ["work", "important"]:
                raise AssertionError("tags should be de-duplicated")

            reloaded = HistoryStore(path=Path(tmp) / "history.json")
            beta = reloaded.find_by_url("https://b.example/2")
            if not beta or not beta["favorite"] or beta["tags"] != ["work", "important"]:
                raise AssertionError("favorite/tags did not persist across reload")
            print("[ok] HistoryStore: favorites, tags, dedup, persistence")

            import customtkinter as ctk
            from app.ui.app import MediaDownloaderApp

            ctk.set_appearance_mode("dark")
            config = ConfigManager(path=Path(tmp) / "config.json")
            app = MediaDownloaderApp(
                config=config,
                history=hist,
                failures=FailureStore(path=Path(tmp) / "failures.json"),
            )
            app.update()

            def titles() -> list[str]:
                return [e["title"] for e in app._filtered_history()[1]]

            app.favorites_only = True
            if set(titles()) != {"Beta"}:
                raise AssertionError(f"favorites filter mismatch: {titles()!r}")
            app.favorites_only = False

            app.history_query = "important"
            if titles() != ["Beta"]:
                raise AssertionError(f"tag search mismatch: {titles()!r}")
            app.history_query = ""

            expected = {
                "size_desc": ["Beta", "Gamma", "Alpha"],
                "size_asc": ["Alpha", "Gamma", "Beta"],
                "name_desc": ["Gamma", "Beta", "Alpha"],
                "date_asc": ["Alpha", "Beta", "Gamma"],
                "date_desc": ["Gamma", "Beta", "Alpha"],
            }
            for mode, want in expected.items():
                app.library_sort = mode
                if titles() != want:
                    raise AssertionError(f"sort {mode}: got {titles()!r}, want {want!r}")
            print("[ok] filters: favorites chip, tag search, 5 sort modes")

            app.favorites_only = True
            app._refresh_history()
            app.favorites_only = False
            app._set_library_sort("type")
            if app.settings.library_sort != "type":
                raise AssertionError("sort choice was not saved")
            app._show_sort_menu()
            if app._sort_menu is None:
                raise AssertionError("sort menu did not open")
            app._close_sort_menu()
            print("[ok] UI wiring: refresh, sort persistence, sort menu")

            before = hist.find_by_url("https://c.example/3")["favorite"]
            app.toggle_history_favorite({"id": ids["Gamma"]})
            after = hist.find_by_url("https://c.example/3")["favorite"]
            if after == before or not after:
                raise AssertionError("card/context favorite toggle did not persist")
            if len(app._filtered_history()[1]) != 3:
                raise AssertionError("all entries should still be visible")
            print("[ok] favorite toggle from card/context menu")

            app.destroy()
            print("[ok] destroyed cleanly")
            return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
