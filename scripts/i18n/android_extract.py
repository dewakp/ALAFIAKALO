"""Move Android's hard-coded Compose strings into res/values/strings.xml.

    docker run --rm -v "$PWD":/repo -w /repo web-backend-test \
        python scripts/i18n/android_extract.py            # report only
        python scripts/i18n/android_extract.py --apply    # rewrite sources + strings.xml

`Text("…")` and `Icon(…, contentDescription = "…")` become
`stringResource(R.string.<name>)`. A Kotlin template becomes positional
arguments, so word order stays the translator's to choose:

    Text("Delete PD session from ${session.sessionDate}?")
    Text(stringResource(R.string.delete_pd_session_from, session.sessionDate))
    <string name="delete_pd_session_from">Delete PD session from %1$s?</string>

Left alone, and reported: a literal that is not the whole argument
(`"…" + x`, `"…".format(x)`), one with nothing to translate ("•", "UF $x",
"$count"), a URL or address, and a contentDescription outside an Icon or Image
(stringResource only compiles in composable scope).

Text(...) is itself composable, so its argument is always in composable scope.
The build is still the proof: run `./gradlew :app:assembleDebug` after --apply.
A template printed a null value as "null"; `stringResource` takes `vararg Any`
and the build refuses it — give that argument a real fallback at the call site
(two of ~1,600 conversions needed one).

Text handed to one of OUR composables converts too — `SwitchSetting("Health
Reminders", description = "…")`, `PasswordField(label: String = "Password")` —
when the parameter is a String whose name says it is text (title, label,
description, …). The login screen's "Password" stayed English in every language
because it was a default argument, not a Text. An argument to a composable is
always evaluated in composable scope, which is what makes stringResource legal
there. androidx calls other than Text are left alone, so an animation's
`label = "chat-status"` is never mistaken for words on the screen.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalogs  # noqa: E402

SOURCES = catalogs.REPO / "Android" / "app" / "src" / "main" / "java"

_TEXT_CALL = re.compile(r"(?<![\w.])Text\(\s*(?=\")")
_CONTENT_DESCRIPTION = re.compile(r"(?<![\w.])contentDescription\s*=\s*(?=\")")
_ICON_CALL = re.compile(r"(?<![\w.])(?:Icon|Image|AsyncImage)\(")
_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", '"': '"', "'": "'", "\\": "\\", "$": "$"}

# aapt2 refuses a Java keyword as a resource name, and Kotlin would need backticks for its own.
_KEYWORDS = set("""
abstract as assert boolean break byte case catch char class const continue default do double else enum
extends false final finally float for fun goto if implements import in instanceof int interface is long
native new null object package private protected public return short static strictfp super switch
synchronized this throw throws transient true try typeof val var void volatile when while
""".split())


# ── Kotlin lexing: just enough to find string literals and step over the rest ─

def read_literal(src: str, i: int) -> tuple[list[tuple[str, str]], int] | None:
    """Parse the regular string literal opening at src[i] into ("text", …) and
    ("expr", …) segments. None for a raw string or an unterminated literal."""
    if src.startswith('"""', i):
        return None
    segments: list[tuple[str, str]] = []
    buf: list[str] = []

    def flush():
        if buf:
            segments.append(("text", "".join(buf)))
            buf.clear()

    i += 1
    while i < len(src):
        ch = src[i]
        if ch == "\\":
            nxt = src[i + 1]
            if nxt == "u":
                buf.append(chr(int(src[i + 2:i + 6], 16)))
                i += 6
            else:
                buf.append(_ESCAPES.get(nxt, nxt))
                i += 2
        elif ch == '"':
            flush()
            return segments, i + 1
        elif ch == "\n":
            return None
        elif ch == "$" and src.startswith("${", i):
            end = _skip_braces(src, i + 1)
            flush()
            segments.append(("expr", src[i + 2:end - 1].strip()))
            i = end
        elif ch == "$" and (name := re.match(r"[A-Za-z_]\w*", src[i + 1:i + 80])):
            flush()
            segments.append(("expr", name.group(0)))
            i += 1 + len(name.group(0))
        else:
            buf.append(ch)
            i += 1
    return None


