"""Fill ALAFIA's UI catalogs in every product language with AI; flag every result for review.

Runs in Docker, through ALAFIA's own provider chain (hosted first, Ollama last —
the same order as everything else). UI strings carry no patient data.

    docker run --rm --env-file WEB/backend/.env -v "$PWD":/repo -w /repo \
        -e PYTHONPATH=/repo/ML/src web-backend-test \
        python scripts/i18n/translate_catalogs.py --platform web [--languages yo,ig] [--dry-run]

iOS goes through Xcode on the host, since only Xcode reads and writes String
Catalogs:

    cd IOS && xcodebuild -exportLocalizations -project ALAFIA.xcodeproj \
        -localizationPath /tmp/alafia-l10n -exportLanguage en
    cp "/tmp/alafia-l10n/en.xcloc/Localized Contents/en.xliff" i18n/ios/en.xliff
    ... translate_catalogs.py --platform ios ...                  (the command above)
    cd IOS && xcodebuild -importLocalizations -project ALAFIA.xcodeproj \
        -localizationPath ../i18n/ios/yo.xliff

Only entries that are missing, or whose English changed since they were
translated, are sent. A translation that breaks a placeholder is refused and the
entry stays untranslated — the app shows English there, which is honest, rather
than a broken or crashing string. Every accepted translation is written to
i18n/review/<platform>/<lang>.json with status "machine" until a person who
reads the language marks it "reviewed".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import catalogs  # noqa: E402

BATCH_SIZE = 40
RETRY_BATCH_SIZES = (10, 1)

_SYSTEM = """\
You translate user-interface text for ALAFIA, a personal health app used by patients,
many of them managing kidney disease or dialysis, into {language}.

You receive a JSON object of id -> English text. Return ONLY a JSON object with the
SAME ids, each value translated. Rules:
- Keep every placeholder exactly as written: {{{{name}}}}, %1$s, %d, %@, %lld, %%.
- Never translate drug names, lab test names, units (mg, mmol/L, kg, mL), numbers, or
  the name ALAFIA.
