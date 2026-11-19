"""SHA-256 integrity verification test.

Run from the project root:  python tests/hash_verification_test.py
"""
import hashlib
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONTENT = b"ProMediaDownloader SHA-256 test payload\n" * 4096
EXPECTED = hashlib.sha256(CONTENT).hexdigest()


def _pump(app, predicate, timeout: float = 12.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.update()
        if predicate():
            return True
        time.sleep(0.03)
    return False


def main() -> int:
    try:
        from app.config import ConfigManager
        from app.core.failures import FailureStore
        from app.core.history import HistoryStore, HASH_STATUSES
        from app.ui.app import MediaDownloaderApp
        from app.utils.hash import normalize_sha256, sha256_file

        # -- pure helpers -------------------------------------------------
        if sha256_file.__name__ != "sha256_file":
            raise AssertionError("unexpected helper import")
        if normalize_sha256("  " + EXPECTED.upper() + " ") != EXPECTED:
            raise AssertionError("normalize_sha256 should uppercase/strip spaces")
        if normalize_sha256("SHA256:" + EXPECTED) != EXPECTED:
            raise AssertionError("sha256: prefix should be accepted")
        if normalize_sha256("0x" + EXPECTED) != EXPECTED:
            raise AssertionError("0x prefix should be accepted")
        if normalize_sha256("deadbeef") or normalize_sha256("z" * 64):
            raise AssertionError("invalid digests must be rejected")
        print("[ok] hash helpers: normalisation, prefixes, validation")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "movie.bin"
            media.write_bytes(CONTENT)
            if sha256_file(media, chunk_size=97) != EXPECTED:
                raise AssertionError("chunked hashing produced a wrong digest")
            print("[ok] chunked SHA-256 matches hashlib on a real file")

            # -- store fields, defaults and persistence -------------------
            hist = HistoryStore(path=root / "history.json", limit=50)
            entry = hist.add("Test", "https://example.test/1", str(media), len(CONTENT), "test")
            if any(
                key not in entry
                for key in ("sha256", "hash_expected", "hash_status", "hash_checked_at")
            ) or entry["hash_status"] != "unchecked":
                raise AssertionError("new entries need clean integrity defaults")

            legacy = root / "legacy.json"
            legacy.write_text(
                '[{"id":"old","title":"Old","url":"https://old.test",'
                '"filepath":"old.bin","size":1,"platform":"x","favorite":false,'
                '"tags":[],"timestamp":"2020-01-01T00:00:00"}]',
                encoding="utf-8",
            )
            old = HistoryStore(path=legacy)
            if old.entries()[0]["hash_status"] != "unchecked":
                raise AssertionError("legacy entries must not be marked verified")
            print("[ok] history: new defaults and legacy back-compatibility")

            entry_id = entry["id"]
            if not hist.update_hash(entry_id, status="pending"):
                raise AssertionError("pending status update failed")
            if hist.entries()[0]["hash_status"] != "pending":
                raise AssertionError("pending status was not stored")
            if not hist.update_hash(entry_id, digest=EXPECTED.upper()):
                raise AssertionError("digest update failed")
            current = hist.entries()[0]
            if current["sha256"] != EXPECTED or current["hash_status"] != "verified":
                raise AssertionError(f"digest/status mismatch: {current!r}")
            if not current["hash_checked_at"]:
                raise AssertionError("verified entries need a checked-at timestamp")

            hist.update_hash(entry_id, expected="a" * 64)
            if hist.entries()[0]["hash_status"] != "mismatch":
                raise AssertionError("wrong expected hash must produce a mismatch")
            hist.update_hash(entry_id, expected=EXPECTED)
            if hist.entries()[0]["hash_status"] != "match":
                raise AssertionError("matching expected hash must produce a match")
            hist.update_hash(entry_id, status="missing")
            if hist.entries()[0]["hash_status"] not in HASH_STATUSES:
                raise AssertionError("invalid status stored")

            reloaded = HistoryStore(path=root / "history.json")
            saved = reloaded.entries()[0]
            if saved["sha256"] != EXPECTED or saved["hash_expected"] != EXPECTED:
                raise AssertionError("hash fields did not persist across reload")
            if saved["hash_status"] != "missing":
                raise AssertionError("last status did not persist")
            print("[ok] history: digest, expected match/mismatch, status, persistence")

            # -- UI wiring -------------------------------------------------
            config = ConfigManager(path=root / "config.json")
            app = MediaDownloaderApp(
                config=config,
                history=hist,
                failures=FailureStore(path=root / "failures.json"),
            )
            app.update()
            if not app.settings.verify_hashes:
                raise AssertionError("automatic verification should default to on")
            switch = app.pro_switches.get("verify_hashes")
            if switch is None or not bool(switch.get()):
                raise AssertionError("Pro settings must expose the verification switch")
            print("[ok] UI: automatic verification enabled in Pro settings")

            class FakeEvent:
                x = 12
                y = 12

            app._show_history_menu(FakeEvent(), dict(saved))
            menus = [w for w in app.winfo_children() if isinstance(w, __import__("customtkinter").CTkToplevel)]
            menu_text = " ".join(
                str(child.cget("text"))
                for menu in menus
                for child in menu.winfo_children()
                if hasattr(child, "cget")
            )
            if "SHA-256" not in menu_text:
                raise AssertionError("context menu is missing hash actions")
            print("[ok] UI: context menu offers verify + expected-hash actions")

            live_entry = hist.entries()[0]
            live_entry["filepath"] = str(media)
            app.verify_history_hash(live_entry)
            if not _pump(app, lambda: hist.entries()[0]["hash_status"] in ("verified", "match")):
                raise AssertionError(f"manual verify stalled: {hist.entries()[0]!r}")
            if hist.entries()[0]["sha256"] != EXPECTED:
                raise AssertionError("manual verify stored the wrong digest")
            label, _colour = app.hash_badge(hist.entries()[0])
            if "✓" not in label:
                raise AssertionError(f"verified badge missing check mark: {label!r}")
            print("[ok] UI: manual verification computed digest in a worker")

            class DummyWindow:
                def destroy(self):
                    pass

            app._save_expected_history_hash(live_entry, " not-a-hash ", DummyWindow())
            if hist.entries()[0]["hash_expected"] != EXPECTED:
                raise AssertionError("invalid expected digest must be rejected without overwriting")
            app._save_expected_history_hash(live_entry, " " + EXPECTED.upper() + " ", DummyWindow())
            if not _pump(app, lambda: hist.entries()[0]["hash_status"] == "match"):
                raise AssertionError(f"match status not reached: {hist.entries()[0]!r}")
            if "✓" not in app.hash_badge(hist.entries()[0])[0]:
                raise AssertionError("match badge missing check mark")
            app._save_expected_history_hash(live_entry, "b" * 64, DummyWindow())
            if not _pump(app, lambda: hist.entries()[0]["hash_status"] == "mismatch"):
                raise AssertionError(f"mismatch status not reached: {hist.entries()[0]!r}")
            if "⚠" not in app.hash_badge(hist.entries()[0])[0]:
                raise AssertionError("mismatch badge missing warning mark")
            print("[ok] UI: expected hash dialog stores match/mismatch with badges")

            # -- automatic verification after a completed download ---------
            auto = root / "auto.bin"
            auto.write_bytes(b"automatic verification " * 100)
            auto_digest = hashlib.sha256(auto.read_bytes()).hexdigest()
            app._record_history({
                "title": "Auto",
                "filepath": str(auto),
                "size": auto.stat().st_size,
                "platform": "test",
                "request": {"url": "https://example.test/auto", "thumbnail_path": ""},
            })
            if not _pump(app, lambda: any(
                e.get("url") == "https://example.test/auto"
                and e.get("hash_status") == "verified"
                for e in hist.entries()
            )):
                raise AssertionError(f"automatic verification failed: {hist.entries()[0]!r}")
            auto_entry = next(e for e in hist.entries() if e.get("url") == "https://example.test/auto")
            if auto_entry["sha256"] != auto_digest:
                raise AssertionError("automatic digest mismatch")
            print("[ok] UI: completed download is hashed automatically")

            app.destroy()
            print("[ok] destroyed cleanly")
            return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