def _skip_string(src: str, i: int) -> int:
    if src.startswith('"""', i):
        end = src.find('"""', i + 3)
        return len(src) if end < 0 else end + 3
    parsed = read_literal(src, i)
    if parsed is None:
        end = src.find("\n", i)
        return len(src) if end < 0 else end
    return parsed[1]


def _skip_braces(src: str, i: int) -> int:
    """Index just past the `}` matching the `{` at src[i]."""
    depth = 0
    while i < len(src):
        ch = src[i]
        if ch == '"':
            i = _skip_string(src, i)
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return i


def _skip_char(src: str, i: int) -> int:
    j = i + 1
    if j < len(src) and src[j] == "\\":
        j += 6 if src[j + 1:j + 2] == "u" else 2
    else:
        j += 1
    return j + 1 if src[j:j + 1] == "'" else i + 1


# ── what a literal becomes ───────────────────────────────────────────────────

def android_format(segments: list[tuple[str, str]]) -> tuple[str, list[str]]:
    """(format string, argument expressions). `%` is doubled only when there
    are arguments: a string read without format arguments is returned raw."""
    exprs = [value for kind, value in segments if kind == "expr"]
    parts, n = [], 0
    for kind, value in segments:
        if kind == "text":
            parts.append(value.replace("%", "%%") if exprs else value)
        else:
            n += 1
            parts.append(f"%{n}$s")
    return "".join(parts), exprs


def translatable(segments: list[tuple[str, str]]) -> bool:
    text = "".join(value for kind, value in segments if kind == "text")
    if "://" in text or re.search(r"\S+@\S+\.\w", text):
        return False
    return any(not word.isupper() for word in catalogs._HAS_WORDS.findall(text))


def resource_name(text: str, taken: dict[str, str]) -> str:
    """A name for `text`: the same English always gets the same name."""
    for name, existing in taken.items():
        if existing == text:
            return name
    words = re.findall(r"[a-z0-9]+", re.sub(r"%\d+\$s|%%", " ", text).lower())
    slug = ""
    for word in words:
        if len(slug) + len(word) + 1 > 40:
            break
        slug = f"{slug}_{word}" if slug else word
    if not slug or not slug[0].isalpha():
        slug = f"text_{slug}" if slug else "text"
    if slug in _KEYWORDS:
        slug += "_label"
    name, n = slug, 2
    while name in taken:
        name, n = f"{slug}_{n}", n + 1
    return name


# ── the rewrite ──────────────────────────────────────────────────────────────

def _inside_icon(src: str, at: int) -> bool:
    window = src[max(0, at - 400):at]
    calls = list(_ICON_CALL.finditer(window))
    if not calls:
        return False
    between = re.sub(r'"(?:[^"\\\n]|\\.)*"', '""', window[calls[-1].end():])
    return between.count("(") - between.count(")") >= 0


def rewrite(src: str, taken: dict[str, str], report: dict) -> str:
    out, i, last = [], 0, 0
    while i < len(src):
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = len(src) if end < 0 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = len(src) if end < 0 else end + 2
            continue
        if src[i] == "'":
            i = _skip_char(src, i)
            continue
        if src[i] == '"':
            i = _skip_string(src, i)
            continue

        match = _TEXT_CALL.match(src, i) or _CONTENT_DESCRIPTION.match(src, i)
        if not match:
            i += 1
            continue
        quote = match.end()
        parsed = read_literal(src, quote)
        if parsed is None:
            report["skipped: raw or multi-line"] += 1
            i = _skip_string(src, quote)
            continue
        segments, end = parsed
        follows = re.match(r"\s*(\S)", src[end:end + 200])
        if not follows or follows.group(1) not in ",)":
            report["skipped: not the whole argument"] += 1
        elif not translatable(segments):
            report["skipped: nothing to translate"] += 1
        elif match.re is _CONTENT_DESCRIPTION and not _inside_icon(src, match.start()):
            report["skipped: contentDescription outside Icon/Image"] += 1
        else:
            text, exprs = android_format(segments)
            name = resource_name(text, taken)
            taken.setdefault(name, text)
            call = ", ".join([f"R.string.{name}", *exprs])
            out.append(src[last:quote])
            out.append(f"stringResource({call})")
            last = end
            report["converted"] += 1
        i = end
    out.append(src[last:])
    return "".join(out)


