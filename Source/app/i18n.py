"""Internationalisation (Arabic / English) for the application.

The module is UI-framework agnostic: :func:`translate` returns plain text,
while :func:`shape_for_tk` prepares Arabic strings for Tk/Tkinter, which does
not perform Arabic glyph shaping or bidirectional reordering by itself.
"""

from __future__ import annotations

from typing import Any

LANGUAGES = ("ar", "en")
LANGUAGE_NAMES = {"ar": "العربية", "en": "English"}
DEFAULT_LANGUAGE = "ar"

# ---------------------------------------------------------------------------
# Translation table: key -> {"ar": ..., "en": ...}
# ---------------------------------------------------------------------------
TRANSLATIONS: dict[str, dict[str, str]] = {
    # General / window
    "app_title": {"ar": "مُنزّل الوسائط الاحترافي", "en": "Pro Media Downloader"},
    "app_subtitle": {
        "ar": "نزّل الفيديو والصوت من يوتيوب وتيك توك وإنستغرام وفيسبوك",
        "en": "Download video & audio from YouTube, TikTok, Instagram, Facebook",
    },
    "tab_home": {"ar": "الرئيسية", "en": "Home"},
    "tab_download": {"ar": "تنزيل الوسائط", "en": "Downloader"},
    "tab_active": {"ar": "التنزيلات النشطة", "en": "Active downloads"},
    "tab_queue": {"ar": "قائمة الانتظار", "en": "Queue"},
    "tab_library": {"ar": "المكتبة", "en": "Media library"},
    "tab_history": {"ar": "سجل التنزيلات", "en": "Download history"},
    "tab_tools": {"ar": "أدوات الوسائط", "en": "Media tools"},
    "tab_settings": {"ar": "الإعدادات", "en": "Settings"},
    "nav_menu": {"ar": "القائمة", "en": "Menu"},
    "sidebar_status": {"ar": "حالة النظام", "en": "System status"},
    "status_ffmpeg_ready": {"ar": "FFmpeg جاهز", "en": "FFmpeg ready"},
    "status_deno_ready": {"ar": "Deno جاهز", "en": "Deno ready"},
    "status_deno_missing": {"ar": "Deno غير مثبّت", "en": "Deno missing"},
    "home_title": {"ar": "لوحة التحكم", "en": "Dashboard"},
    "home_subtitle": {
        "ar": "نظرة سريعة على تحميلاتك وأنشطتك الأخيرة.",
        "en": "A quick look at your downloads and recent activity.",
    },
    "home_stats_total": {"ar": "إجمالي التحميلات", "en": "Total downloads"},
    "home_stats_active": {"ar": "جارٍ التحميل", "en": "Active"},
    "home_stats_completed": {"ar": "الملفات المكتملة", "en": "Completed files"},
    "home_stats_size": {"ar": "الحجم الكلي", "en": "Total size"},
    "home_quick_actions": {"ar": "إجراءات سريعة", "en": "Quick actions"},
    "home_storage": {"ar": "مساحة التخزين", "en": "Storage"},
    "home_storage_path": {"ar": "مجلد التحميلات", "en": "Download folder"},
    "home_open_folder": {"ar": "فتح المجلد", "en": "Open folder"},
    "home_recent": {"ar": "آخر التحميلات", "en": "Recent downloads"},
    "home_recent_empty": {"ar": "لا توجد تحميلات بعد.", "en": "No downloads yet."},
    "queue_title": {"ar": "قائمة الانتظار", "en": "Download queue"},
    "queue_subtitle": {
        "ar": "تحكّم بترتيب الأولوية وجميع التحميلات من مكان واحد.",
        "en": "Control priority and all your downloads from one place.",
    },
    "queue_empty": {"ar": "الطابور فارغ حالياً.", "en": "The queue is empty."},
    "queue_pause_all": {"ar": "إيقاف الكل", "en": "Pause all"},
    "queue_resume_all": {"ar": "استئناف الكل", "en": "Resume all"},
    "queue_cancel_all": {"ar": "إلغاء الكل", "en": "Cancel all"},
    "queue_priority": {"ar": "الأولوية", "en": "Priority"},
    "completed_title": {"ar": "الملفات المكتملة", "en": "Completed files"},
    "completed_subtitle": {
        "ar": "ملفاتك الجاهزة مع فتح سريع للمجلد.",
        "en": "Your finished files with quick folder access.",
    },
    "completed_empty": {"ar": "لا توجد ملفات مكتملة بعد.", "en": "No completed files yet."},
    "active_title": {"ar": "التنزيلات النشطة", "en": "Active downloads"},
    "active_subtitle": {
        "ar": "تابع تقدم التحميلات الجارية وأدِرها لحظة بلحظة.",
        "en": "Follow and control downloads currently in progress.",
    },
    "library_title": {"ar": "مكتبة الوسائط", "en": "Media library"},
    "library_subtitle": {
        "ar": "كل ملفاتك المكتملة في مكان واحد لفتحها ومشاركتها.",
        "en": "All your finished files in one place to open and share.",
    },
    "tools_title": {"ar": "أدوات الوسائط", "en": "Media tools"},
    "tools_subtitle": {
        "ar": "حوّل الملفات واضغطها وقصّها باستخدام FFmpeg.",
        "en": "Convert, compress and trim media using FFmpeg.",
    },
    "tool_choose": {"ar": "اختيار ملف", "en": "Choose file"},
    "tool_run": {"ar": "ابدأ", "en": "Run"},
    "tool_ready": {"ar": "جاهز", "en": "Ready"},
    "tool_running": {"ar": "جارٍ المعالجة…", "en": "Processing…"},
    "tool_done": {"ar": "تم الحفظ: {path}", "en": "Saved: {path}"},
    "tool_failed": {"ar": "فشل: {error}", "en": "Failed: {error}"},
    "tool_no_file": {"ar": "اختر ملفاً أولاً", "en": "Choose a file first"},
    "tool_no_ffmpeg": {"ar": "FFmpeg غير متاح", "en": "FFmpeg is not available"},
    "tool_bad_time": {"ar": "أدخل وقتاً صالحاً بالثواني", "en": "Enter valid times in seconds"},
    "tool_start": {"ar": "من (ثانية)", "en": "Start (s)"},
    "tool_duration": {"ar": "المدة (ثانية)", "en": "Duration (s)"},
    "tool_extract_title": {"ar": "استخراج صوت MP3", "en": "Extract MP3 audio"},
    "tool_extract_desc": {
        "ar": "استخرج الصوت من أي فيديو بجودة عالية.",
        "en": "Extract high-quality audio from any video.",
    },
    "tool_compress_title": {"ar": "ضغط الفيديو", "en": "Compress video"},
    "tool_compress_desc": {
        "ar": "قلّل حجم الفيديو مع الحفاظ على جودة مقبولة.",
        "en": "Reduce video size while keeping acceptable quality.",
    },
    "tool_trim_title": {"ar": "قص مقطع", "en": "Trim clip"},
    "tool_trim_desc": {
        "ar": "اقطع مقطعاً قصيراً من بداية ومدة محددتين.",
        "en": "Cut a short clip from a chosen start and duration.",
    },
    "tool_convert_title": {"ar": "تحويل الصيغة", "en": "Convert format"},
    "tool_convert_desc": {
        "ar": "حوّل الفيديو أو الصوت إلى MP4 أو MKV أو WebM أو MP3 أو M4A.",
        "en": "Convert video or audio to MP4, MKV, WebM, MP3 or M4A.",
    },
    "tool_gif_title": {"ar": "إنشاء GIF", "en": "Create GIF"},
    "tool_gif_desc": {
        "ar": "أنشئ GIF متحركاً من مقطع قصير بإعدادات الإطارات والعرض.",
        "en": "Create an animated GIF from a short clip with FPS and width control.",
    },
    "tool_merge_title": {"ar": "دمج صوت بفيديو", "en": "Merge audio with video"},
    "tool_merge_desc": {
        "ar": "اربط ملف صوت بملف فيديو في ملف واحد متزامن.",
        "en": "Attach an audio file to a video in one synchronised file.",
    },
    "tool_subtitle_title": {"ar": "حرق الترجمة", "en": "Burn subtitles"},
    "tool_subtitle_desc": {
        "ar": "ادمج ملف ترجمة SRT أو ASS داخل الفيديو بشكل دائم.",
        "en": "Permanently embed an SRT or ASS subtitle file into the video.",
    },
    "tool_cover_title": {"ar": "استخراج غلاف", "en": "Extract cover"},
    "tool_cover_desc": {
        "ar": "احفظ أول إطار من الفيديو كصورة غلاف JPG.",
        "en": "Save the first video frame as a JPG cover image.",
    },
    "tool_choose_audio": {"ar": "ملف الصوت", "en": "Audio file"},
    "tool_choose_subtitle": {"ar": "ملف الترجمة", "en": "Subtitle file"},
    "tool_format": {"ar": "الصيغة", "en": "Format"},
    "tool_fps": {"ar": "الإطارات/ث", "en": "FPS"},
    "tool_width": {"ar": "العرض", "en": "Width"},
    "tool_bad_value": {"ar": "أدخل قيمة صالحة", "en": "Enter a valid value"},
    "tool_no_second": {"ar": "اختر الملف الثاني أولاً", "en": "Choose the second file first"},
    "download_title": {"ar": "تنزيل الوسائط", "en": "Download media"},
    "download_subtitle": {
        "ar": "ألصق الرابط، اختر الجودة، ثم ابدأ التنزيل — كل شيء في مكان واحد.",
        "en": "Paste a link, pick a quality, then start downloading — all in one place.",
    },
    "history_subtitle": {
        "ar": "كل الملفات التي نزّلتها مع فتح سريع للمجلد.",
        "en": "Every file you downloaded, with quick access to its folder.",
    },
    "settings_subtitle": {
        "ar": "خصّص اللغة والمظهر وجودة التنزيل.",
        "en": "Customize language, appearance and download quality.",
    },
    "theme_dark": {"ar": "داكن", "en": "Dark"},
    "theme_light": {"ar": "فاتح", "en": "Light"},
    "theme_toggle_tip": {"ar": "تبديل الوضع الليلي / النهاري", "en": "Toggle dark / light mode"},
    "lang_toggle_tip": {"ar": "تبديل اللغة", "en": "Switch language"},
    "close": {"ar": "إغلاق", "en": "Close"},
    "cancel": {"ar": "إلغاء", "en": "Cancel"},
    "confirm": {"ar": "تأكيد", "en": "Confirm"},

    # URL / fetch
    "url_section": {"ar": "رابط الوسائط", "en": "Media URL"},
    "url_placeholder": {
        "ar": "الصق رابط الفيديو أو قائمة التشغيل هنا…",
        "en": "Paste a video or playlist URL here…",
    },
    "paste": {"ar": "لصق", "en": "Paste"},
    "paste_tip": {"ar": "لصق من الحافظة", "en": "Paste from clipboard"},
    "fetch": {"ar": "فحص الرابط", "en": "Fetch info"},
    "fetching": {"ar": "جارٍ الفحص…", "en": "Fetching…"},

    # Media info
    "info_section": {"ar": "معلومات الوسائط", "en": "Media info"},
    "info_empty_title": {"ar": "لم يتم فحص أي رابط بعد", "en": "No media loaded yet"},
    "info_empty_hint": {
        "ar": "أدخل رابطاً ثم اضغط «فحص الرابط» لعرض العنوان والصورة والجودة.",
        "en": "Enter a URL, then press Fetch to preview the title, thumbnail and quality.",
    },
    "info_channel": {"ar": "القناة", "en": "Channel"},
    "info_duration": {"ar": "المدة", "en": "Duration"},
    "info_platform": {"ar": "المنصة", "en": "Platform"},
    "info_playlist": {"ar": "قائمة تشغيل", "en": "Playlist"},
    "info_entries": {"ar": "{count} عنصر", "en": "{count} items"},
    "choose_items": {"ar": "اختيار فيديوهات", "en": "Choose videos"},

    # Options
    "options_section": {"ar": "خيارات التنزيل", "en": "Download options"},
    "mode": {"ar": "النوع", "en": "Type"},
    "mode_video": {"ar": "فيديو", "en": "Video"},
    "mode_audio": {"ar": "صوت", "en": "Audio"},
    "quality": {"ar": "الجودة", "en": "Quality"},
    "quality_best": {"ar": "أفضل جودة متاحة", "en": "Best available"},
    "audio_m4a_best": {"ar": "صوت أصلي بدون تحويل", "en": "Original audio (no conversion)"},
    "audio_quality": {"ar": "جودة الصوت", "en": "Audio quality"},
    "dest_section": {"ar": "مجلد الحفظ", "en": "Save folder"},
    "browse": {"ar": "تغيير المجلد", "en": "Change folder"},
    "choose_folder_title": {"ar": "اختر مجلد الحفظ", "en": "Choose download folder"},
    "download": {"ar": "تنزيل", "en": "Download"},
    "download_audio_mp3": {"ar": "تنزيل الصوت", "en": "Download audio"},

    # Queue / tasks
    "queue_section": {"ar": "التنزيلات", "en": "Downloads"},
    "queue_empty": {
        "ar": "لا توجد تنزيلات حالياً. أضف رابطاً للبدء.",
        "en": "No downloads yet. Add a URL to start.",
    },
    "clear_finished": {"ar": "إزالة المنتهية", "en": "Clear finished"},

    # Batch link inbox
    "link_inbox_btn": {"ar": "صندوق الروابط", "en": "Link Inbox"},
    "link_inbox_tip": {
        "ar": "الصق عدة روابط دفعة واحدة لإضافتها للطابور",
        "en": "Paste several links at once to add them to the queue",
    },
    "link_inbox_title": {"ar": "صندوق الروابط", "en": "Link Inbox"},
    "link_inbox_hint": {
        "ar": "الصق رابطاً في كل سطر (أو أكثر من رابط في السطر). يتم تجاهل الروابط المكررة.",
        "en": "Paste one link per line (or several per line). Duplicates are ignored.",
    },
    "link_inbox_paste": {"ar": "لصق من الحافظة", "en": "Paste from clipboard"},
    "link_inbox_add": {"ar": "إضافة للطابور", "en": "Add to queue"},
    "link_inbox_clear": {"ar": "مسح الكل", "en": "Clear all"},
    "link_inbox_count": {"ar": "{count} رابط جاهز", "en": "{count} link(s) ready"},
    "link_inbox_empty": {"ar": "الصق روابط للبدء", "en": "Paste links to begin"},
    "link_inbox_added": {"ar": "تمت إضافة {count} رابط للطابور", "en": "Added {count} link(s) to the queue"},
    "link_inbox_skipped": {"ar": "تم تخطي {count} رابط مكرر", "en": "Skipped {count} duplicate link(s)"},
    "link_inbox_no_valid": {"ar": "لم يتم العثور على روابط صالحة", "en": "No valid links found"},

    # Failed Downloads Center
    "failed_center_btn": {"ar": "مركز الفاشلة", "en": "Failed Center"},
    "failed_center_title": {
        "ar": "مركز التحميلات الفاشلة",
        "en": "Failed Downloads Center",
    },
    "failed_center_subtitle": {
        "ar": "راجع التحميلات التي فشلت وأعد محاولتها بضغطة واحدة.",
        "en": "Review failed downloads and retry them with one click.",
    },
    "failed_center_empty": {
        "ar": "لا توجد تحميلات فاشلة. كل شيء يسير بشكل جيد!",
        "en": "No failed downloads. Everything is looking good!",
    },
    "failed_center_retry": {"ar": "إعادة المحاولة", "en": "Retry"},
    "failed_center_retry_all": {"ar": "إعادة محاولة الكل", "en": "Retry all"},
    "failed_center_clear": {"ar": "مسح الكل", "en": "Clear all"},
    "failed_center_remove": {"ar": "إزالة", "en": "Remove"},
    "failed_center_attempts": {"ar": "المحاولة {count}", "en": "Attempt {count}"},
    "failed_center_reason": {"ar": "السبب: {reason}", "en": "Reason: {reason}"},
    "failed_center_retrying": {"ar": "تمت إعادة الجدولة", "en": "Re-scheduled"},
    "toast_auto_retry": {
        "ar": "إعادة جدولة تلقائية — المحاولة {count}",
        "en": "Auto-retry scheduled — attempt {count}",
    },
    "toast_failure_removed": {"ar": "تمت الإزالة", "en": "Removed"},
    "toast_failed_cleared": {"ar": "تم مسح مركز الفاشلة", "en": "Failed center cleared"},
    "toast_failures_retried": {
        "ar": "تمت إعادة جدولة {count} تحميل",
        "en": "Re-scheduled {count} download(s)",
    },
    "settings_auto_retry_failed": {
        "ar": "إعادة المحاولة التلقائية",
        "en": "Automatic retry",
    },
    "settings_auto_retry_failed_hint": {
        "ar": "إعادة جدولة أخطاء الشبكة تلقائياً حتى 3 محاولات",
        "en": "Automatically reschedule network errors up to 3 attempts",
    },
    "state_pending": {"ar": "في الانتظار", "en": "Queued"},
    "state_downloading": {"ar": "جارٍ التنزيل", "en": "Downloading"},
    "state_paused": {"ar": "متوقف مؤقتاً", "en": "Paused"},
    "state_processing": {"ar": "جارٍ المعالجة", "en": "Processing"},
    "state_completed": {"ar": "مكتمل", "en": "Completed"},
    "state_error": {"ar": "خطأ", "en": "Error"},
    "state_cancelled": {"ar": "ملغى", "en": "Cancelled"},
    "btn_pause": {"ar": "إيقاف مؤقت", "en": "Pause"},
    "btn_resume": {"ar": "استئناف", "en": "Resume"},
    "btn_cancel": {"ar": "إلغاء", "en": "Cancel"},
    "btn_open": {"ar": "فتح المجلد", "en": "Open folder"},
    "btn_retry": {"ar": "إعادة المحاولة", "en": "Retry"},
    "btn_remove": {"ar": "إزالة", "en": "Remove"},
    "stats_line": {
        "ar": "{percent}% • {speed} • متبقي {eta}",
        "en": "{percent}% • {speed} • ETA {eta}",
    },
    "stats_done": {"ar": "{percent}% • {size}", "en": "{percent}% • {size}"},
    "stats_paused": {"ar": "{percent}% • متوقف مؤقتاً", "en": "{percent}% • paused"},
    "stats_processing": {"ar": "جارٍ الدمج والتحويل…", "en": "Merging / converting…"},

    # History
    "history_section": {"ar": "سجل التنزيلات", "en": "Download history"},
    "history_empty": {"ar": "لم يتم تنزيل أي ملف بعد.", "en": "No downloaded files yet."},
    "history_clear": {"ar": "مسح السجل", "en": "Clear history"},
    "history_clear_confirm": {
        "ar": "هل تريد مسح كل سجل التنزيلات؟ (لن تُحذف الملفات من القرص)",
        "en": "Clear all download history? (Files will not be deleted from disk)",
    },
    "history_open_failed": {"ar": "تعذّر فتح المجلد.", "en": "Could not open the folder."},
    "history_item_meta": {
        "ar": "{platform} • {date} • {size}",
        "en": "{platform} • {date} • {size}",
    },
    "history_missing_file": {"ar": "الملف غير موجود", "en": "File missing"},
    "history_stats_title": {"ar": "نظرة عامة", "en": "Overview"},
    "history_stats_count": {"ar": "عدد الملفات", "en": "Files"},
    "history_stats_size": {"ar": "الحجم الإجمالي", "en": "Total size"},
    "history_stats_last": {"ar": "آخر تنزيل", "en": "Last download"},
    "stat_empty": {"ar": "—", "en": "—"},

    # Settings
    "settings_section": {"ar": "إعدادات التطبيق", "en": "Application settings"},
    "settings_download_dir": {"ar": "مجلد الحفظ الافتراضي", "en": "Default download folder"},
    "settings_concurrency": {"ar": "عدد التنزيلات المتزامنة", "en": "Concurrent downloads"},
    "settings_concurrency_hint": {
        "ar": "يُطبَّق عند إعادة تشغيل البرنامج.",
        "en": "Applied after restarting the app.",
    },
    "settings_theme": {"ar": "المظهر", "en": "Appearance"},
    "settings_palette": {"ar": "لوحة الألوان", "en": "Colour palette"},
    "settings_palette_hint": {
        "ar": "اختر لوحة ألوان من Color Hunt لتغيير هوية الواجهة بالكامل مع الحفاظ على الثيم الفاتح أو الداكن.",
        "en": "Pick a Color Hunt palette to restyle the whole interface while keeping the light or dark theme.",
    },
    "palette_blue": {"ar": "الأزرق الكلاسيكي", "en": "Classic blue"},
    "palette_sand": {"ar": "الرملي الزيتوني", "en": "Olive sand"},
    "palette_olive": {"ar": "الزيتوني الداكن", "en": "Deep olive"},
    "palette_ocean": {"ar": "المحيط الفيروزي", "en": "Teal ocean"},
    "palette_forest": {"ar": "الغابات", "en": "Forest"},
    "palette_sky": {"ar": "السماء الزرقاء", "en": "Blue sky"},
    "palette_lime": {"ar": "الليموني", "en": "Lime garden"},
    "palette_linen": {"ar": "الكتاني", "en": "Linen"},
    "settings_language": {"ar": "اللغة", "en": "Language"},
    "settings_audio_bitrate": {"ar": "جودة MP3 الافتراضية", "en": "Default MP3 quality"},
    "settings_embed_meta": {"ar": "دمج بيانات الوسائط (Metadata)", "en": "Embed metadata"},
    "settings_embed_thumb": {"ar": "دمج الصورة المصغرة", "en": "Embed thumbnail"},
    "settings_ffmpeg": {"ar": "حالة FFmpeg", "en": "FFmpeg status"},
    "settings_js_runtime": {"ar": "محرك JavaScript (ليوتيوب)", "en": "JavaScript runtime (YouTube)"},
    "settings_js_ok": {
        "ar": "متوفر — استخراج يوتيوب يعمل بكفاءة",
        "en": "Available — YouTube extraction works fully",
    },
    "settings_js_missing": {
        "ar": "غير موجود — بعض جودات يوتيوب قد لا تظهر",
        "en": "Missing — some YouTube qualities may be unavailable",
    },
    "settings_js_hint": {
        "ar": "ثبّت Deno بالأمر: winget install DenoLand.Deno",
        "en": "Install Deno with: winget install DenoLand.Deno",
    },
    "settings_ffmpeg_ok": {
        "ar": "متوفر — التحويل بين الصيغ مفعّل",
        "en": "Available — format conversion enabled",
    },
    "settings_ffmpeg_missing": {
        "ar": "غير مثبّت — تنزيل MP3 والدمج قد لا يعمل",
        "en": "Not installed — MP3 conversion and merging may fail",
    },
    "settings_ffmpeg_hint": {
        "ar": "ثبّت FFmpeg بالأمر: winget install Gyan.FFmpeg — أو ضع ffmpeg.exe داخل مجلد bin في المشروع.",
        "en": "Install with: winget install Gyan.FFmpeg — or place ffmpeg.exe inside the project's bin folder.",
    },
    "settings_config_folder": {"ar": "فتح مجلد الإعدادات", "en": "Open config folder"},
    "settings_about": {"ar": "حول البرنامج", "en": "About"},
    "settings_about_text": {
        "ar": "برنامج مفتوح المصدر لتنزيل الوسائط مبني بلغة Python باستخدام yt-dlp و CustomTkinter.\n"
        "استخدمه لتنزيل المحتوى الذي تملك حقوقه فقط، واحترم شروط استخدام كل منصة.",
        "en": "An open-source Python media downloader built with yt-dlp and CustomTkinter.\n"
        "Use it only for content you have the rights to download, and respect each platform's terms.",
    },
    "settings_saved": {"ar": "تم حفظ الإعدادات", "en": "Settings saved"},
    "settings_shortcuts": {
        "ar": "اختصارات: Ctrl+1/2/3 للتنقل بين الصفحات، وF5 لفحص الرابط.",
        "en": "Shortcuts: Ctrl+1/2/3 to switch pages, F5 to fetch a link.",
    },

    # Playlist dialog
    "playlist_dialog_title": {"ar": "اختيار فيديوهات القائمة", "en": "Select playlist videos"},
    "playlist_dialog_subtitle": {
        "ar": "تم العثور على {count} فيديو. اختر ما تريد تنزيله.",
        "en": "{count} videos found. Choose what to download.",
    },
    "playlist_limited": {
        "ar": "يتم عرض أول {count} عنصر فقط.",
        "en": "Showing the first {count} items only.",
    },
    "select_all": {"ar": "تحديد الكل", "en": "Select all"},
    "select_none": {"ar": "إلغاء التحديد", "en": "Select none"},
    "start_download": {"ar": "بدء التنزيل", "en": "Start download"},
    "selected_count": {"ar": "المحدد: {count}", "en": "Selected: {count}"},

    # Status messages
    "status_ready": {"ar": "جاهز", "en": "Ready"},
    "status_fetching": {"ar": "جارٍ جلب معلومات الوسائط…", "en": "Fetching media info…"},
    "status_fetched": {"ar": "تم جلب المعلومات بنجاح.", "en": "Media info loaded."},
    "status_error": {"ar": "فشل جلب المعلومات", "en": "Fetch failed"},
    "status_added": {
        "ar": "تمت إضافة {count} تنزيل إلى القائمة.",
        "en": "Added {count} download(s) to the queue.",
    },
    "status_completed": {"ar": "اكتمل التنزيل: {title}", "en": "Download complete: {title}"},
    "status_cancelled": {"ar": "تم إلغاء التنزيل.", "en": "Download cancelled."},
    "status_paused": {"ar": "تم الإيقاف المؤقت.", "en": "Paused."},
    "status_resumed": {"ar": "تم الاستئناف.", "en": "Resumed."},
    "status_cleared": {"ar": "تم مسح السجل.", "en": "History cleared."},
    "status_paste_empty": {"ar": "الحافظة فارغة.", "en": "The clipboard is empty."},
    "status_playlist_loaded": {"ar": "تم العثور على قائمة تشغيل.", "en": "Playlist found."},
    "status_settings_saved": {"ar": "تم حفظ الإعدادات.", "en": "Settings saved."},
    "status_cleared_finished": {
        "ar": "تم إزالة التنزيلات المنتهية.",
        "en": "Finished downloads removed.",
    },
    "toast_added": {
        "ar": "أُضيف إلى قائمة التنزيل",
        "en": "Added to the download queue",
    },
    "toast_completed": {
        "ar": "اكتمل التنزيل: {title}",
        "en": "Download complete: {title}",
    },
    "toast_failed": {
        "ar": "فشل التنزيل — {reason}",
        "en": "Download failed — {reason}",
    },
    "toast_cancelled": {
        "ar": "تم إلغاء التنزيل",
        "en": "Download cancelled",
    },

    # Errors
    "error_title": {"ar": "تعذّر إكمال العملية", "en": "Operation failed"},
    "err_empty_url": {"ar": "الرجاء إدخال رابط أولاً.", "en": "Please enter a URL first."},
    "err_invalid_url": {
        "ar": "الرابط غير صالح. تأكد من نسخ رابط كامل يبدأ بـ http أو https.",
        "en": "Invalid URL. Make sure you copied a full link starting with http or https.",
    },
    "err_private": {
        "ar": "هذا الفيديو خاص ولا يمكن تنزيله.",
        "en": "This video is private and cannot be downloaded.",
    },
    "err_unavailable": {
        "ar": "الفيديو غير متوفر أو تم حذفه.",
        "en": "The video is unavailable or has been removed.",
    },
    "err_login": {
        "ar": "يتطلب هذا المحتوى تسجيل الدخول أو التحقق من العمر.",
        "en": "This content requires sign-in or age verification.",
    },
    "err_geo": {
        "ar": "هذا المحتوى محجوب جغرافياً في منطقتك.",
        "en": "This content is geo-blocked in your region.",
    },
    "err_rate_limit": {
        "ar": "طلبات كثيرة جداً. انتظر قليلاً ثم أعد المحاولة.",
        "en": "Too many requests. Wait a moment and retry.",
    },
    "err_network": {
        "ar": "تعذّر الاتصال بالإنترنت أو انقطع الاتصال. تحقق من الشبكة وأعد المحاولة.",
        "en": "Network error or connection lost. Check your connection and retry.",
    },
    "err_ffmpeg": {
        "ar": "FFmpeg غير مثبّت أو غير موجود. ثبّته لتفعيل تحويل MP3 ودمج الفيديو.",
        "en": "FFmpeg is missing. Install it to enable MP3 conversion and video merging.",
    },
    "err_disk": {"ar": "لا توجد مساحة كافية على القرص.", "en": "Not enough disk space."},
    "err_copyright": {
        "ar": "تم حجب المحتوى بسبب حقوق النشر.",
        "en": "The content is blocked due to copyright.",
    },
    "err_format": {
        "ar": "الصيغة المطلوبة غير متاحة لهذا الفيديو. جرّب جودة أخرى.",
        "en": "The requested format is unavailable. Try another quality.",
    },
    "err_playlist_empty": {
        "ar": "قائمة التشغيل فارغة أو لا تحتوي عناصر قابلة للتنزيل.",
        "en": "The playlist is empty or has no downloadable items.",
    },
    "err_no_formats": {
        "ar": "لم يتم العثور على صيغ قابلة للتنزيل لهذا الرابط.",
        "en": "No downloadable formats were found.",
    },
    "err_choose_items": {
        "ar": "لم تحدد أي فيديو من القائمة.",
        "en": "You did not select any videos.",
    },
    "err_generic": {"ar": "حدث خطأ غير متوقع.", "en": "An unexpected error occurred."},

    # Confirmation
    "confirm_exit_title": {"ar": "الخروج من البرنامج", "en": "Exit application"},
    "confirm_exit": {
        "ar": "هناك تنزيلات جارية. هل تريد إلغاءها والخروج؟",
        "en": "Downloads are still running. Cancel them and exit?",
    },
    "ffmpeg_missing_short": {"ar": "FFmpeg غير مثبّت", "en": "FFmpeg missing"},

    # Advanced settings / network
    "settings_advanced": {"ar": "إعدادات متقدمة", "en": "Advanced settings"},
    "settings_network": {"ar": "الشبكة والوكيل", "en": "Network & proxy"},
    "settings_proxy": {"ar": "الوكيل (Proxy)", "en": "Proxy"},
    "settings_proxy_hint": {
        "ar": "اتركه فارغاً لعدم استخدام وكيل. مثال: http://127.0.0.1:8080",
        "en": "Leave empty to disable. Example: http://127.0.0.1:8080",
    },
    "settings_speed_limit": {"ar": "حد سرعة التنزيل", "en": "Download speed limit"},
    "speed_unlimited": {"ar": "غير محدود", "en": "Unlimited"},
    "speed_limit_option": {"ar": "{value} كيلوبايت/ث", "en": "{value} KB/s"},
    "settings_container": {"ar": "صيغة الفيديو", "en": "Video container"},
    "settings_container_hint": {
        "ar": "MP4 الأوسع توافقاً، MKV يدعم الترجمة والمسارات، WEBM أصغر حجماً.",
        "en": "MP4 is the most compatible, MKV supports subtitles/tracks, WEBM is smaller.",
    },
    "settings_subtitles": {"ar": "تضمين الترجمة", "en": "Embed subtitles"},
    "settings_subtitle_langs": {"ar": "لغات الترجمة", "en": "Subtitle languages"},
    "settings_subtitle_langs_hint": {
        "ar": "أكواد مفصولة بفواصل، مثال: ar,en",
        "en": "Comma-separated codes, e.g. ar,en",
    },
    "settings_auto_clipboard": {
        "ar": "كشف الروابط من الحافظة",
        "en": "Detect links from clipboard",
    },
    "settings_auto_clipboard_hint": {
        "ar": "يملأ حقل الرابط تلقائياً عند نسخ رابط جديد.",
        "en": "Fills the URL field automatically when a new link is copied.",
    },
    "settings_schedule": {"ar": "جدولة التنزيل", "en": "Schedule download"},
    "schedule_now": {"ar": "الآن", "en": "Now"},
    "schedule_15": {"ar": "بعد 15 دقيقة", "en": "In 15 minutes"},
    "schedule_30": {"ar": "بعد 30 دقيقة", "en": "In 30 minutes"},
    "schedule_60": {"ar": "بعد ساعة", "en": "In 1 hour"},
    "schedule_120": {"ar": "بعد ساعتين", "en": "In 2 hours"},
    "state_scheduled": {"ar": "مجدول", "en": "Scheduled"},
    "stats_scheduled": {"ar": "يبدأ الساعة {time}", "en": "Starts at {time}"},
    "status_clipboard_detected": {
        "ar": "تم اكتشاف رابط في الحافظة.",
        "en": "Link detected in the clipboard.",
    },
    "status_added_skipped": {
        "ar": "تمت إضافة {count} وتخطي {skipped} مكرر.",
        "en": "Added {count}, skipped {skipped} duplicate(s).",
    },
    "err_duplicate": {
        "ar": "هذا الرابط موجود بالفعل في قائمة التنزيل.",
        "en": "This link is already in the download queue.",
    },
    "history_duplicate_title": {"ar": "تنزيل مكرر", "en": "Duplicate download"},
    "history_duplicate_confirm": {
        "ar": "هذا الملف موجود في السجل. هل تريد تنزيله مرة أخرى؟",
        "en": "This file is in history. Download it again?",
    },
    "status_duplicate_skipped": {
        "ar": "تم تخطي رابط مكرر.",
        "en": "Duplicate link skipped.",
    },
    "btn_preview": {"ar": "معاينة", "en": "Preview"},
    "btn_qr": {"ar": "QR", "en": "QR"},
    "qr_title": {"ar": "رمز QR للرابط", "en": "Link QR code"},
    "qr_unavailable": {
        "ar": "مكتبة QR غير متوفرة. ثبّت qrcode[pil] لتفعيل رمز QR.",
        "en": "QR library is unavailable. Install qrcode[pil] to enable QR codes.",
    },
    "err_qr_empty": {
        "ar": "أدخل رابطاً أولاً لإنشاء رمز QR.",
        "en": "Enter a link first to generate a QR code.",
    },
    "history_search_placeholder": {"ar": "بحث في السجل…", "en": "Search history…"},
    "history_filter_all": {"ar": "الكل", "en": "All"},
    "history_filter_video": {"ar": "فيديو", "en": "Video"},
    "history_filter_audio": {"ar": "صوت", "en": "Audio"},
    "history_filter_image": {"ar": "صور", "en": "Images"},
    "history_filter_other": {"ar": "أخرى", "en": "Other"},
    "history_filter_favorite": {"ar": "المفضلة", "en": "Favorites"},

    # Library favorites, tags and sorting
    "library_sort": {"ar": "فرز", "en": "Sort"},
    "library_sort_tip": {"ar": "ترتيب عناصر المكتبة", "en": "Sort the library entries"},
    "library_sort_title": {"ar": "ترتيب المكتبة", "en": "Sort library"},
    "sort_date_desc": {"ar": "الأحدث أولاً", "en": "Newest first"},
    "sort_date_asc": {"ar": "الأقدم أولاً", "en": "Oldest first"},
    "sort_size_desc": {"ar": "الأكبر حجماً", "en": "Largest first"},
    "sort_size_asc": {"ar": "الأصغر حجماً", "en": "Smallest first"},
    "sort_name_asc": {"ar": "الاسم (أ–ي)", "en": "Name (A–Z)"},
    "sort_name_desc": {"ar": "الاسم (ي–أ)", "en": "Name (Z–A)"},
    "sort_type": {"ar": "حسب النوع", "en": "By type"},
    "ctx_add_favorite": {"ar": "إضافة للمفضلة", "en": "Add to favorites"},
    "ctx_remove_favorite": {"ar": "إزالة من المفضلة", "en": "Remove from favorites"},
    "ctx_edit_tags": {"ar": "تعديل الوسوم", "en": "Edit tags"},
    "tags_dialog_title": {"ar": "وسوم الملف", "en": "File tags"},
    "tags_dialog_hint": {
        "ar": "افصل بين الوسوم بفاصلة (مثال: عمل، مهم، 2026)",
        "en": "Separate tags with a comma (e.g. work, important, 2026)",
    },
    "tags_dialog_save": {"ar": "حفظ الوسوم", "en": "Save tags"},
    "tags_current": {"ar": "الوسوم: {tags}", "en": "Tags: {tags}"},
    "toast_fav_added": {"ar": "أُضيف للمفضلة", "en": "Added to favorites"},
    "toast_fav_removed": {"ar": "أُزيل من المفضلة", "en": "Removed from favorites"},
    "toast_tags_saved": {"ar": "تم حفظ الوسوم", "en": "Tags saved"},

    # SHA-256 integrity verification
    "ctx_verify_hash": {"ar": "التحقق من الملف (SHA-256)", "en": "Verify file (SHA-256)"},
    "ctx_set_expected_hash": {
        "ar": "تعيين التجزئة المتوقعة",
        "en": "Set expected hash",
    },
    "hash_dialog_title": {"ar": "التجزئة المتوقعة SHA-256", "en": "Expected SHA-256 hash"},
    "hash_dialog_hint": {
        "ar": "الصق بصمة SHA-256 المكوّنة من 64 خانة سداسية عشرية (مع بادئة sha256: اختيارية).",
        "en": "Paste the 64-character hexadecimal SHA-256 digest (optional sha256: prefix).",
    },
    "hash_dialog_save": {"ar": "حفظ والتحقق", "en": "Save & verify"},
    "hash_invalid": {
        "ar": "أدخل بصمة SHA-256 صالحة من 64 خانة",
        "en": "Enter a valid 64-character SHA-256 digest",
    },
    "hash_expected_saved": {
        "ar": "تم حفظ التجزئة المتوقعة وجارٍ التحقق",
        "en": "Expected hash saved — verifying now",
    },
    "hash_toast_verified": {"ar": "تم حساب SHA-256 بنجاح", "en": "SHA-256 computed successfully"},
    "hash_toast_match": {"ar": "التجزئة مطابقة ✓", "en": "Hash matches ✓"},
    "hash_toast_mismatch": {"ar": "تحذير: التجزئة غير مطابقة!", "en": "Warning: hash mismatch!"},
    "hash_toast_missing": {"ar": "الملف غير موجود، تعذّر التحقق", "en": "File missing — cannot verify"},
    "hash_toast_error": {"ar": "تعذّر حساب التجزئة", "en": "Could not compute the hash"},
    "hash_verified": {"ar": "✓ SHA-256", "en": "✓ SHA-256"},
    "hash_match": {"ar": "✓ SHA-256 مطابق", "en": "✓ SHA-256 match"},
    "hash_mismatch": {"ar": "⚠ SHA-256 غير مطابق", "en": "⚠ SHA-256 mismatch"},
    "hash_pending": {"ar": "⏳ SHA-256…", "en": "⏳ SHA-256…"},
    "hash_unchecked": {"ar": "SHA-256 غير محسوب", "en": "SHA-256 not computed"},
    "hash_missing": {"ar": "⚠ SHA-256 الملف مفقود", "en": "⚠ SHA-256 file missing"},
    "hash_error": {"ar": "⚠ SHA-256 خطأ", "en": "⚠ SHA-256 error"},
    "settings_verify_hashes": {
        "ar": "التحقق التلقائي من سلامة الملفات (SHA-256)",
        "en": "Automatic file integrity check (SHA-256)",
    },
    "settings_verify_hashes_hint": {
        "ar": "يحسب بصمة SHA-256 لكل ملف بعد اكتمال تنزيله ويحفظها في السجل.",
        "en": "Computes a SHA-256 digest for every finished download and stores it in history.",
    },

    # Smart download rules
    "settings_tab_rules": {"ar": "القواعد", "en": "Rules"},
    "rules_title": {"ar": "قواعد التحميل الذكية", "en": "Smart download rules"},
    "rules_hint": {
        "ar": "تُطبَّق القواعد تلقائياً على كل تنزيل جديد. عطّل أي قاعدة للاحتفاظ بالسلوك الافتراضي.",
        "en": "Rules apply automatically to every new download. Disable any rule to keep default behaviour.",
    },
    "rule_kind_video": {"ar": "الفيديو → مجلد الفيديو", "en": "Video → video folder"},
    "rule_kind_video_hint": {
        "ar": "يحفظ ملفات الفيديو داخل مجلد فرعي منفصل.",
        "en": "Saves video files in a separate subfolder.",
    },
    "rule_kind_audio": {"ar": "الصوت → مجلد الصوت", "en": "Audio → audio folder"},
    "rule_kind_audio_hint": {
        "ar": "يحفظ ملفات الصوت داخل مجلد فرعي منفصل.",
        "en": "Saves audio files in a separate subfolder.",
    },
    "rule_large_files": {"ar": "الملفات الكبيرة → مجلد خاص", "en": "Large files → dedicated folder"},
    "rule_large_files_hint": {
        "ar": "ينقل الملفات التي يتجاوز حجمها الحد المحدد إلى مجلد خاص (عند توفر الحجم التقديري).",
        "en": "Routes files above the size limit to a dedicated folder (when an estimate is available).",
    },
    "rule_slow_quality": {"ar": "بطء الإنترنت → جودة أقل", "en": "Slow connection → lower quality"},
    "rule_slow_quality_hint": {
        "ar": "يحدّ من أعلى جودة فيديو عندما تكون سرعة التنزيل الحالية منخفضة.",
        "en": "Caps the maximum video height when the current download speed is low.",
    },
    "rule_custom": {"ar": "قاعدة مخصصة", "en": "Custom rule"},
    "rule_value_kind": {"ar": "النوع", "en": "Kind"},
    "rule_value_mb": {"ar": "الحد (ميجابايت)", "en": "Limit (MB)"},
    "rule_value_kbps": {"ar": "السرعة (كيلوبايت/ث)", "en": "Speed (KB/s)"},
    "rule_value_platform": {"ar": "المنصة", "en": "Platform"},
    "rule_value_keyword": {"ar": "كلمة في العنوان", "en": "Title keyword"},
    "rule_action_folder": {"ar": "اسم المجلد", "en": "Folder name"},
    "rule_action_height": {"ar": "أعلى ارتفاع", "en": "Max height"},
    "rule_add": {"ar": "إضافة قاعدة", "en": "Add rule"},
    "rule_add_title": {"ar": "قاعدة جديدة", "en": "New rule"},
    "rule_name": {"ar": "اسم القاعدة", "en": "Rule name"},
    "rule_condition": {"ar": "الشرط", "en": "Condition"},
    "rule_action": {"ar": "الإجراء", "en": "Action"},
    "rule_value": {"ar": "القيمة", "en": "Value"},
    "rule_save": {"ar": "حفظ", "en": "Save"},
    "rule_cancel": {"ar": "إلغاء", "en": "Cancel"},
    "rule_remove": {"ar": "حذف", "en": "Remove"},
    "rule_custom_empty": {"ar": "لا توجد قواعد مخصصة بعد.", "en": "No custom rules yet."},
    "rule_condition_kind": {"ar": "نوع الملف", "en": "File kind"},
    "rule_condition_size": {"ar": "الحجم ≥", "en": "Size ≥"},
    "rule_condition_speed": {"ar": "السرعة ≤", "en": "Speed ≤"},
    "rule_condition_platform": {"ar": "المنصة تحتوي", "en": "Platform contains"},
    "rule_condition_keyword": {"ar": "العنوان يحتوي", "en": "Title contains"},
    "rule_action_subdir": {"ar": "مجلد فرعي", "en": "Subfolder"},
    "rule_action_max_height": {"ar": "تحديد الجودة", "en": "Cap quality"},
    "rule_action_audio_only": {"ar": "صوت فقط", "en": "Audio only"},
    "toast_rule_saved": {"ar": "تم حفظ القاعدة", "en": "Rule saved"},
    "toast_rule_removed": {"ar": "تم حذف القاعدة", "en": "Rule removed"},
    "toast_rule_invalid": {"ar": "أكمل بيانات القاعدة بشكل صحيح", "en": "Fill in the rule details correctly"},
    "status_rules_applied": {"ar": "قواعد مطبّقة: {names}", "en": "Rules applied: {names}"},

    # ---- Duplicate file detection ------------------------------------
    "dup_title": {"ar": "كشف الملفات المكررة", "en": "Find duplicate files"},
    "dup_hint": {
        "ar": "يفحص المكتبة باستخدام بصمات SHA-256 المحفوظة أو الاسم والحجم. لا تتم قراءة محتوى الملفات.",
        "en": "Scans the library using saved SHA-256 digests, or name and size. File contents are never read.",
    },
    "dup_scan": {"ar": "فحص المكتبة", "en": "Scan library"},
    "dup_scanning": {"ar": "جارٍ الفحص…", "en": "Scanning…"},
    "dup_empty": {"ar": "لم يتم العثور على ملفات مكررة.", "en": "No duplicate files found."},
    "dup_found": {
        "ar": "تم العثور على {count} مجموعة مكررة",
        "en": "Found {count} duplicate group(s)",
    },
    "dup_wasted": {"ar": "مساحة قابلة للاسترداد: {size}", "en": "Reclaimable space: {size}"},
    "dup_reason_hash": {"ar": "بصمة متطابقة", "en": "Identical hash"},
    "dup_reason_name_size": {"ar": "الاسم والحجم متطابقان", "en": "Same name and size"},
    "dup_keep": {"ar": "الإبقاء", "en": "Keep"},
    "dup_remove": {"ar": "حذف", "en": "Remove"},
    "dup_cleanup": {"ar": "حذف المحدد", "en": "Delete selected"},
    "dup_min_size": {"ar": "أصغر حجم (ميجابايت)", "en": "Minimum size (MB)"},
    "dup_confirm": {
        "ar": "سيتم نقل {count} ملف إلى سلة المحذوفات وإزالته من السجل. هل تريد المتابعة؟",
        "en": "Move {count} file(s) to the Recycle Bin and remove them from history?",
    },
    "dup_done": {"ar": "تم حذف {count} ملف واسترداد {size}", "en": "Deleted {count} file(s), reclaimed {size}"},
    "dup_no_selection": {"ar": "اختر ملفاً واحداً على الأقل", "en": "Select at least one file"},
    "dup_open": {"ar": "كشف المكررات", "en": "Find duplicates"},

    # ---- Download groups ---------------------------------------------
    "groups_title": {"ar": "مجموعات التنزيل", "en": "Download groups"},
    "groups_hint": {
        "ar": "نظّم تنزيلاتك في مجموعات وتابع تقدم كل مجموعة على حدة.",
        "en": "Organise downloads into groups and track each group's progress.",
    },
    "groups_manage": {"ar": "إدارة المجموعات", "en": "Manage groups"},
    "groups_add": {"ar": "مجموعة جديدة", "en": "New group"},
    "groups_name": {"ar": "اسم المجموعة", "en": "Group name"},
    "groups_empty": {"ar": "لا توجد مجموعات بعد.", "en": "No groups yet."},
    "groups_assign": {"ar": "تعيين إلى مجموعة", "en": "Assign to group"},
    "groups_unassigned": {"ar": "بدون مجموعة", "en": "No group"},
    "groups_rename": {"ar": "إعادة تسمية", "en": "Rename"},
    "groups_remove": {"ar": "حذف المجموعة", "en": "Delete group"},
    "groups_start": {"ar": "بدء المجموعة", "en": "Start group"},
    "groups_pause": {"ar": "إيقاف المجموعة", "en": "Pause group"},
    "groups_summary": {"ar": "{done}/{total} مكتمل", "en": "{done}/{total} completed"},
    "groups_created": {"ar": "تم إنشاء المجموعة", "en": "Group created"},
    "groups_deleted": {"ar": "تم حذف المجموعة", "en": "Group deleted"},
    "groups_assigned": {"ar": "تم التعيين إلى {name}", "en": "Assigned to {name}"},
    "groups_no_group": {"ar": "أنشئ مجموعة أولاً", "en": "Create a group first"},
    "groups_color": {"ar": "اللون", "en": "Color"},

    # ---- Bandwidth / per-download speed -------------------------------
    "bw_menu": {"ar": "حد السرعة لهذا التنزيل", "en": "Speed limit for this download"},
    "bw_auto": {"ar": "حسب الإعدادات", "en": "Use setting"},
    "bw_unlimited": {"ar": "بلا حد", "en": "Unlimited"},
    "bw_set": {"ar": "{speed} كيلوبايت/ث", "en": "{speed} KB/s"},
    "bw_applied": {"ar": "تم تطبيق حد السرعة", "en": "Speed limit applied"},
    "bw_hint": {
        "ar": "يُطبَّق الحد فوراً على التنزيل الجاري ويُحفظ لإعادة المحاولة.",
        "en": "Applied immediately to the running download and saved for retries.",
    },

    # ---- Media workspace ---------------------------------------------
    "workspace_title": {"ar": "مساحة عمل الوسائط", "en": "Media workspace"},
    "workspace_subtitle": {
        "ar": "كل ما تحتاجه في لوحة واحدة: المهام، المكتبة، الأدوات، والإحصائيات.",
        "en": "Everything in one panel: tasks, library, tools and statistics.",
    },
    "workspace_open": {"ar": "فتح مساحة العمل", "en": "Open workspace"},
    "workspace_back": {"ar": "العودة للوحة الرئيسية", "en": "Back to dashboard"},
    "workspace_tasks": {"ar": "المهام النشطة", "en": "Active tasks"},
    "workspace_library": {"ar": "المكتبة", "en": "Library"},
    "workspace_tools": {"ar": "أدوات الوسائط", "en": "Media tools"},
    "workspace_stats": {"ar": "الإحصائيات", "en": "Statistics"},
    "workspace_empty_tasks": {"ar": "لا توجد مهام نشطة حالياً.", "en": "No active tasks right now."},
    "workspace_recent": {"ar": "أحدث الملفات", "en": "Recent files"},
    "workspace_quick": {"ar": "إجراءات سريعة", "en": "Quick actions"},

    # ---- Diagnostics --------------------------------------------------
    "diag_title": {"ar": "فحص النظام", "en": "System diagnostics"},
    "diag_hint": {
        "ar": "فحص سريع وبدون اتصال بالإنترنت لمكونات البرنامج وبيئة التشغيل.",
        "en": "A fast, offline check of the app components and runtime environment.",
    },
    "diag_open": {"ar": "فحص النظام", "en": "Run diagnostics"},
    "diag_run": {"ar": "إعادة الفحص", "en": "Re-run checks"},
    "diag_python": {"ar": "إصدار Python", "en": "Python version"},
    "diag_ytdlp": {"ar": "محرك التنزيل yt-dlp", "en": "yt-dlp engine"},
    "diag_ffmpeg": {"ar": "FFmpeg", "en": "FFmpeg"},
    "diag_js_runtime": {"ar": "محرك JavaScript", "en": "JavaScript runtime"},
    "diag_download_dir": {"ar": "مجلد التنزيلات", "en": "Download folder"},
    "diag_disk_space": {"ar": "المساحة المتاحة", "en": "Free disk space"},
    "diag_palette": {"ar": "الثيم المحفوظ", "en": "Saved palette"},
    "diag_history": {"ar": "سجل التنزيلات", "en": "Download history"},
    "diag_proxy": {"ar": "الخادم الوكيل", "en": "Proxy"},
    "diag_ok": {"ar": "سليم", "en": "OK"},
    "diag_warn": {"ar": "تحذير", "en": "Warning"},
    "diag_error": {"ar": "خطأ", "en": "Error"},

    # ---- First-run onboarding ----------------------------------------
    "onb_title": {"ar": "مرحباً بك في ProMediaDownloader", "en": "Welcome to ProMediaDownloader"},
    "onb_skip": {"ar": "تخطي", "en": "Skip"},
    "onb_next": {"ar": "التالي", "en": "Next"},
    "onb_back": {"ar": "السابق", "en": "Back"},
    "onb_finish": {"ar": "ابدأ الآن", "en": "Get started"},
    "onb_1_title": {"ar": "الصق رابط الوسائط", "en": "Paste a media link"},
    "onb_1_body": {
        "ar": "الصق رابط الفيديو أو الصوت في_homeوانقر «فحص». يمكنك أيضاً لصق عدة روابط دفعة واحدة من صندوق الوارد.",
        "en": "Paste a video or audio link on the home page and click Inspect. You can also paste several links at once from the Link Inbox.",
    },
    "onb_2_title": {"ar": "اختر الجودة ثم نزّل", "en": "Choose quality and download"},
    "onb_2_body": {
        "ar": "اختر أعلى جودة أو صوتاً فقط، ثم ابدأ التنزيل. تظهر المهام في صفحة التنزيلات النشطة.",
        "en": "Pick the best quality or audio-only, then start. Tasks appear on the Active Downloads page.",
    },
    "onb_3_title": {"ar": "نظّم مكتبتك", "en": "Organise your library"},
    "onb_3_body": {
        "ar": "أضف المفضلة والوسوم، ابحث بسرعة، واستخدم كشف المكررات لتنظيف الملفات المكررة بأمان.",
        "en": "Add favorites and tags, search quickly, and use duplicate detection to clean up safely.",
    },
    "onb_4_title": {"ar": "قواعد ذكية وأدوات احترافية", "en": "Smart rules and pro tools"},
    "onb_4_body": {
        "ar": "فعّل قواعد التحميل الذكية من الإعدادات، وجرّب أدوات FFmpeg، وافحص النظام بنقرة واحدة.",
        "en": "Enable smart download rules in Settings, try the FFmpeg tools, and run diagnostics in one click.",
    },

    "btn_open_downloads": {"ar": "فتح مجلد التنزيل", "en": "Open download folder"},
    "history_shown": {"ar": "عرض {shown} من {total}", "en": "Showing {shown} of {total}"},
    "stat_active": {"ar": "التنزيلات النشطة", "en": "Active downloads"},
    "stat_speed": {"ar": "السرعة الحالية", "en": "Current speed"},
    "settings_updates": {"ar": "التحديثات", "en": "Updates"},
    "settings_update_url": {"ar": "رابط ملف الإصدار", "en": "Version file URL"},
    "settings_update_url_hint": {
        "ar": "رابط JSON يحتوي على أحدث إصدار. اتركه فارغاً لتعطيل التحقق.",
        "en": "A JSON URL with the latest version. Leave empty to disable.",
    },
    "btn_check_updates": {"ar": "التحقق من التحديثات", "en": "Check for updates"},
    "status_update_unset": {
        "ar": "لم يتم ضبط رابط التحديثات.",
        "en": "Update URL is not configured.",
    },
    "status_update_checking": {
        "ar": "جارٍ التحقق من التحديثات…",
        "en": "Checking for updates…",
    },
    "status_update_available": {
        "ar": "يتوفر إصدار جديد: {version}",
        "en": "A new version is available: {version}",
    },
    "status_update_latest": {
        "ar": "أنت تستخدم أحدث إصدار ({version}).",
        "en": "You are on the latest version ({version}).",
    },
    "status_update_failed": {
        "ar": "تعذّر التحقق من التحديثات.",
        "en": "Could not check for updates.",
    },
    "history_no_results": {
        "ar": "لا توجد نتائج مطابقة للبحث.",
        "en": "No items match your search.",
    },
    "update_available_title": {"ar": "تحديث متوفر", "en": "Update available"},
    "update_open_confirm": {
        "ar": "يتوفر الإصدار {version}. هل تريد فتح صفحة التنزيل؟",
        "en": "Version {version} is available. Open the download page?",
    },
    "settings_ffmpeg_required_for_sub": {
        "ar": "تضمين الترجمة يتطلب FFmpeg.",
        "en": "Embedding subtitles requires FFmpeg.",
    },

    # --- 16-item UI overhaul -----------------------------------------
    "theme_system": {"ar": "النظام", "en": "System"},
    "theme_system_active": {"ar": "يتبع إعداد النظام", "en": "Follows system setting"},
    "settings_theme_hint": {
        "ar": "«النظام» يبدّل الثيم تلقائياً حسب إعدادات ويندوز.",
        "en": "“System” follows the Windows light/dark setting automatically.",
    },
    "settings_tab_general": {"ar": "عام", "en": "General"},
    "settings_tab_format": {"ar": "الصيغة", "en": "Format"},
    "settings_tab_network": {"ar": "الشبكة", "en": "Network"},
    "settings_tab_updates": {"ar": "التحديثات", "en": "Updates"},
    "settings_ui_scale": {"ar": "حجم الخط", "en": "Font size"},
    "ui_scale_normal": {"ar": "عادي", "en": "Normal"},
    "ui_scale_large": {"ar": "كبير", "en": "Large"},
    "settings_ui_scale_hint": {
        "ar": "كبّر النصوص في كل الواجهة لسهولة القراءة.",
        "en": "Enlarge text across the whole interface for easier reading.",
    },
    "settings_reduce_motion": {"ar": "تقليل الحركة", "en": "Reduce motion"},
    "settings_reduce_motion_hint": {
        "ar": "يعطّل انتقالات الصفحات والحركات التلقائية.",
        "en": "Disables page transitions and automatic animations.",
    },
    "settings_saved_badge": {"ar": "✓ تم الحفظ", "en": "✓ Saved"},
    "settings_saved_flash": {"ar": "تم حفظ الإعدادات", "en": "Settings saved"},

    "nav_active_badge_tip": {
        "ar": "{count} تنزيل نشط",
        "en": "{count} active download(s)",
    },
    "nav_home_tip": {"ar": "نظرة عامة على تحميلاتك", "en": "Overview of your downloads"},
    "nav_download_tip": {"ar": "بدء تنزيل جديد", "en": "Start a new download"},
    "nav_active_tip": {"ar": "متابعة التحميلات الجارية", "en": "Monitor downloads in progress"},
    "nav_queue_tip": {"ar": "إدارة طابور التحميل", "en": "Manage the download queue"},
    "nav_library_tip": {"ar": "ملفاتك المكتملة", "en": "Your completed files"},
    "nav_history_tip": {"ar": "عرض سجل التنزيلات", "en": "View download history"},
    "nav_tools_tip": {"ar": "تحويل وقص وضغط الوسائط", "en": "Convert, trim and compress media"},
    "nav_settings_tip": {"ar": "تخصيص البرنامج", "en": "Customize the app"},
    "home_go": {"ar": "تحليل الرابط", "en": "Analyze link"},

    "status_opened_notifications": {
        "ar": "تم فتح مركز الإشعارات",
        "en": "Opened the notification centre",
    },
    "status_opened_about": {"ar": "تم فتح نبذة عن البرنامج", "en": "Opened the about dialog"},

    # ---- Pro features -------------------------------------------------
    "settings_tab_pro": {"ar": "احترافي", "en": "Pro"},
    "settings_smart_naming": {
        "ar": "تسمية ذكية للملفات",
        "en": "Smart file naming",
    },
    "settings_smart_naming_hint": {
        "ar": "ينظّف عنوان الملف تلقائياً ويزيل الرموز غير الصالحة.",
        "en": "Cleans the file title automatically and removes invalid characters.",
    },
    "settings_auto_shutdown": {
        "ar": "إيقاف الجهاز بعد اكتمال التحميلات",
        "en": "Shut down the PC when downloads finish",
    },
    "settings_auto_shutdown_hint": {
        "ar": "يظهر عدّاد مع إمكانية الإلغاء قبل إيقاف الجهاز.",
        "en": "Shows a countdown with an option to cancel before shutdown.",
    },
    "settings_auto_fetch_clipboard": {
        "ar": "اقتراح تحميل الرابط المنسوخ تلقائياً",
        "en": "Offer to download copied links automatically",
    },
    "settings_auto_fetch_clipboard_hint": {
        "ar": "عند نسخ رابط فيديو يظهر سؤال: هل تريد تحميله؟",
        "en": "When a video link is copied, asks: do you want to download it?",
    },
    "settings_enable_stats": {
        "ar": "تفعيل إحصائيات التحميل",
        "en": "Enable download statistics",
    },
    "settings_enable_stats_hint": {
        "ar": "يعرض تقارير يومية وشهرية في الصفحة الرئيسية.",
        "en": "Shows daily and monthly reports on the home page.",
    },
    "settings_show_thumbnails": {
        "ar": "عرض الصور المصغّرة في المهام",
        "en": "Show thumbnails on task cards",
    },
    "settings_show_thumbnails_hint": {
        "ar": "يعرض صورة الفيديو داخل كل مهمة تنزيل.",
        "en": "Displays the video image inside every download task.",
    },
    "clipboard_prompt_title": {"ar": "رابط مكتشف", "en": "Link detected"},
    "clipboard_download_prompt": {
        "ar": "تم اكتشاف رابط فيديو، هل تريد تحميله؟",
        "en": "A video link was detected. Do you want to download it?",
    },
    "auto_shutdown_title": {"ar": "إيقاف تلقائي", "en": "Automatic shutdown"},
    "auto_shutdown_message": {
        "ar": "اكتملت جميع التحميلات. سيتم إيقاف الجهاز خلال {seconds} ثانية.",
        "en": "All downloads finished. The PC will shut down in {seconds} seconds.",
    },
    "auto_shutdown_cancel": {"ar": "إلغاء الإيقاف", "en": "Cancel shutdown"},
    "auto_shutdown_toast": {
        "ar": "سيتم إيقاف الجهاز بعد انتهاء التحميلات",
        "en": "The PC will shut down after downloads finish",
    },
    "stats_panel_title": {"ar": "إحصائيات التحميل", "en": "Download statistics"},
    "stats_today": {"ar": "اليوم", "en": "Today"},
    "stats_month": {"ar": "هذا الشهر", "en": "This month"},
    "stats_total": {"ar": "الإجمالي", "en": "All time"},
    "stats_last14": {"ar": "آخر 14 يوماً", "en": "Last 14 days"},
    "stats_count": {"ar": "{count} ملف", "en": "{count} files"},
    "stats_empty": {"ar": "لا توجد بيانات كافية بعد.", "en": "Not enough data yet."},
    "stats_refresh": {"ar": "تحديث", "en": "Refresh"},
    "mini_mode_title": {"ar": "الوضع المصغّر", "en": "Mini mode"},
    "mini_mode_tip": {"ar": "نافذة عائمة تعرض التحميلات", "en": "Floating window with downloads"},
    "mini_mode_empty": {"ar": "لا توجد تحميلات نشطة", "en": "No active downloads"},
    "info_size": {"ar": "الحجم التقريبي: {size}", "en": "Approx. size: {size}"},
    "info_suggest_format": {"ar": "الصيغة المقترحة: {format}", "en": "Suggested format: {format}"},
    "queue_priority_label": {"ar": "الأولوية: {name}", "en": "Priority: {name}"},
    "queue_priority_high": {"ar": "عالية", "en": "High"},
    "queue_priority_normal": {"ar": "عادية", "en": "Normal"},
    "queue_priority_low": {"ar": "منخفضة", "en": "Low"},

    "notifications_title": {"ar": "مركز الإشعارات", "en": "Notification centre"},
    "notifications_empty": {
        "ar": "لا توجد إشعارات بعد.",
        "en": "No notifications yet.",
    },
    "notifications_clear": {"ar": "مسح الكل", "en": "Clear all"},
    "notification_bell_tip": {"ar": "الإشعارات", "en": "Notifications"},
    "notifications_badge_tip": {
        "ar": "{count} إشعار جديد",
        "en": "{count} new notification(s)",
    },
    "notifications_just_now": {"ar": "الآن", "en": "Just now"},

    "about_title": {"ar": "حول البرنامج", "en": "About"},
    "about_tagline": {
        "ar": "مُنزّل وسائط سريع وأنيق لسطح المكتب",
        "en": "A fast, elegant desktop media downloader",
    },
    "about_version": {"ar": "الإصدار", "en": "Version"},
    "about_made_with": {
        "ar": "مبني بلغة Python باستخدام yt-dlp و CustomTkinter.",
        "en": "Built with Python, yt-dlp and CustomTkinter.",
    },
    "about_license": {
        "ar": "استخدمه لتنزيل المحتوى الذي تملك حقوقه فقط.",
        "en": "Use it only for content you have the rights to download.",
    },
    "about_shortcuts": {
        "ar": "اختصارات: Ctrl+1/2/3 للتنقل • Ctrl+F للبحث • Ctrl+V للصق • F5 للفحص",
        "en": "Shortcuts: Ctrl+1/2/3 pages • Ctrl+F search • Ctrl+V paste • F5 fetch",
    },
    "btn_close": {"ar": "إغلاق", "en": "Close"},

    "library_view_grid": {"ar": "شبكة", "en": "Grid"},
    "library_view_list": {"ar": "قائمة", "en": "List"},
    "library_view_tip": {"ar": "تبديل عرض المكتبة", "en": "Toggle library view"},
    "history_kpi_files": {"ar": "الملفات", "en": "Files"},
    "history_kpi_size": {"ar": "الحجم الإجمالي", "en": "Total size"},
    "history_kpi_last": {"ar": "آخر تنزيل", "en": "Last download"},
    "history_kpi_active": {"ar": "النشطة", "en": "Active"},
    "history_kpi_speed": {"ar": "السرعة", "en": "Speed"},
    "history_empty_title": {"ar": "مكتبتك فارغة", "en": "Your library is empty"},
    "history_empty_hint": {
        "ar": "نزّل أول ملف ليظهر هنا مع صورته المصغرة وتفاصيله.",
        "en": "Download your first file to see it here with its thumbnail and details.",
    },
    "history_empty_action": {"ar": "اذهب إلى التنزيل", "en": "Go to downloads"},
    "history_empty_filtered_title": {
        "ar": "لا توجد نتائج مطابقة",
        "en": "No matching results",
    },
    "history_empty_filtered_hint": {
        "ar": "جرّب كلمة بحث أخرى أو أزل عامل التصفية.",
        "en": "Try a different search or clear the filter.",
    },
    "history_empty_clear": {"ar": "مسح البحث والتصفية", "en": "Clear search & filters"},
    "search_tip": {"ar": "بحث", "en": "Search"},
    "search_clear_tip": {"ar": "مسح البحث", "en": "Clear search"},
    "url_clear_tip": {"ar": "مسح الرابط", "en": "Clear URL"},
    "drop_hint": {
        "ar": "يمكنك أيضاً سحب رابط وإفلاته داخل النافذة.",
        "en": "You can also drag and drop a link into the window.",
    },

    "ctx_open_file": {"ar": "فتح الملف", "en": "Open file"},
    "ctx_open_folder": {"ar": "فتح المجلد", "en": "Open folder"},
    "ctx_copy_link": {"ar": "نسخ الرابط", "en": "Copy link"},
    "ctx_retry": {"ar": "إعادة المحاولة", "en": "Retry"},
    "ctx_remove": {"ar": "إزالة من القائمة", "en": "Remove from list"},
    "ctx_pause": {"ar": "إيقاف مؤقت", "en": "Pause"},
    "ctx_resume": {"ar": "استئناف", "en": "Resume"},
    "ctx_cancel": {"ar": "إلغاء التنزيل", "en": "Cancel download"},
    "status_copied": {"ar": "تم نسخ الرابط.", "en": "Link copied."},

    "status_connection_online": {"ar": "متصل", "en": "Online"},
    "status_connection_offline": {"ar": "غير متصل", "en": "Offline"},
    "status_total_speed": {"ar": "السرعة: {speed}", "en": "Speed: {speed}"},
    "status_space": {"ar": "متاح: {free}", "en": "Free: {free}"},
    "download_status_idle": {
        "ar": "جاهز للبدء — ألصق رابطاً وابدأ التنزيل.",
        "en": "Ready — paste a link and start downloading.",
    },
    "skeleton_loading": {"ar": "جارٍ التحميل…", "en": "Loading…"},

    "kind_video": {"ar": "فيديو", "en": "Video"},
    "kind_audio": {"ar": "صوت", "en": "Audio"},
    "kind_image": {"ar": "صورة", "en": "Image"},
    "kind_other": {"ar": "ملف", "en": "File"},
    "timeline_today": {"ar": "اليوم", "en": "Today"},
    "timeline_yesterday": {"ar": "أمس", "en": "Yesterday"},
    "timeline_earlier": {"ar": "أقدم", "en": "Earlier"},
}

