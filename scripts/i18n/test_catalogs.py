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


def test_a_reply_quoting_a_term_with_plain_quotes_is_still_read():
    """Every string that quotes a term was refused in every language: the model
    wrote “kidney” as "kidney" inside its JSON string, the reply stopped being
    JSON, and each retry failed the same way. This is the reply it gave, verbatim."""
    sys.path.insert(0, str(catalogs.REPO / "ML" / "src"))
    import translate_catalogs as tc

    raw = ('```json\n{\n  "1": "Versuchen Sie „kidney", „ESRD", „sickle cell" oder einen Code wie „GB61.5".",\n'
           '  "2": "Zeile eins\\nZeile zwei"\n}\n```')
    assert tc._parse_numbered(raw, {"1", "2"}) == {
        "1": 'Versuchen Sie „kidney", „ESRD", „sickle cell" oder einen Code wie „GB61.5".',
        "2": "Zeile eins\nZeile zwei",
    }
    # A reply that is already valid JSON is taken as it is.
    assert tc._parse_numbered('{"1": "Senha"}', {"1"}) == {"1": "Senha"}


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


def test_ios_messages_built_in_code_follow_the_chosen_language():
    """A view model's `errorMessage = "…"` is a String, which SwiftUI draws
    verbatim: 24 of them stayed English on screens the patient had set to French.
    `AppLanguage.text("…")` looks the message up in the chosen language
    (LocalizationTests proves that on the simulator)."""
    root = catalogs.REPO / "IOS" / "ALAFIA"
    assigned = re.compile(r'\b(?:errorMessage|error|message|statusMessage|successMessage|alertMessage|alertTitle|'
                          r'infoMessage|toast)\s*=\s*("(?:[^"\\\n]|\\.)*")')
    offenders = []
    for path in sorted(root.rglob("*.swift")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for match in assigned.finditer(line):
                words = re.sub(r"\\\(.*?\)", "", match.group(1))
                if catalogs._HAS_WORDS.search(words):
                    offenders.append(f"{path.relative_to(root)}:{number}  {line.strip()[:100]}")
    assert not offenders, "wrap these in AppLanguage.text(…):\n" + "\n".join(offenders)


# ── Android: Compose text comes from resources ───────────────────────────────

@pytest.mark.parametrize("kotlin,string,call", [
    # A template becomes positional arguments; word order is the translator's.
    ('Text("Delete PD session from ${s.date}?")', "Delete PD session from %1$s?", "stringResource(R.string.x, s.date)"),
    # Quotes inside an interpolation do not end the literal.
    ('Text("Ref: ${r.low ?: "-"} – ${r.high ?: "-"}")', "Ref: %1$s – %2$s", 'stringResource(R.string.x, r.low ?: "-", r.high ?: "-")'),
    # Kotlin's $name takes an identifier only: ".take(3)" is literal text.
    ('Text("Qty: $it.take(3)")', "Qty: %1$s.take(3)", "stringResource(R.string.x, it)"),
    ('Text("e.g. \\"I take Calcitriol\\"")', 'e.g. "I take Calcitriol"', "stringResource(R.string.x)"),
    # % is doubled only when the string is formatted.
    ('Text("e.g., 1.5% Dextrose")', "e.g., 1.5% Dextrose", "stringResource(R.string.x)"),
    ('Text("${pct}% done")', "%1$s%% done", "stringResource(R.string.x, pct)"),
])
def test_android_literals_become_resources(kotlin, string, call):
    import android_extract as ax
    from collections import Counter

    taken, report = {}, Counter()
    out = ax.rewrite(kotlin, taken, report)
    (name, text), = taken.items()
    assert text == string
    assert out == f"Text({call.replace('R.string.x', f'R.string.{name}')})"


@pytest.mark.parametrize("kotlin,reason", [
    ('Text("Price: $%.2f / month".format(it))', "skipped: not the whole argument"),
    ('Text("UF ${it.toInt()}")', "skipped: nothing to translate"),   # an acronym and a number
    ('Text("• ${meal.name}")', "skipped: nothing to translate"),
    ('Text("Visit https://alafia.app/help")', "skipped: nothing to translate"),
    ('NavItem(route = "home", contentDescription = "Home")', "skipped: contentDescription outside Icon/Image"),
])
def test_android_literals_that_must_stay_as_they_are(kotlin, reason):
    import android_extract as ax
    from collections import Counter

    report = Counter()
    assert ax.rewrite(kotlin, {}, report) == kotlin
    assert report[reason] == 1


def test_android_text_handed_to_our_composables_becomes_a_resource():
    """The login screen's "Password" stayed English in Arabic and French: it was
    PasswordField's default argument, which pass 1 — Text("…") only — never saw."""
    import android_extract as ax
    from collections import Counter
    from pathlib import Path

    path = Path("Screen.kt")
    src = '''@Composable
fun SwitchSetting(title: String, description: String = "Off by default", checked: Boolean) {}

@Composable
fun Screen() {
    SwitchSetting("Health Reminders", description = "Remind me to log", checked = true)
    Text(text = "Welcome back")
    val pulse = rememberInfiniteTransition(label = "chat status")
    Pill(label = "Active")
}
'''
    taken = {}
    out = ax.convert(src, path, ax.signatures({path: src}), taken, Counter())
    assert set(taken.values()) == {"Off by default", "Health Reminders", "Remind me to log", "Welcome back"}
    assert "description: String = stringResource(R.string." in out            # a default argument
    assert 'rememberInfiniteTransition(label = "chat status")' in out          # an animation's debug label
    assert 'Pill(label = "Active")' in out                                     # not a composable we declare


@pytest.mark.parametrize("kotlin,converted,kept", [
    ('Text(if (busy) "Signing…" else "Sign off on this session")', {"Signing…", "Sign off on this session"}, []),
    ('Text(card.emptyReason ?: "Nothing recorded.", style = s)', {"Nothing recorded."}, []),
    # The literal the expression TESTS is data: translated, it would never match.
    ('Text(if (status == "active") "Active" else "Stopped")', {"Active", "Stopped"}, ['status == "active"']),
    ('Text(if ("pending" != state) "Done" else "Waiting")', {"Done", "Waiting"}, ['"pending" != state']),
    ('Text("Price: $%.2f / month".format(it))', set(), ['"Price: $%.2f / month".format(it)']),
    ('Text((if (danger) "⚠ " else "") + value)', set(), []),                  # nothing worded
    # An argument to a nested call may be a lookup key.
    ('Text(labelFor("potassium"))', set(), ['labelFor("potassium")']),
])
def test_android_literal_branches_of_a_text_argument(kotlin, converted, kept):
    import android_extract as ax
    from collections import Counter
    from pathlib import Path

    taken = {}
    out = ax.convert(kotlin, Path("S.kt"), {}, taken, Counter())
    assert set(taken.values()) == converted
    for fragment in kept:
        assert fragment in out


def test_android_has_no_hard_coded_ui_text():
    """1,169 `Text("…")` literals rendered English in every language, because a
    Compose literal is never looked up — and so did "Password", a default
    argument. Anything android_extract would still convert is a new one."""
    import android_extract as ax
    from collections import Counter

    sources = {path: path.read_text(encoding="utf-8") for path in sorted(ax.SOURCES.rglob("*.kt"))}
    sigs = ax.signatures(sources)
    offenders = []
    for path, src in sources.items():
        report = Counter()
        taken = dict(catalogs.read_android(catalogs.SOURCE_LANGUAGE))
        if ax.convert(src, path, sigs, taken, report) != src:
            offenders.append(f"{path.relative_to(ax.SOURCES)}: {dict(report)}")
    assert not offenders, ("hard-coded Compose text — run scripts/i18n/android_extract.py --apply:\n"
                           + "\n".join(offenders))
