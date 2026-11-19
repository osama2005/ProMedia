"""Responsive sizing test: live font/image/shape/spacing/column scaling.

Run from the project root:  python tests/resize_test.py
"""
import os
import sys
import traceback
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    try:
        import customtkinter as ctk
        from app.ui.app import MediaDownloaderApp

        ctk.set_appearance_mode("dark")
        app = MediaDownloaderApp()
        app.update()

        nav_font = app.nav_items[0].icon_label._font
        logo = app._logo_image

        # Feed a few fake completed downloads so the library grid is built.
        fake_entries = [
            {
                "id": f"resize-test-{index}",
                "title": f"clip {index}",
                "filepath": f"C:/tmp/clip{index}.mp4",
                "url": "",
                "platform": "test",
                "timestamp": date.today().isoformat(),
                "size": 1024 * 1024,
                "status": "done",
            }
            for index in range(8)
        ]
        app.history.entries = lambda: fake_entries
        app.library_view = "grid"
        app._refresh_history()
        app.update()

        samples = []
        for geometry in ("1040x740", "1180x900", "1500x1000", "1920x1080"):
            app.geometry(geometry)
            app.update()
            app.update_idletasks()
            app._apply_history_columns(force=True)
            app.update_idletasks()
            font_size = abs(int(nav_font.cget("size")))
            padx = int(app.nav_frame.grid_info().get("padx", 0) or 0)
            samples.append(
                (geometry, app._ui_scale_factor, font_size, tuple(logo._size),
                 padx, app._history_columns)
            )
            if app.thumb_label.winfo_width() <= 0:
                raise AssertionError("thumbnail collapsed after resize")
            print(
                f"[ok] {geometry}: scale={app._ui_scale_factor:.2f}, "
                f"font={font_size}, logo={tuple(logo._size)}, "
                f"nav padx={padx}, cols={app._history_columns}"
            )

        factors = [sample[1] for sample in samples]
        fonts = [sample[2] for sample in samples]
        pads = [sample[4] for sample in samples]
        columns = [sample[5] for sample in samples]
        if not (factors[0] < factors[1] < factors[2] <= factors[3]):
            raise AssertionError(f"scale did not grow with the window: {factors}")
        if not (fonts[0] < fonts[1] < fonts[2] <= fonts[3]):
            raise AssertionError(f"icon font did not follow the window: {fonts}")
        if not (pads[0] <= pads[1] <= pads[2] <= pads[3]):
            raise AssertionError(f"padding did not follow the window: {pads}")
        if not all(1 <= count <= 4 for count in columns):
            raise AssertionError(f"invalid library column count: {columns}")
        if columns[-1] < columns[0]:
            raise AssertionError(f"library columns shrank as window grew: {columns}")
        if len(app._scale_fonts) > 1200 or len(app._scale_spacings) > 2000:
            raise AssertionError("scaling registry grew unexpectedly")

        print(f"[ok] registry: {len(app._scale_fonts)} fonts, "
              f"{len(app._scale_images)} images, {len(app._scale_shapes)} shapes, "
              f"{len(app._scale_spacings)} spacings")
        app.destroy()
        print("[ok] destroyed cleanly")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