# Tags shown next to known video heights (language neutral).
VIDEO_HEIGHT_TAGS = {
    4320: "8K",
    2160: "4K",
    1440: "2K",
    1080: "Full HD",
    720: "HD",
    480: "SD",
}

# Flags to avoid repeated import attempts / incomplete shaping.
_shaper_ready: bool | None = None


def translate(lang: str, key: str, **kwargs: Any) -> str:
    """Return the translation of *key* for *lang* (with optional formatting).

    Falls back to English, then to the key itself, so the UI never crashes on
    a missing translation.
    """
    lang = lang if lang in LANGUAGES else DEFAULT_LANGUAGE
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANGUAGE) or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def _load_shapers() -> bool:
    """Try to import the optional Arabic shaping libraries once."""
    global _shaper_ready
    if _shaper_ready is None:
        try:
            import arabic_reshaper  # noqa: F401
            from bidi.algorithm import get_display  # noqa: F401

            _shaper_ready = True
        except Exception:  # pragma: no cover - optional dependency
            _shaper_ready = False
    return _shaper_ready


def shape_for_tk(text: str, lang: str) -> str:
    """Prepare *text* for display in Tkinter.

    Tk (8.6) does not shape Arabic glyphs or apply the bidi algorithm, so
    Arabic labels would otherwise appear as disconnected, reversed letters.
    When the optional ``arabic-reshaper``/``python-bidi`` packages are
    available they are used transparently.
    """
    if not text or lang != "ar":
        return text
    if not _load_shapers():
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # pragma: no cover - defensive
        return text


def is_rtl(lang: str) -> bool:
    return lang == "ar"
