"""Smart download rules test: engine, persistence and UI integration.

Run from the project root:  python tests/smart_rules_test.py
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
        from app.core.models import DownloadRequest, MediaInfo
        from app.core.rules import (
            DEFAULT_RULES,
            apply_rules,
            parse_size_text,
            safe_folder_name,
            sanitize_rules,
        )

        # -- pure helpers -------------------------------------------------
        defaults = sanitize_rules(None)
        if len(defaults) != len(DEFAULT_RULES) or any(r["enabled"] for r in defaults):
            raise AssertionError("default rules must be present but disabled")
        if parse_size_text("1.5 GB") != int(1.5 * 1024 ** 3):
            raise AssertionError("parse_size_text failed on GB")
        if parse_size_text("unknown") != 0:
            raise AssertionError("unknown size must be 0")
        folder = safe_folder_name("../../evil\\dir:name")
        if "/" in folder or "\\" in folder or ":" in folder or ".." in folder:
            raise AssertionError(f"folder name was not sanitised: {folder!r}")
        if safe_folder_name("   ") != "Media":
            raise AssertionError("blank folder name needs a safe fallback")
        print("[ok] helpers: defaults, size parsing, safe folder names")

        rules = sanitize_rules([
            {"id": "kind", "condition": "kind", "value": "video", "action": "subdir",
             "action_value": "Video", "enabled": True},
            {"id": "large", "condition": "size", "value": 200, "action": "subdir",
             "action_value": "Large Files", "enabled": True},
            {"id": "slow", "condition": "speed", "value": 500, "action": "max_height",
             "action_value": 480, "enabled": True},
            {"id": "keyword", "condition": "keyword", "value": "mix", "action": "audio_only",
             "enabled": True},
        ])
        request = DownloadRequest(
            url="https://example.test/video", title="my clip", mode="video",
            height=1080, dest_dir="C:/Downloads", platform="YouTube",
        )
        updated, applied = apply_rules(
            request, rules, approx_bytes=300 * 1024 ** 2, speed_kbps=200
        )
        parts = [part.lower() for part in Path(updated.dest_dir).parts]
        if "video" not in parts or "large files" not in parts:
            raise AssertionError(f"folder rules not applied: {updated.dest_dir!r}")
        if updated.height != 480:
            raise AssertionError(f"slow rule did not cap height: {updated.height!r}")
        if len(applied) != 3:
            raise AssertionError(f"expected 3 applied rules: {applied!r}")
        again, applied_again = apply_rules(
            updated, rules, approx_bytes=300 * 1024 ** 2, speed_kbps=200
        )
        if again.dest_dir != updated.dest_dir or applied_again:
            raise AssertionError("retry would re-apply the same rules")

        unknown, names = apply_rules(request, rules, approx_bytes=0, speed_kbps=0)
        lower_names = [str(name).lower() for name in names]
        if "large" in lower_names or "slow" in lower_names or unknown.height != request.height:
            raise AssertionError(f"unknown size/speed must not trigger rules: {names!r}")

        audio, _ = apply_rules(
            DownloadRequest(url="u", title="a mix", mode="video", height=1080),
            rules,
        )
        if audio.mode != "audio" or audio.height is not None:
            raise AssertionError("audio_only action failed")
        print("[ok] engine: kind/size/speed/keyword actions and retry safety")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manager = ConfigManager(path=root / "config.json")
            settings = manager.load()
            if len(settings.download_rules) != 4:
                raise AssertionError("new settings need 4 default rules")
            settings.download_rules[0]["enabled"] = True
            manager.save(settings)
            if not manager.load().download_rules[0]["enabled"]:
                raise AssertionError("rules did not persist")
            print("[ok] settings: rules stored and reloaded from config.json")

            import customtkinter as ctk
            from app.ui.app import MediaDownloaderApp

            ctk.set_appearance_mode("dark")
            app = MediaDownloaderApp(
                config=manager,
                history=HistoryStore(path=root / "history.json"),
                failures=FailureStore(path=root / "failures.json"),
            )
            app.update()
            if len(app.rule_widgets) != 4 or not hasattr(app, "rules_host"):
                raise AssertionError("Rules tab was not built")
            print("[ok] UI: rules tab renders 4 editable rules")

            app.rule_widgets[0]["switch"].select()
            app.rule_widgets[0]["value"].set("video")
            app._save_rule_changes()
            if not app.settings.download_rules[0]["enabled"]:
                raise AssertionError("switch change was not saved")
            if not manager.load().download_rules[0]["enabled"]:
                raise AssertionError("switch change was not persisted")

            class DummyWindow:
                def destroy(self):
                    pass

            app._save_custom_rule(
                "My rule", app.T("rule_condition_keyword"), "mix",
                app.T("rule_action_audio_only"), "", DummyWindow(),
            )
            if len(app.settings.download_rules) != 5:
                raise AssertionError("custom rule was not added")
            custom = app.settings.download_rules[-1]
            if custom["name"] != "My rule" or custom["condition"] != "keyword":
                raise AssertionError(f"custom rule malformed: {custom!r}")
            app._remove_rule(custom["id"])
            if len(app.settings.download_rules) != 4:
                raise AssertionError("custom rule was not removed")
            print("[ok] UI: add/remove custom rule, switch persistence")

            for widgets in app.rule_widgets:
                widgets["switch"].deselect()
            app.rule_widgets[0]["switch"].select()  # kind -> Video
            app.rule_widgets[2]["switch"].select()  # size -> Large Files
            app.rule_widgets[3]["switch"].select()  # speed -> 720p
            app._save_rule_changes()
            app.current_info = MediaInfo(
                url="https://example.test/video", title="clip",
                approx_size="300 MB", platform="YouTube",
            )
            app.current_mode_index = 0
            app._current_speed_kbps = lambda: 200.0
            req = app._make_request(
                "https://example.test/video", "clip", "YouTube", ""
            )
            parts = [part.lower() for part in Path(req.dest_dir).parts]
            if "video" not in parts or "large files" not in parts:
                raise AssertionError(f"UI did not apply folder rules: {req.dest_dir!r}")
            if req.height != 720:
                raise AssertionError(f"UI did not cap quality: {req.height!r}")
            print("[ok] UI: new download request honours rules and speed")

            app.destroy()
            print("[ok] destroyed cleanly")
            return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
