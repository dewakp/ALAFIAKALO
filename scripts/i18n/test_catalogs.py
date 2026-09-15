"""The rules that make a machine translation safe to ship.

    docker run --rm -v "$PWD":/repo -w /repo web-backend-test \
        python -m pytest -q -p no:cacheprovider scripts/i18n/test_catalogs.py
"""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalogs  # noqa: E402


@pytest.mark.parametrize("source,translation,problem", [
    ("{{count}} meals today", "{{ count }} comidas hoy", None),          # spacing is not a change
    ("{{count}} meals today", "comidas hoy", "missing ['{{count}}']"),
    ("Hello %1$s", "Bonjour %s", "missing ['%1$s']; added ['%s']"),     # would crash the formatter
    ("%@ logged %lld doses", "%@ a enregistré %lld doses", None),
    ("100%% done", "100%% terminé", None),
    ("Save", "Guardar {{extra}}", "added ['{{extra}}']"),
])
def test_a_translation_that_breaks_a_placeholder_is_refused(source, translation, problem):
    assert catalogs.placeholder_problem(source, translation) == problem


def test_web_catalogs_round_trip_in_source_order_and_keep_unicode(tmp_path):
    source = {"nav.home": "Home", "nav.meals": "Meals", "common.save": "Save"}
    catalogs.write_web("yo", {"common.save": "Fi pamọ́", "nav.home": "Ilé"}, list(source), root=tmp_path)
    written = catalogs.web_path("yo", tmp_path).read_text(encoding="utf-8")
    assert "Fi pamọ́" in written                       # not \\u escapes
    assert catalogs.read_web("yo", tmp_path) == {"nav.home": "Ilé", "common.save": "Fi pamọ́"}
    assert list(json.loads(written)) == ["nav", "common"]  # source order; untranslated keys absent


@pytest.mark.parametrize("text", [
    "Don't forget your dose",
    '"Quoted" text',
    "@home is a resource reference unless escaped",
    "?attr likewise",
    "Two\nlines",
    "Back\\slash & <angle>",
    "%1$s of %2$d",
])
def test_android_escaping_round_trips(tmp_path, text):
    catalogs.write_android("fr", {"k": text}, ["k"], root=tmp_path)
    assert catalogs.read_android("fr", tmp_path) == {"k": text}