# ── pass 2: text handed to a composable as an argument ───────────────────────

_TEXT_PARAM = re.compile(r"label|title|subtitle|message|placeholder|text|description|hint|header|heading|"
                         r"caption|tooltip|confirmText|dismissText|actionLabel|emptyText")
_COMPOSABLE_DECL = re.compile(r"@Composable\s+(?:(?:private|internal|public)\s+)?fun\s+([A-Z]\w*)\s*\(")
_CALL = re.compile(r"(?<![\w.])([A-Z]\w*)\s*\(")
_DEFAULT_TEXT = re.compile(r"(\w+)\s*:\s*String\??\s*=\s*(?=\")")


def _code_mask(src: str) -> bytearray:
    """1 where src is code; 0 inside strings, character literals and comments."""
    mask = bytearray(b"\x01") * len(src)
    i = 0
    while i < len(src):
        if src.startswith("//", i):
            end = src.find("\n", i)
            end = len(src) if end < 0 else end
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            end = len(src) if end < 0 else end + 2
        elif src[i] == '"':
            end = _skip_string(src, i)
        elif src[i] == "'":
            end = _skip_char(src, i)
        else:
            i += 1
            continue
        mask[i:end] = b"\x00" * (end - i)
        i = end
    return mask


def split_top_level(src: str, open_at: int) -> tuple[list[tuple[int, int]], int]:
    """Spans of the comma-separated items inside the bracket at src[open_at], and
    the index just past its closing bracket. Strings, chars and comments are skipped."""
    depth, i, start, spans = 0, open_at + 1, open_at + 1, []
    while i < len(src):
        ch = src[i]
        if ch == '"':
            i = _skip_string(src, i)
            continue
        if ch == "'":
            i = _skip_char(src, i)
            continue
        if src.startswith("//", i):
            end = src.find("\n", i)
            i = len(src) if end < 0 else end
            continue
        if src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = len(src) if end < 0 else end + 2
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                if src[start:i].strip():
                    spans.append((start, i))
                return spans, i + 1
            depth -= 1
        elif ch == "," and depth == 0:
            spans.append((start, i))
            start = i + 1
        i += 1
    return spans, i


def _parameters(src: str, open_at: int) -> list[tuple[str, str]]:
    params = []
    for start, end in split_top_level(src, open_at)[0]:
        part = re.sub(r"@\w+(?:\([^)]*\))?\s*", "", src[start:end]).strip()
        match = re.match(r"(?:vararg\s+)?(\w+)\s*:\s*([^=]+?)\s*(?:=.*)?$", part, re.S)
        params.append((match.group(1), match.group(2).strip()) if match else ("", ""))
    return params


def signatures(sources: dict[Path, str]) -> dict:
    """Our composables' parameters, {path: {name: params}}, plus {None: {name: params}}
    for names declared once in the app. A private StatCard exists in two files with
    different parameters, so a file's own declaration wins."""
    by_file: dict = {}
    seen: dict[str, list] = {}
    for path, src in sources.items():
        mask = _code_mask(src)
        local = by_file.setdefault(path, {})
        for match in _COMPOSABLE_DECL.finditer(src):
            if mask[match.start()]:
                local[match.group(1)] = params = _parameters(src, match.end() - 1)
                seen.setdefault(match.group(1), []).append(params)
    by_file[None] = {name: found[0] for name, found in seen.items() if len(found) == 1}
    return by_file


