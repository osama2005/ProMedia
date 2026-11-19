"""Smoke test: build the whole UI without entering the Tk mainloop.

Run from the project root:  python tests/smoke_test.py
Catches startup NameErrors / geometry errors before building the EXE.
"""
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        import customtkinter as ctk
        from app.ui.app import MediaDownloaderApp, apply_palette as apply_app_palette
        from app.ui.theme import PALETTE_KEYS
        from app.ui.widgets import apply_palette as apply_widget_palette

        ctk.set_appearance_mode("light")
        app = MediaDownloaderApp()
        app.update_idletasks()

        pages = getattr(app, "pages", []) or []
        print(f"[ok] app built: {len(pages)} pages, palette={app.settings.palette}")

        # Visit every page to force lazy widgets to build, and verify the page
        # is actually raised to the top of the stacking order.  CTkScrollableFrame
        # overrides lift()/lower() but not tkraise(); using tkraise() here used
        # to leave scrollable pages hidden behind the last-created page.
        for i, page in enumerate(pages):
            try:
                app._switch_page(i, animate=False)
                app.update()
                outer = getattr(page, "_parent_frame", page)
                topmost = app.pages_host.winfo_children()[-1]
                if topmost is not outer:
                    raise AssertionError(f"page {i} was not raised to the top")
                print(f"[ok] page {i}")
            except Exception:
                print(f"[FAIL] page {i}")
                traceback.print_exc()
                return 1

        # Every palette must resolve cleanly in both appearance modes.
        for mode in ("light", "dark"):
            ctk.set_appearance_mode(mode)
            for key in PALETTE_KEYS:
                try:
                    apply_app_palette(key)
                    apply_widget_palette(key)
                    app.update_idletasks()
                except Exception:
                    print(f"[FAIL] palette {key} in {mode}")
                    traceback.print_exc()
                    return 1
        print(f"[ok] {len(PALETTE_KEYS)} palettes in light+dark")

        app.destroy()
        print("[ok] destroyed cleanly")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.stdout.flush()
    code = main()
    sys.stdout.flush()
    os._exit(code)