def test_android_skips_strings_marked_untranslatable(tmp_path):
    path = catalogs.android_path("en", tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text('<resources><string name="app_name" translatable="false">ALAFIA</string>'
                    '<string name="login">Login</string></resources>', encoding="utf-8")
    assert catalogs.read_android("en", tmp_path) == {"login": "Login"}


def test_only_missing_or_stale_entries_are_sent_for_translation():
    source = {"a": "Save", "b": "Delete meal", "c": "Close"}
    target = {"a": "Guardar", "b": "Eliminar"}
    ledger = {"a": {"source": "Save"}, "b": {"source": "Delete"}}   # b's English has since changed
    assert catalogs.needs_translation(source, target, ledger) == {"b": "Delete meal", "c": "Close"}


# The shape of Xcode 26's -exportLocalizations output, trimmed.
_XLIFF = """<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="urn:oasis:names:tc:xliff:document:1.2" version="1.2">
  <file original="ALAFIA/Resources/InfoPlist.xcstrings" source-language="en" target-language="en" datatype="plaintext">
    <body>
      <trans-unit id="NSCameraUsageDescription" xml:space="preserve">
        <source>ALAFIA uses your camera to photograph a meal.</source>
        <target state="new">ALAFIA uses your camera to photograph a meal.</target>
        <note>Privacy - Camera Usage Description</note>
      </trans-unit>
    </body>
  </file>
  <file original="ALAFIA/Resources/Localizable.xcstrings" source-language="en" target-language="en" datatype="plaintext">
    <body>
      <trans-unit id="#%@" xml:space="preserve"><source>#%@</source><target state="new">#%@</target><note/></trans-unit>
      <trans-unit id="#%lld" xml:space="preserve"><source>#%lld</source><target state="new">#%lld</target><note/></trans-unit>
      <trans-unit id="%lld/10" xml:space="preserve"><source>%lld/10</source><target state="new">%lld/10</target><note/></trans-unit>
      <trans-unit id="%lld doses" xml:space="preserve"><source>%lld doses</source><target state="new">%lld doses</target><note/></trans-unit>
      <trans-unit id="Save" xml:space="preserve"><source>Save</source><target state="new">Save</target><note/></trans-unit>
    </body>
  </file>
</xliff>
"""


def _ios_export(root):
    path = catalogs.ios_path("en", root)
    path.parent.mkdir(parents=True)
    path.write_text(_XLIFF, encoding="utf-8")


def test_ios_reads_every_worded_string_including_the_permission_prompts(tmp_path):
    _ios_export(tmp_path)
    assert catalogs.read_ios("en", tmp_path) == {
        "InfoPlist.xcstrings::NSCameraUsageDescription": "ALAFIA uses your camera to photograph a meal.",
        "Localizable.xcstrings::%lld doses": "%lld doses",
        "Localizable.xcstrings::Save": "Save",
    }


def test_ios_writes_an_xliff_xcode_will_actually_import(tmp_path):
    _ios_export(tmp_path)
    translated = {"Localizable.xcstrings::Save": "Fi pamọ́", "Localizable.xcstrings::%lld doses": "%lld ìwọ̀n"}
    catalogs.write_ios("yo", translated, [], root=tmp_path)
    written = catalogs.ios_path("yo", tmp_path).read_text(encoding="utf-8")
    assert written.count('target-language="yo"') == 2
    # Xcode skips "needs-review-translation" as unfinished and imports nothing;
    # review status is kept in i18n/review/ios/<lang>.json instead.
    assert written.count('state="translated"') == 2
    assert "needs-review-translation" not in written
    assert "ns0:" not in written  # Xcode's default namespace is kept
    # Untranslated units carry no target, so an English placeholder is never read as a translation.
    assert catalogs.read_ios("yo", tmp_path) == translated


def test_the_model_sees_short_ids_so_it_cannot_rewrite_our_keys():
    """Given the real keys, the model echoed them back with its own typography —
    “%@” as "%@" — which broke the JSON and lost the whole batch. Ids survive that."""
    import asyncio

    sys.path.insert(0, str(catalogs.REPO / "ML" / "src"))
    import translate_catalogs as tc

    sent = {}

    class _Reply:
        success, error, source = True, None, "fake:model"

        def __init__(self, text):
            self.data = {"text": text}

    class _Provider:
        async def infer(self, payload):
            numbered = json.loads(payload["messages"][1]["content"])
            sent.update(numbered)
            answer = {n: f"FR {text}" for n, text in numbered.items()}
            return _Reply("```json\n" + json.dumps(answer, ensure_ascii=False) + "\n```")

    batch = {
        "Localizable.xcstrings::Couldn’t check your membership": "Couldn’t check your membership",
        "Localizable.xcstrings::No ICD-11 match for “%@”.": "No ICD-11 match for “%@”.",
    }
    translations, raw, source = asyncio.run(tc._translate_batch(_Provider(), "French", batch))

    assert set(sent) == {"1", "2"}  # the model never sees our keys
    assert translations == {key: f"FR {text}" for key, text in batch.items()}
    assert source == "fake:model"


def test_every_platform_offers_exactly_the_same_languages():
    """One language list, four copies. A language one client offers and another
    does not is a patient who picks Yoruba on the web and gets English on the phone."""
    repo = catalogs.REPO
    expected = set(catalogs.LANGUAGES)

    web = (repo / "WEB/frontend/src/i18n.js").read_text(encoding="utf-8")
    assert set(re.findall(r"\{ code: '([a-z]{2})'", web)) == expected, "web i18n.js"

    backend = (repo / "WEB/backend/app/services/prompt_language.py").read_text(encoding="utf-8")
    block = backend.split("LANGUAGES: dict[str, tuple[str, str]] = {", 1)[1].split("}", 1)[0]
    assert set(re.findall(r'"([a-z]{2})": \(', block)) == expected, "backend prompt_language.py"

    ios = (repo / "IOS/ALAFIA/App/AppConfig.swift").read_text(encoding="utf-8")
    ios_codes = re.search(r"static let codes = \[([^\]]+)\]", ios).group(1)
    assert set(re.findall(r'"([a-z]{2})"', ios_codes)) == expected, "iOS AppLanguage.codes"

    android = (repo / "Android/app/src/main/java/com/alafia/android/AppLanguage.kt").read_text(encoding="utf-8")
    android_codes = re.search(r"val CODES = listOf\(([^)]+)\)", android).group(1)
    assert set(re.findall(r'"([a-z]{2})"', android_codes)) == expected, "Android AppLanguage.CODES"


# ── iOS: a worded literal must reach a LocalizedStringKey ────────────────────

def _skip_string(src: str, i: int) -> int:
    """Index just past the Swift string literal that opens at src[i]."""
    triple = src.startswith('"""', i)
    i += 3 if triple else 1
    while i < len(src):
        if src.startswith("\\(", i):
            i = _close(src, i + 1, "(", ")")
        elif src[i] == "\\":
            i += 2
        elif triple and src.startswith('"""', i):
            return i + 3
        elif not triple and src[i] == '"':
            return i + 1
        else:
            i += 1
    return i


def _close(src: str, i: int, opener: str, closer: str) -> int:
    """Index just past the bracket closing the one at src[i], skipping strings and comments."""
    depth = 0
    while i < len(src):
        if src[i] == '"':
            i = _skip_string(src, i)
            continue
        if src.startswith("//", i):
            i = src.find("\n", i) % (len(src) + 1)
            continue
        if src[i] == opener:
            depth += 1
        elif src[i] == closer:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


_DRAWN = r"(?:\bText|\bLabel|\bTextField|\bSecureField|\bButton|\bToggle|\bSection|\.navigationTitle)\(\s*{prop}\s*[,)]"

# Parameters that name a piece of interface text. `value`, `unit` and their kind
# carry data — "\(hr) bpm", "kcal" — and drawing those verbatim is right.
_LABEL_PROP = re.compile(r"(?i)^(?:\w*(?:title|label|message|desc|description|caption|header|placeholder|prompt|hint)|text)$")


def _worded(literal: str) -> bool:
    """Whether a Swift literal, quotes included, holds words to translate once
    interpolations, placeholders and acronyms ("FDC", "BMI") are set aside."""
    kept, i = [], 1
    while i < len(literal) - 1:
        if literal.startswith("\\(", i):
            i = _close(literal, i + 1, "(", ")")
        else:
            kept.append(literal[i])
            i += 1
    text = catalogs._PLACEHOLDER.sub("", "".join(kept))
    return any(not word.isupper() for word in catalogs._HAS_WORDS.findall(text))


def test_ios_worded_literals_are_never_drawn_through_a_string():
    """`Text(title)` with `title: String` renders verbatim and Xcode never
    extracts the caller's literal. Every label drawn through LKTextField and
    LKButton stayed English in every language — "Password" and "Sign In" on a
    French login screen — until those titles became LocalizedStringKey."""
    root = catalogs.REPO / "IOS" / "ALAFIA"
    sources = {path: path.read_text(encoding="utf-8") for path in root.rglob("*.swift")}

    seen, drawn = set(), {}
    for text in sources.values():
        for struct in re.finditer(r"\bstruct (\w+)\s*:\s*View\s*\{", text):
            seen.add(struct.group(1))
            body = text[struct.end() - 1:_close(text, struct.end() - 1, "{", "}")]
            for prop in re.findall(r"\b(?:let|var) (\w+)\s*:\s*String\b(?![?!])", body):
                if _LABEL_PROP.match(prop) and re.search(_DRAWN.format(prop=re.escape(prop)), body):
                    drawn.setdefault(struct.group(1), set()).add(prop)
    assert {"LKTextField", "LKButton", "LoginView"} <= seen, "the scan cannot see the views — it is broken, not clean"

    offenders = []
    for path, text in sources.items():
        for view, props in drawn.items():
            for call in re.finditer(rf"\b{view}\(", text):
                args = text[call.end() - 1:_close(text, call.end() - 1, "(", ")")]
                for prop in props:
                    for arg in re.finditer(rf'\b{prop}:\s*"', args):
                        literal = args[arg.end() - 1:_skip_string(args, arg.end() - 1)]
                        if _worded(literal):
                            line = text.count("\n", 0, call.start()) + 1
                            offenders.append(f"{path.relative_to(root)}:{line} {view}({prop}: {literal})")
    assert not offenders, "type these parameters LocalizedStringKey:\n" + "\n".join(offenders)