def rewrite_arguments(src: str, path: Path, sigs: dict, taken: dict[str, str], report) -> str:
    mask = _code_mask(src)
    edits: list[tuple[int, int, list]] = []

    def consider(at: int, limit: int, kind: str) -> None:
        parsed = read_literal(src, at)
        if parsed is None or src[parsed[1]:limit].strip():
            return
        if not translatable(parsed[0]):
            report["skipped: nothing to translate"] += 1
            return
        edits.append((at, parsed[1], parsed[0]))
        report[kind] += 1

    for match in _COMPOSABLE_DECL.finditer(src):
        if not mask[match.start()]:
            continue
        for start, end in split_top_level(src, match.end() - 1)[0]:
            default = _DEFAULT_TEXT.search(src, start, end)
            if default and _TEXT_PARAM.fullmatch(default.group(1)):
                consider(default.end(), end, "converted: default argument")

    for match in _CALL.finditer(src):
        name = match.group(1)
        if not mask[match.start()] or src[max(0, match.start() - 4):match.start()] == "fun ":
            continue
        params = sigs.get(path, {}).get(name) or sigs.get(None, {}).get(name)
        if name != "Text" and not params:
            continue
        types = dict(params or [])
        position = 0
        for start, end in split_top_level(src, match.end() - 1)[0]:
            arg = src[start:end]
            named = re.match(r"\s*(\w+)\s*=(?!=)\s*", arg)
            if named:
                param, at = named.group(1), start + named.end()
            else:
                param = params[position][0] if params and position < len(params) else ""
                at = start + len(arg) - len(arg.lstrip())
                position += 1
            if src[at:at + 1] != '"':
                continue
            if name == "Text":
                # Text("…") is pass 1's; only the named form is left for this one.
                if named and param == "text":
                    consider(at, end, "converted: named argument")
            elif _TEXT_PARAM.fullmatch(param) and types.get(param) in ("String", "String?"):
                consider(at, end, "converted: named argument" if named else "converted: positional argument")

    out = src
    for at, end, segments in sorted(edits, reverse=True):
        text, exprs = android_format(segments)
        name = resource_name(text, taken)
        taken.setdefault(name, text)
        out = out[:at] + f"stringResource({', '.join([f'R.string.{name}', *exprs])})" + out[end:]
    return out


# ── pass 3: a literal that is one operand of the text argument ───────────────
#
# `Text(if (busy) "Signing…" else "Sign off on this session")` and
# `Text(card.emptyReason ?: "Nothing recorded.")` — the argument is an
# expression, so pass 1 skipped it. Each worded literal that is a whole BRANCH
# converts; a literal the expression tests stays exactly as it is, because
# `status == "active"` compares against data, and translating it would silently
# never match (CLAUDE.md §3aw).

# Inside an argument a branch follows `else`, `?:` or the `)` closing an if's
# condition. After `(`, `,` or `=` a literal is an argument to a NESTED call —
# `Text(labelFor("potassium"))` — and may be a lookup key, so it stays.
_BEFORE_OPERAND = re.compile(r"(?:\belse|\?:|\))\s*$")
_AFTER_OPERAND = re.compile(r"\s*(?:\belse\b|\)|,|$)")


