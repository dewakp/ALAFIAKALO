"""ALAFIA's UI string catalogs — read, write, and check placeholders. No network.

`translate_catalogs.py` does the translating; this module owns the formats, so
the rules that keep a translation SAFE to ship live in one testable place:

  - a translation that drops, adds or alters a placeholder is refused. A web
    string missing `{{count}}` renders a sentence with a hole in it; an Android
    string whose `%1$s` became `%d` crashes the formatter at runtime.
  - every machine translation is recorded against the English it came from, so
    a changed source is re-translated and re-flagged instead of drifting.

Catalogs, one English source per platform, in the platform's own format:

  web      WEB/frontend/src/locales/<lang>.json            i18next, {{name}}
  android  Android/app/src/main/res/values[-<lang>]/strings.xml   %1$s, %d
  ios      i18n/ios/<lang>.xliff (Xcode export / import)   %@, %lld
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

REPO = Path(__file__).resolve().parents[2]
SOURCE_LANGUAGE = "en"

# The product's languages: the same eleven codes as the web switcher
# (WEB/frontend/src/i18n.js), the backend (app/services/prompt_language.py) and
# AppLanguage on iOS and Android. test_catalogs.py pins the web copy.
LANGUAGES: dict[str, str] = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ar": "Arabic",
    "zh": "Chinese (Simplified)",
    "yo": "Yoruba",
    "ig": "Igbo",
    "ha": "Hausa",
    "sw": "Swahili",
}

PLATFORMS = ("web", "android", "ios")

_PLACEHOLDER = re.compile(r"\{\{\s*[\w.]+\s*\}\}|%(?:\d+\$)?(?:lld|ld|@|[sdfu])|%%")


def placeholders(text: str) -> Counter:
    return Counter(match.group(0).replace(" ", "") for match in _PLACEHOLDER.finditer(text))


def placeholder_problem(source: str, translation: str) -> str | None:
    """Why this translation cannot ship, or None when its placeholders match."""
    wanted, got = placeholders(source), placeholders(translation)
    if wanted == got:
        return None
    parts = []
    missing = sorted((wanted - got).elements())
    added = sorted((got - wanted).elements())
    if missing:
        parts.append(f"missing {missing}")
    if added:
        parts.append(f"added {added}")
    return "; ".join(parts)


# ── web: nested i18next JSON, addressed by dotted keys ───────────────────────

def web_path(lang: str, root: Path = REPO) -> Path:
    return root / "WEB" / "frontend" / "src" / "locales" / f"{lang}.json"


def flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in tree.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict):
            flat.update(flatten(value, f"{dotted}."))
        else:
            flat[dotted] = str(value)
    return flat


def unflatten(flat: dict[str, str]) -> dict:
    tree: dict = {}
    for dotted, value in flat.items():
        node = tree
        *parents, leaf = dotted.split(".")
        for part in parents:
            node = node.setdefault(part, {})
        node[leaf] = value
    return tree


def read_web(lang: str, root: Path = REPO) -> dict[str, str]:
    path = web_path(lang, root)
    return flatten(json.loads(path.read_text(encoding="utf-8"))) if path.exists() else {}


def write_web(lang: str, entries: dict[str, str], order: list[str], root: Path = REPO) -> Path:
    ordered = {key: entries[key] for key in order if key in entries}
    path = web_path(lang, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(unflatten(ordered), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


# ── android: res/values[-<lang>]/strings.xml ─────────────────────────────────

def android_path(lang: str, root: Path = REPO) -> Path:
    folder = "values" if lang == SOURCE_LANGUAGE else f"values-{lang}"
    return root / "Android" / "app" / "src" / "main" / "res" / folder / "strings.xml"


def android_unescape(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch == "\\" and i + 1 < len(text):
            nxt = text[i + 1]
            out.append({"n": "\n", "t": "\t"}.get(nxt, nxt))
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def android_escape(text: str) -> str:
    """Android's resource escaping, then XML's. An unescaped apostrophe is a
    BUILD failure (aapt2), and a leading @ or ? is read as a resource reference."""
    escaped = (text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
               .replace("\n", "\\n").replace("\t", "\\t"))
    if escaped[:1] in ("@", "?"):
        escaped = "\\" + escaped
    return xml_escape(escaped)


def read_android(lang: str, root: Path = REPO) -> dict[str, str]:
    path = android_path(lang, root)
    if not path.exists():
        return {}
    entries: dict[str, str] = {}
    for element in ET.parse(path).getroot().findall("string"):
        if element.get("translatable") == "false":
            continue
        entries[element.get("name")] = android_unescape("".join(element.itertext()))
    return entries


def write_android(lang: str, entries: dict[str, str], order: list[str], root: Path = REPO) -> Path:
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f"<!-- {LANGUAGES[lang]}. Machine-translated entries are listed for review in",
        f"     i18n/review/android/{lang}.json. Generated by scripts/i18n/translate_catalogs.py. -->",
        "<resources>",
    ]
    lines += [f'    <string name="{key}">{android_escape(entries[key])}</string>' for key in order if key in entries]
    lines.append("</resources>")
    path = android_path(lang, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ── ios: Xcode's XLIFF export and import ─────────────────────────────────────
#
# SwiftUI treats a literal that reaches a `LocalizedStringKey` — `Text("Save")`,
# or a component whose title is typed that way — as a localization key. A
# `String` is drawn verbatim and never extracted; test_catalogs.py guards that.
# `xcodebuild -exportLocalizations -exportLanguage en` extracts every key —
# 1,525 app strings and 9 Info.plist prompts on 2026-09-15 — and
# `xcodebuild -importLocalizations` writes a language back into the project's
# String Catalogs, so project.pbxproj is never edited by hand.

_XLIFF_NS = "urn:oasis:names:tc:xliff:document:1.2"
_X = f"{{{_XLIFF_NS}}}"
_HAS_WORDS = re.compile(r"[^\W\d_]{2,}")


def ios_path(lang: str, root: Path = REPO) -> Path:
    return root / "i18n" / "ios" / f"{lang}.xliff"


def _ios_key(file_element: ET.Element, unit: ET.Element) -> str:
    # Keyed by catalog as well as id: InfoPlist and Localizable are separate
    # namespaces, and their ids are not the English text (NSCameraUsageDescription).
    return f"{Path(file_element.get('original', '')).name}::{unit.get('id')}"


def read_ios(lang: str, root: Path = REPO) -> dict[str, str]:
    path = ios_path(lang, root)
    if not path.exists():
        return {}
    entries: dict[str, str] = {}
    for file_element in ET.parse(path).getroot().iter(f"{_X}file"):
        for unit in file_element.iter(f"{_X}trans-unit"):
            if lang == SOURCE_LANGUAGE:
                text = unit.findtext(f"{_X}source", default="")
                # Words are counted with placeholders removed: the "lld" in "#%lld"
                # is a format specifier, and "#%lld" or "%lld/10" has nothing to translate.
                if _HAS_WORDS.search(_PLACEHOLDER.sub("", text)):
                    entries[_ios_key(file_element, unit)] = text
                continue
            target = unit.find(f"{_X}target")
            # state="new" is Xcode's English placeholder, not a translation.
            if target is not None and target.get("state") != "new" and (target.text or "").strip():
                entries[_ios_key(file_element, unit)] = target.text
    return entries


def write_ios(lang: str, entries: dict[str, str], order: list[str], root: Path = REPO) -> Path:
    """<lang>.xliff built on the English export, ready for -importLocalizations.

    `order` is unused — the export's own structure is kept — and accepted for a
    common writer signature. An untranslated unit carries no <target>, so Xcode
    shows English there rather than an empty string.

    Targets are written as state="translated". "needs-review-translation" was
    the first choice and Xcode skips every such unit as unfinished: the import
    exited 0, printed 1,239 warnings and "No translations to import", and
    imported nothing. Review status lives in i18n/review/ios/<lang>.json instead.
    """
    ET.register_namespace("", _XLIFF_NS)
    ET.register_namespace("xsi", "http://www.w3.org/2001/XMLSchema-instance")
    tree = ET.parse(ios_path(SOURCE_LANGUAGE, root))
    for file_element in tree.getroot().iter(f"{_X}file"):
        file_element.set("target-language", lang)
        for unit in file_element.iter(f"{_X}trans-unit"):
            target = unit.find(f"{_X}target")
            translation = entries.get(_ios_key(file_element, unit))
            if translation is None:
                if target is not None:
                    unit.remove(target)
                continue
            if target is None:
                target = ET.Element(f"{_X}target")
                unit.insert(1, target)  # directly after <source>
            target.text = translation
            target.set("state", "translated")
    path = ios_path(lang, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return path


READERS = {"web": read_web, "android": read_android, "ios": read_ios}
WRITERS = {"web": write_web, "android": write_android, "ios": write_ios}


# ── review ledger: what the machine translated, against which English ────────

def review_path(platform: str, lang: str, root: Path = REPO) -> Path:
    return root / "i18n" / "review" / platform / f"{lang}.json"


def read_review(platform: str, lang: str, root: Path = REPO) -> dict[str, dict]:
    path = review_path(platform, lang, root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_review(platform: str, lang: str, ledger: dict[str, dict], root: Path = REPO) -> Path:
    path = review_path(platform, lang, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(ledger.items())), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def needs_translation(source: dict[str, str], target: dict[str, str], ledger: dict[str, dict]) -> dict[str, str]:
    """Entries to (re)translate: absent in the target, or translated from an
    English source that has since changed. A reviewed, current entry is kept."""
    todo = {}
    for key, english in source.items():
        if key not in target:
            todo[key] = english
        elif key in ledger and ledger[key].get("source") != english:
            todo[key] = english
    return todo