- Keep interface text as short as the English: these are buttons, labels and titles.
- Use the standard written form of {language}, including its tone marks and diacritics.
- Plain, respectful language a patient understands. Medical meaning must not change.
- Where a term has no established {language} equivalent, keep the English term.
"""


def _parse_json(text: str) -> dict:
    from alafia_model.capabilities.vision import VisionCapability

    parsed = VisionCapability._parse_json(text)
    return parsed if isinstance(parsed, dict) else {}


_NUMBERED_LINE = re.compile(r'^\s*"(\d+)"\s*:\s*"(.*)"\s*,?\s*$')


def _parse_numbered(raw: str, expected: set[str]) -> dict[str, str]:
    """The reply as {id: translation}.

    JSON first. A reply can be JSON in every respect but one: the model quotes a
    term with a plain quote mark — “kidney” came back as "kidney", and German
    „Freigeben" closes with one — so the whole reply fails to parse and the
    string is lost on every retry, in every language. The model writes one entry
    per line, so a line holding `"<id>": "<text>"` is read as that entry, the
    text running from the first quote to the LAST one on the line.
    """
    parsed = _parse_json(raw)
    if expected <= set(parsed):
        return parsed
    recovered: dict[str, str] = {}
    for line in raw.splitlines():
        match = _NUMBERED_LINE.match(line)
        if not match or match.group(1) not in expected:
            continue
        body = match.group(2).replace('\\"', '"').replace('"', '\\"')
        try:
            recovered[match.group(1)] = json.loads(f'"{body}"')
        except json.JSONDecodeError:
            recovered[match.group(1)] = match.group(2)
    return {**recovered, **{n: text for n, text in parsed.items() if n in expected}}


async def _translate_batch(llm, language: str, batch: dict[str, str]) -> tuple[dict, str, str]:
    """Returns (translations keyed by OUR keys, raw reply text, which provider answered).

    The model sees short numeric ids, never our keys. Given the real keys it
    tidied their typography as it echoed them back — "Couldn’t" became
    "Couldn't", “%@” became "%@" — so the key no longer matched, and a straight
    quote inside a JSON key made the whole reply unparseable: every string in
    the batch was lost for one quote mark.
    """
    ids = {str(n): key for n, key in enumerate(batch, start=1)}
    numbered = {n: batch[key] for n, key in ids.items()}
    result = await llm.infer({
        "task": "chat",
        "temperature": 0.1,
        "max_tokens": 8000,
        "json_mode": True,
        "messages": [
            {"role": "system", "content": _SYSTEM.format(language=language)},
            {"role": "user", "content": json.dumps(numbered, ensure_ascii=False)},
        ],
    })
    if not result.success:
        raise RuntimeError(result.error or "the provider chain returned no answer")
    raw = (result.data or {}).get("text", "")
    parsed = _parse_numbered(raw, set(ids))
    translations = {ids[n]: value for n, value in parsed.items() if n in ids}
    return translations, raw, result.source or "unknown provider"


async def translate_language(llm, platform: str, lang: str, *, dry_run: bool, limit: int | None = None) -> dict:
    source = catalogs.READERS[platform](catalogs.SOURCE_LANGUAGE)
    target = catalogs.READERS[platform](lang)
    ledger = catalogs.read_review(platform, lang)
    todo = catalogs.needs_translation(source, target, ledger)
    if limit is not None:
        todo = dict(list(todo.items())[:limit])
    report = {"language": lang, "to_translate": len(todo), "translated": 0, "refused": {}}
    if dry_run or not todo:
        return report

    async def run(entries: dict[str, str], batch_size: int) -> dict[str, str]:
        """Translate in batches; returns the entries no translation came back for."""
        unanswered: dict[str, str] = {}
        items = list(entries.items())
        for start in range(0, len(items), batch_size):
            batch = dict(items[start:start + batch_size])
            answer, raw, source = await _translate_batch(llm, catalogs.LANGUAGES[lang], batch)
            missing = [k for k in batch if not isinstance(answer.get(k), str) or not answer[k].strip()]
            if missing:
                # Say so, and show what came back: a reply that silently lacks keys
                # looks like a success, and "0 keys" alone does not say whether the
                # model refused, answered in prose, or was cut off.
                print(f"    {platform}/{lang}: a batch of {len(batch)} came back without {len(missing)} "
                      f"(reply had {len(answer)} keys, from {source}, {len(raw)} chars): "
                      f"{raw[:300]!r}")
            for key, english in batch.items():
                if key in missing:
                    unanswered[key] = english
                    continue
                translation = answer[key]
                problem = catalogs.placeholder_problem(english, translation)
                if problem:
                    report["refused"][key] = problem
                    continue
                target[key] = translation.strip()
                ledger[key] = {"source": english, "translation": target[key], "status": "machine",
                               "translated_on": date.today().isoformat()}
                report["translated"] += 1
        return unanswered

    unanswered = await run(todo, BATCH_SIZE)
    # Retry in ever smaller batches, down to one string at a time, so a single
    # malformed reply can no longer take its neighbours down with it.
    for size in RETRY_BATCH_SIZES:
        if not unanswered:
            break
        unanswered = await run(unanswered, size)
    for key in unanswered:
        report["refused"][key] = "no translation returned after retries"

    catalogs.WRITERS[platform](lang, target, list(source))
    catalogs.write_review(platform, lang, ledger)
    return report


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Translate ALAFIA UI catalogs.")
    parser.add_argument("--platform", choices=catalogs.PLATFORMS, required=True)
    parser.add_argument("--languages", default="", help="comma-separated codes; default: every product language")
    parser.add_argument("--dry-run", action="store_true", help="count what would be translated; send nothing")
    parser.add_argument("--limit", type=int, default=None,
                        help="translate at most N entries per language — for a smoke run before the full catalog")
    args = parser.parse_args(argv)

    requested = [c.strip() for c in args.languages.split(",") if c.strip()] or list(catalogs.LANGUAGES)
    unknown = [c for c in requested if c not in catalogs.LANGUAGES]
    if unknown:
        print(f"unknown language code(s): {unknown}", file=sys.stderr)
        return 2
    targets = [c for c in requested if c != catalogs.SOURCE_LANGUAGE]

    llm = None
    if not args.dry_run:
        from alafia_model.capabilities.llm import LLMCapability
        llm = LLMCapability()

    failed = False
    for lang in targets:
        try:
            report = await translate_language(llm, args.platform, lang, dry_run=args.dry_run, limit=args.limit)
        except RuntimeError as exc:
            print(f"{lang}: FAILED — {exc}", file=sys.stderr)
            failed = True
            continue
        refused = report["refused"]
        print(f"{args.platform}/{lang}: {report['to_translate']} to translate, "
              f"{report['translated']} translated, {len(refused)} refused")
        for key, why in list(refused.items())[:10]:
            print(f"    refused {key}: {why}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
