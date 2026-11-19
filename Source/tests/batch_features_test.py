"""Batch feature test: groups, duplicates, bandwidth, workspace, diagnostics.

Run from the project root:  python tests/batch_features_test.py
"""
import os
import sys
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        from app.config import ConfigManager, Settings, SPEED_LIMITS_KBPS
        from app.core.diagnostics import run_diagnostics
        from app.core.duplicates import cleanup_duplicates, find_duplicates
        from app.core.downloader import DownloadManager, build_ydl_opts
        from app.core.groups import GroupStore
        from app.core.history import HistoryStore
        from app.core.models import DownloadRequest
        from app.utils.trash import send_to_trash, trash_available

        # --------------------------------------------------------------
        # 1. GroupStore CRUD + persistence + live summary
        # --------------------------------------------------------------
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = GroupStore(path=root / "groups.json")
            g1 = store.add_group("University", "#4CAF88")
            g2 = store.add_group("Work", "#5B9BD5")
            if not g1 or not g2 or g1["id"] == g2["id"]:
                raise AssertionError("add_group must return unique groups")
            if not store.rename_group(g1["id"], "Lectures"):
                raise AssertionError("rename_group failed")
            if store.group_name(g1["id"]) != "Lectures":
                raise AssertionError("rename_group did not persist in memory")

            url = "https://example.test/watch?v=abc"
            if not store.assign(url, g1["id"]):
                raise AssertionError("assign failed")
            if store.group_for(url) != g1["id"]:
                raise AssertionError("group_for failed")
            if store.urls_for(g1["id"]) != [url]:
                raise AssertionError("urls_for failed")

            request = DownloadRequest(url=url, title="lecture", mode="video")
            snapshots = [{
                "status": "downloading",
                "request": request.__dict__,
            }]
            summary = store.summary(snapshots)
            lectures = next(s for s in summary if s["id"] == g1["id"])
            if lectures["active"] != 1 or lectures["total"] != 1:
                raise AssertionError(f"group summary wrong: {lectures!r}")

            # Reload from disk to prove persistence.
            reloaded = GroupStore(path=root / "groups.json")
            groups = reloaded.groups()
            if len(groups) != 2 or reloaded.group_for(url) != g1["id"]:
                raise AssertionError("groups did not persist across reload")
            if reloaded.group_name(g1["id"]) != "Lectures":
                raise AssertionError("rename did not persist across reload")

            # Unassign + remove cleanup.
            reloaded.unassign_url(url)
            if reloaded.group_for(url):
                raise AssertionError("unassign_url failed")
            if not reloaded.remove_group(g2["id"]) or len(reloaded.groups()) != 1:
                raise AssertionError("remove_group failed")
            print("[ok] groups: CRUD, URL membership, persistence and live summary")

        # --------------------------------------------------------------
        # 2. Duplicate detection (hash + name/size) and safe cleanup
        # --------------------------------------------------------------
        digest = "a" * 64
        base = {
            "title": "clip", "size": 10 * 1024 ** 2,
            "timestamp": "2026-01-01", "platform": "YouTube",
        }
        entries = [
            {**base, "id": "e1", "filepath": "/dl/clip.mp4", "sha256": digest},
            {**base, "id": "e2", "filepath": "/dl/clip (1).mp4", "sha256": digest},
            {**base, "id": "e3", "filepath": "/dl/song.mp4", "sha256": ""},
            {**base, "id": "e4", "filepath": "/dl/song (1).mp4", "sha256": ""},
        ]
        groups = find_duplicates(entries, min_size=1024)
        if len(groups) != 2:
            raise AssertionError(f"expected 2 duplicate groups, got {len(groups)}")
        hash_group = next(g for g in groups if g.reason == "hash")
        name_group = next(g for g in groups if g.reason == "name_size")
        if set(e["id"] for e in hash_group.entries) != {"e1", "e2"}:
            raise AssertionError("hash grouping wrong")
        if set(e["id"] for e in name_group.entries) != {"e3", "e4"}:
            raise AssertionError("name/size grouping wrong")
        # Hash group wins: an entry hashed above must not also appear in the
        # name/size group.
        hashed_ids = {e["id"] for e in hash_group.entries}
        if hashed_ids & {e["id"] for e in name_group.entries}:
            raise AssertionError("an entry leaked into two groups")

        # Cleanup only removes non-kept entries from the supplied groups.
        hist = HistoryStore(path=root / "dup_history.json")
        saved = []
        for entry in entries:
            saved.append(hist.add(entry["title"], f"url-{entry['id']}",
                                  entry["filepath"], entry["size"],
                                  entry["platform"]))
        real_ids = {str(e["filepath"]): str(e["id"]) for e in hist.entries()}
        cleanup_groups = []
        for group in groups:
            mapped = [{**e, "id": real_ids[e["filepath"]]} for e in group.entries]
            keep_path = next(
                e["filepath"] for e in group.entries if e["id"] == group.keep_id
            )
            cleanup_groups.append(type(group)(
                key=group.key, reason=group.reason, entries=mapped,
                wasted_bytes=group.wasted_bytes,
                keep_id=real_ids[keep_path],
            ))
        result = cleanup_duplicates(cleanup_groups, hist, delete_files=False)
        if result["history"] != 2:
            raise AssertionError(
                f"cleanup should remove exactly 2 duplicates, got {result['history']}"
            )
        print(f"[ok] duplicates: {len(groups)} groups, cleanup removed "
              f"{result['history']} history entries (trash available={trash_available()})")

        # --------------------------------------------------------------
        # 3. Bandwidth: request-level cap overrides global; -1 unlimited
        # --------------------------------------------------------------
        settings = Settings(speed_limit_kbps=512, download_dir=str(root / "dl"))
        opts = build_ydl_opts(
            DownloadRequest(url="u", title="t", mode="video"), settings, None
        )
        if opts.get("ratelimit") != 512 * 1024:
            raise AssertionError(f"global limit not applied: {opts.get('ratelimit')}")
        capped = build_ydl_opts(
            DownloadRequest(url="u", title="t", mode="video", speed_limit_kbps=1024),
            settings, None,
        )
        if capped.get("ratelimit") != 1024 * 1024:
            raise AssertionError("per-request cap did not override global")
        unlimited = build_ydl_opts(
            DownloadRequest(url="u", title="t", mode="video", speed_limit_kbps=-1),
            settings, None,
        )
        if "ratelimit" in unlimited:
            raise AssertionError("explicit unlimited must remove ratelimit")

        # --------------------------------------------------------------
        # 4. Live per-task speed change + group actions on the manager
        # --------------------------------------------------------------
        manager = DownloadManager(lambda: settings, None)
        request = DownloadRequest(
            url="https://example.test/g", title="g", mode="video",
            group="grp-1", speed_limit_kbps=256,
        )
        task = manager.enqueue(request)
        if task is None or manager.set_task_speed_limit(task.id, 2048) is not True:
            raise AssertionError("set_task_speed_limit failed on a queued task")
        if task.request.speed_limit_kbps != 2048:
            raise AssertionError("live speed change not stored on request")
        if manager.tasks_for_group("grp-1") != [task.id]:
            raise AssertionError("tasks_for_group failed")
        if manager.group_action("grp-1", "pause") != 1:
            raise AssertionError("group pause did not affect the queued task")
        if manager.group_action("grp-1", "start") != 1:
            raise AssertionError("group start did not resume the paused task")
        manager.shutdown()
        print("[ok] bandwidth: global/request/-1 limits, live change and group actions")

        # --------------------------------------------------------------
        # 5. Diagnostics (offline, no network)
        # --------------------------------------------------------------
        results = run_diagnostics(settings, None, history_count=0)
        keys = {r.key for r in results}
        for expected in ("python", "ytdlp", "ffmpeg", "download_dir", "palette"):
            if expected not in keys:
                raise AssertionError(f"missing diagnostic check: {expected}")
        if not any(r.key == "palette" and r.ok for r in results):
            raise AssertionError("forest palette should pass diagnostics")
        print(f"[ok] diagnostics: {len(results)} offline checks")

        # --------------------------------------------------------------
        # 6. Full UI: 8 nav items, workspace overlay, dialog openers
        # --------------------------------------------------------------
        import customtkinter as ctk
        from app.ui.app import MediaDownloaderApp

        ctk.set_appearance_mode("dark")
        cfg = ConfigManager(path=root / "config.json")
        cfg.load()
        app = MediaDownloaderApp(
            config=cfg,
            history=HistoryStore(path=root / "ui_history.json"),
            failures=__import__("app.core.failures", fromlist=["FailureStore"]).FailureStore(
                path=root / "ui_failures.json"
            ),
            groups=GroupStore(path=root / "ui_groups.json"),
        )
        app.update()

        if len(app.pages) != 8 or len(app.nav_items) != 8:
            raise AssertionError(f"sidebar must stay at 8 items: pages={len(app.pages)}")
        labels = [item.text_label.cget("text") for item in app.nav_items]
        # Compare against T() so the check works with or without the Arabic
        # reshaper installed (the packaged EXE always shapes the text).
        expected_labels = [app.T(key) for key in (
            "tab_home", "tab_download", "tab_active", "tab_queue",
            "tab_library", "tab_history", "tab_tools", "tab_settings",
        )]
        if labels != expected_labels:
            raise AssertionError(f"nav labels changed: {labels!r}")
        if getattr(app, "workspace_page", None) is None:
            raise AssertionError("workspace overlay was not built")

        # Open workspace, verify it sits above the pages and refreshes.
        app._toggle_workspace(True)
        app.update()
        if not app.workspace_visible:
            raise AssertionError("workspace did not open")
        app._refresh_workspace()
        app.update()

        # Switching a page must close the overlay and keep the 8-page stack.
        app._switch_page(4, animate=False)
        app.update()
        if app.workspace_visible:
            raise AssertionError("page switch must hide the workspace overlay")
        if app.current_tab_index != 4:
            raise AssertionError("page switch did not land on the library")
        print("[ok] UI: 8 nav items preserved, workspace overlay opens/refreshes/hides")

        # Dialog openers must construct and destroy cleanly (no modal grab
        # interference because we never call mainloop).
        openers = (
            "_open_duplicates", "_open_groups", "_open_diagnostics",
            "_open_onboarding",
        )
        for opener in openers:
            getattr(app, opener)()
            app.update()
        for attr in ("duplicates_dialog", "groups_dialog",
                     "diagnostics_dialog", "onboarding_dialog"):
            win = getattr(app, attr, None)
            if win is None:
                raise AssertionError(f"{attr} was not created")
            win.destroy()
        app.update()

        # _make_request must carry speed limit + group from the live menus.
        app.speed_menu.set(app.T("bw_set", speed=1024))
        grp = app.groups.add_group("TestGroup", "#4CAF88")
        app.groups.assign("https://example.test/req", grp["id"])
        app._refresh_group_choices()
        app.group_menu.set("TestGroup")
        req = app._make_request("https://example.test/req", "req", "YouTube", "")
        if req.speed_limit_kbps != 1024 or req.group != grp["id"]:
            raise AssertionError(
                f"request did not carry bandwidth/group: {req.speed_limit_kbps}, {req.group!r}"
            )
        print("[ok] UI: dialogs open, request carries speed limit and group")

        app.destroy()
        print("\nALL BATCH FEATURE CHECKS PASSED")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