def rewrite_operands(src: str, path: Path, sigs: dict, taken: dict[str, str], report) -> str:
    mask = _code_mask(src)
    edits: list[tuple[int, int, list]] = []

    def scan(start: int, end: int) -> None:
        i = start
        while i < end:
            if src[i] != '"' or src.startswith('"""', i):
                i += 1
                continue
            parsed = read_literal(src, i)
            if parsed is None:
                i += 1
                continue
            segments, stop = parsed
            before, after = src[start:i], src[stop:end]
            whole = not before.strip() and not after.strip()   # pass 1 / pass 2 territory
            if (not whole and _BEFORE_OPERAND.search(before) and _AFTER_OPERAND.match(after)
                    and not re.search(r"(==|!=|\bin|\bis)\s*$", before) and not re.match(r"\s*(==|!=|->|\.)", after)
                    and translatable(segments)):
                edits.append((i, stop, segments))
                report["converted: operand"] += 1
            i = stop

    for match in _CALL.finditer(src):
        name = match.group(1)
        if not mask[match.start()] or src[max(0, match.start() - 4):match.start()] == "fun ":
            continue
        params = sigs.get(path, {}).get(name) or sigs.get(None, {}).get(name)
        if name != "Text" and not params:
            continue
        types = dict(params or [])
        position = 0
        for start, end in split_top_level(src, match.end() - 1)[0]:
            arg = src[start:end]
            named = re.match(r"\s*(\w+)\s*=(?!=)\s*", arg)
            if named:
                param, body = named.group(1), start + named.end()
            else:
                param = params[position][0] if params and position < len(params) else ("text" if name == "Text" and position == 0 else "")
                body = start
                position += 1
            if name == "Text" and param != "text":
                continue
            if name != "Text" and not (_TEXT_PARAM.fullmatch(param) and types.get(param) in ("String", "String?")):
                continue
            scan(body, end)

    out = src
    for at, end, segments in sorted(set((a, b, tuple(s)) for a, b, s in edits), reverse=True):
        text, exprs = android_format(list(segments))
        name = resource_name(text, taken)
        taken.setdefault(name, text)
        out = out[:at] + f"stringResource({', '.join([f'R.string.{name}', *exprs])})" + out[end:]
    return out


def convert(src: str, path: Path, sigs: dict, taken: dict[str, str], report) -> str:
    """All passes: Text and Icon literals, text handed to our composables, then
    literals that are one branch of such an argument."""
    out = rewrite_arguments(rewrite(src, taken, report), path, sigs, taken, report)
    return rewrite_operands(out, path, sigs, taken, report)


def ensure_imports(src: str) -> str:
    wanted = ["import androidx.compose.ui.res.stringResource", "import com.alafia.android.R"]
    missing = [line for line in wanted if not re.search(rf"^{re.escape(line)}$", src, re.M)]
    if not missing:
        return src
    imports = list(re.finditer(r"^import .*$", src, re.M))
    at = imports[-1].end() if imports else re.search(r"^package .*$", src, re.M).end()
    return src[:at] + "\n" + "\n".join(missing) + src[at:]


def append_strings(new: dict[str, str]) -> None:
    path = catalogs.android_path(catalogs.SOURCE_LANGUAGE)
    text = path.read_text(encoding="utf-8")
    block = ["", "    <!-- Screens. Extracted from Compose by scripts/i18n/android_extract.py. -->"]
    block += [f'    <string name="{name}">{catalogs.android_escape(value)}</string>' for name, value in new.items()]
    at = text.rindex("</resources>")
    path.write_text(text[:at].rstrip() + "\n" + "\n".join(block) + "\n" + text[at:], encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="rewrite the sources and strings.xml")
    args = parser.parse_args(argv)

    existing = catalogs.read_android(catalogs.SOURCE_LANGUAGE)
    taken = dict(existing)
    report = Counter()
    sources = {path: path.read_text(encoding="utf-8") for path in sorted(SOURCES.rglob("*.kt"))}
    sigs = signatures(sources)
    changed = {}
    for path, before in sources.items():
        after = convert(before, path, sigs, taken, report)
        if after != before:
            changed[path] = ensure_imports(after)

    new = {name: text for name, text in taken.items() if name not in existing}
    print(f"files changed: {len(changed)}   new strings: {len(new)}")
    for key, count in report.items():
        print(f"  {key}: {count}")
    for name, text in list(new.items())[:25]:
        print(f"  {name} = {text!r}")

    if args.apply:
        for path, text in changed.items():
            path.write_text(text, encoding="utf-8")
        append_strings(new)
        print("applied — now build: cd Android && ./gradlew :app:assembleDebug")
    return 0


if __name__ == "__main__":
    sys.exit(main())
