"""ICD-11 MMS catalog — the complete WHO linearization, searchable offline.

The data is **generated, never typed**: `app/data/icd11_mms.tsv.gz` comes from
WHO's published Simple Tabulation of the Mortality and Morbidity Statistics
linearization (see `scripts/build_icd11_catalog.py`). Hand-writing ICD codes is
how a plausible-looking wrong code reaches a patient record — G6PD deficiency is
`3A10.00`, which is not what anyone guesses.

Why the whole catalog and not a curated subset: a shortlist silently lacks
whatever the patient actually has, which is the same failure as reading the
wrong conditions table (CLAUDE.md §3aa). All 35k codes gzip to 370 KB.

Three things the WHO file does not give us, all handled here:

- **Word order.** Titles are formal ("Type 2 diabetes mellitus"), so a substring
  match on "diabetes mellitus type 2" finds nothing. Matching is token-wise.
- **Lay terms and abbreviations.** "ESRD", "G6PD" and "heart attack" appear in
  no title. `ICD11_ALIASES` maps them to verified codes.
- **British spelling.** WHO writes "haemodialysis", "tumour", "anaemia",
  "oesophagus" — 867 titles carry a spelling a US patient will not type, and
  "hemodialysis" matched nothing at all before `_fold()` existed. Both the index
  and the query are folded, so either spelling finds the same code.

The official API (id.who.int) needs OAuth client credentials this deployment
does not have, and a type-ahead should not depend on an outbound call anyway.
"""

from __future__ import annotations

import gzip
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "icd11_mms.tsv.gz"

# ICD-11 stem codes: two alphanumerics, two alphanumerics, then optional
# .N / .NN extensions — e.g. 1A00, GB61.5, 3A10.00. Chapter 'X' extension
# codes and the 'V' supplementary section share the shape.
ICD11_CODE_RE = re.compile(r"^[0-9A-Z]{2}[0-9A-Z]{2}(\.[0-9A-Z]{1,2})?$", re.IGNORECASE)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Chapters that are not patient diagnoses. WHO is explicit that extension codes
# (X) never stand alone, the functioning supplement (V) scores ability rather
# than disease, and chapter 26 is the Traditional Medicine module. Left in the
# default results they crowd out the real answer: searching "kidney" used to
# return "Kidney" (XA6KU8) and "Kidney meridian pattern (TM1)" above chronic
# kidney disease.
_NON_DIAGNOSTIC_CHAPTERS = frozenset({"X", "V", "26"})

# Chapters that ARE codeable but rarely what someone entering a chronic
# condition means; ranked after a real diagnosis of equal match quality.
_CHAPTER_PENALTY = {
    "21": 1,  # symptoms, signs and clinical findings
    "24": 1,  # factors influencing health status (e.g. "Kidney donor")
    "23": 2,  # external causes of morbidity
    "25": 2,  # codes for special purposes
}

# British → American spelling folds, applied to index and query alike.
# Ordered longest-first; each is applied to whole tokens only.
_SPELLING_FOLDS = (
    ("aemia", "emia"),      # anaemia, leukaemia
    ("aemo", "emo"),        # haemodialysis, haemoglobin
    ("haem", "hem"),        # haemorrhage
    ("oesoph", "esoph"),    # oesophagus
    ("oedema", "edema"),
    ("rrhoea", "rrhea"),    # diarrhoea, gonorrhoea
    ("paed", "ped"),        # paediatric
    ("coel", "cel"),        # coeliac
    ("gynae", "gyne"),
    ("orthopae", "orthope"),
    ("anaest", "anest"),
    ("our", "or"),          # tumour, behaviour, colour
    ("ae", "e"),
    ("oe", "e"),
)


def _code_depth(code: str) -> int:
    """How deep in the hierarchy a code sits — GB61 is 0, GB61.5 is 1.

    Stands in for prominence: a top-level category is far more likely to be
    what someone means than a sub-sub-classification of it.
    """
    _, _, tail = code.partition(".")
    return len(tail)


def _fold(token: str) -> str:
    """Normalise a single lowercase token to a spelling-neutral form."""
    for british, american in _SPELLING_FOLDS:
        token = token.replace(british, american)
    return token


@dataclass(frozen=True)
class ICD11Code:
    """A single ICD-11 MMS entity."""

    code: str
    title: str
    chapter: str
    chapter_title: str
    is_leaf: bool
    is_residual: bool
    kind: str


def _tokenize(text: str) -> List[str]:
    """Lowercase word tokens, spelling-folded so haemo/hemo collapse."""
    return [_fold(t) for t in _TOKEN_RE.findall(text.lower())]


class _Catalog:
    """Parsed catalog plus the inverted index that keeps search cheap."""

    def __init__(self) -> None:
        self.codes: Dict[str, ICD11Code] = {}
        self.chapters: Dict[str, str] = {}
        self.version: str = "unknown"
        self._order: List[ICD11Code] = []
        self._by_token: Dict[str, List[int]] = {}

    def load(self) -> "_Catalog":
        if not _DATA_FILE.exists():  # pragma: no cover - packaging error
            raise FileNotFoundError(
                f"ICD-11 catalog missing at {_DATA_FILE}. "
                "Regenerate with scripts/build_icd11_catalog.py."
            )

        with gzip.open(_DATA_FILE, "rt", encoding="utf-8") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line:
                    continue
                if line.startswith("#chapter\t"):
                    _, num, title = line.split("\t", 2)
                    self.chapters[num] = title
                    continue
                if line.startswith("#"):
                    if self.version == "unknown":
                        self.version = line.lstrip("# ").strip()
                    continue
                parts = line.split("\t")
                if len(parts) < 6 or parts[0] == "code":
                    continue
                code, title, chapter, is_leaf, is_residual, kind = parts[:6]
                entry = ICD11Code(
                    code=code,
                    title=title,
                    chapter=chapter,
                    chapter_title=self.chapters.get(chapter, ""),
                    is_leaf=is_leaf == "1",
                    is_residual=is_residual == "1",
                    kind=kind,
                )
                self.codes[code] = entry
                self._order.append(entry)

        # chapter_title is resolved after the fact for any row that appeared
        # before its chapter header (it never does today, but the file format
        # does not promise ordering).
        for idx, entry in enumerate(self._order):
            if not entry.chapter_title and entry.chapter in self.chapters:
                fixed = ICD11Code(
                    **{**entry.__dict__, "chapter_title": self.chapters[entry.chapter]}
                )
                self._order[idx] = fixed
                self.codes[entry.code] = fixed

        for idx, entry in enumerate(self._order):
            for token in set(_tokenize(entry.title)):
                self._by_token.setdefault(token, []).append(idx)

        return self

    def candidates(self, tokens: Iterable[str]) -> List[int]:
        """Row indices whose title contains every token (prefix-wise).

        Narrows 35k rows to a handful before any scoring happens. The rarest
        token is intersected first so the working set starts small.
        """
        postings: List[List[int]] = []
        for token in tokens:
            exact = self._by_token.get(token)
            if exact is not None:
                postings.append(exact)
                continue
            # Unfinished word in a type-ahead ("kidn"): fall back to a prefix
            # sweep over the token vocabulary.
            merged: set[int] = set()
            for vocab, rows in self._by_token.items():
                if vocab.startswith(token):
                    merged.update(rows)
            if not merged:
                return []
            postings.append(sorted(merged))

        if not postings:
            return []
        postings.sort(key=len)
        result = set(postings[0])
        for other in postings[1:]:
            result &= set(other)
            if not result:
                return []
        return sorted(result)

    def entry_at(self, idx: int) -> ICD11Code:
        return self._order[idx]

    def all_entries(self) -> List[ICD11Code]:
        return list(self._order)


@lru_cache(maxsize=1)
def _catalog() -> _Catalog:
    return _Catalog().load()


# ── Lay terms and abbreviations ───────────────────────────────────────
#
# None of these strings appear in an ICD-11 title, so without this map a
# patient searching what their doctor actually said gets nothing. Every code
# here is verified against the generated catalog by
# tests/test_icd11_catalog.py — add a term only with its code checked.
#
# Ordered most-specific first; the first code becomes the top hit.
ICD11_ALIASES: Dict[str, Tuple[str, ...]] = {
    # ── Renal — the app's primary domain (§3aa, §3ac) ──
    "esrd": ("GB61.5",),
    "eskd": ("GB61.5",),
    "end stage renal disease": ("GB61.5",),
    "end stage kidney disease": ("GB61.5",),
    "end-stage renal disease": ("GB61.5",),
    "kidney failure": ("GB61.5", "GB60"),
    "renal failure": ("GB61.5", "GB60"),
    "ckd": ("GB61", "GB61.5", "GB61.4", "GB61.3", "GB61.2"),
    "aki": ("GB60",),
    "acute kidney injury": ("GB60",),
    "dialysis": ("GB61.5",),
    # ── Blood disorders / inherited traits ──
    "g6pd": ("3A10.00",),
    "g6pd deficiency": ("3A10.00",),
    "glucose 6 phosphate dehydrogenase deficiency": ("3A10.00",),
    "favism": ("3A10.00",),
    "sickle cell": ("3A51.1", "3A51.2", "3A51.0"),
    "sickle cell anemia": ("3A51.1", "3A51.2"),
    "sickle cell anaemia": ("3A51.1", "3A51.2"),
    "sickle cell disease": ("3A51.1", "3A51.2"),
    "scd": ("3A51.1",),
    "thalassemia": ("3A50", "3A50.2", "3A50.0"),
    "anemia": ("3A00",),
    # ── Endocrine ──
    "t1d": ("5A10",),
    "t1dm": ("5A10",),
    "type 1 diabetes": ("5A10",),
    "t2d": ("5A11",),
    "t2dm": ("5A11",),
    "type 2 diabetes": ("5A11",),
    "diabetes": ("5A11", "5A10"),
    "underactive thyroid": ("5A00",),
    # ── Cardiovascular ──
    "heart attack": ("BA41",),
    "mi": ("BA41",),
    "myocardial infarction": ("BA41",),
    "high blood pressure": ("BA00",),
    "htn": ("BA00",),
    "hypertension": ("BA00",),
    "chf": ("BD10",),
    "congestive heart failure": ("BD10",),
    "heart failure": ("BD10", "BD1Z"),
    "afib": ("BC81.3",),
    "a fib": ("BC81.3",),
    "atrial fibrillation": ("BC81.3",),
    "stroke": ("8B20",),
    # ── Respiratory ──
    "copd": ("CA22",),
    "emphysema": ("CA22",),
    # ── Gastro ──
    "gerd": ("DA22",),
    "acid reflux": ("DA22",),
    "heartburn": ("DA22",),
    "ibd": ("DD70", "DD71"),
    "inflammatory bowel disease": ("DD70", "DD71"),
    "crohns": ("DD70",),
    "crohn's": ("DD70",),
    "uc": ("DD71",),
    "ulcerative colitis": ("DD71",),
    "ibs": ("DD91.0",),
    "irritable bowel syndrome": ("DD91.0",),
    # ── Cancers ──
    "breast cancer": ("2C6Z", "2C61.0", "2C61"),
    "prostate cancer": ("2C82",),
    "lung cancer": ("2C25",),
    "colon cancer": ("2B90",),
    "colorectal cancer": ("2B90", "2B92"),
    "bowel cancer": ("2B90", "2B92"),
    "rectal cancer": ("2B92",),
    # ── Autoimmune / other ──
    "lupus": ("4A40.0", "4A40"),
    "sle": ("4A40.0",),
    "hiv": ("1C62",),
    "aids": ("1C62",),
    # ── Musculoskeletal ──
    "arthritis": ("FA01", "FA00"),
    "gout": ("FA25",),
    # ── Bare organ words ──
    #
    # A one-word query cannot be ranked by structure alone: the WHO file
    # carries no prevalence or prominence signal, so "kidney" matches "Kidney
    # donor" and "Accessory kidney" exactly as well as chronic kidney disease.
    # Rather than invent a relevance heuristic that pretends otherwise, the
    # common intent is stated outright for the organs this app is about.
    "kidney": ("GB61", "GB61.5", "GB60"),
    "kidneys": ("GB61", "GB61.5", "GB60"),
    "renal": ("GB61", "GB61.5", "GB60"),
    "liver": ("DB99.0", "DB93.1", "DB92"),
    "heart": ("BD10", "BA41", "BA00"),
    "lung": ("CA22", "CA23", "2C25"),
    "lungs": ("CA22", "CA23", "2C25"),
    "thyroid": ("5A00", "5A02"),
    "bowel": ("DD91.0", "DD70", "DD71"),
}


@lru_cache(maxsize=1)
def _folded_aliases() -> Dict[str, Tuple[str, ...]]:
    """Alias keys under the same normalisation queries get.

    Without this, "crohn's" (which tokenises to "crohn s") and any key spelled
    the British way would never be reachable. Where two keys fold together the
    first one wins, and they map to the same codes by construction.
    """
    folded: Dict[str, Tuple[str, ...]] = {}
    for term, codes in ICD11_ALIASES.items():
        folded.setdefault(" ".join(_tokenize(term)), codes)
    return folded


# ── Public API ────────────────────────────────────────────────────────


def catalog_version() -> str:
    """The WHO release stamp the bundled catalog was built from."""
    return _catalog().version


def get_icd11_by_code(code: str) -> Optional[ICD11Code]:
    """Look up one code. Case-insensitive; codes are stored upper-case."""
    if not code:
        return None
    return _catalog().codes.get(code.strip().upper())


def is_valid_icd11_code(code: str) -> bool:
    """True when *code* is a real ICD-11 MMS code, not merely code-shaped."""
    return get_icd11_by_code(code) is not None


def list_chapters() -> List[Dict[str, str]]:
    """The 28 ICD-11 chapters, in WHO order."""
    cat = _catalog()
    return [{"chapter": num, "title": title} for num, title in sorted(cat.chapters.items())]


def search_icd11(
    query: str,
    chapter: Optional[str] = None,
    limit: int = 20,
    include_residual: bool = True,
    include_non_diagnostic: bool = False,
) -> List[ICD11Code]:
    """Rank ICD-11 codes for a free-text or code query.

    Ordering, best first: exact code, code prefix, alias hit, exact title,
    title starting with the query, all query tokens present as word prefixes,
    then remaining token matches. Within a tier, a real diagnosis outranks a
    symptom or health-status code, non-residual entries come before "other
    specified"/"unspecified" ones, then the shorter title.

    Extension, functioning-supplement and traditional-medicine chapters are
    omitted unless *include_non_diagnostic* is set — see
    `_NON_DIAGNOSTIC_CHAPTERS`. An explicit *chapter* filter always wins, so
    those chapters remain browsable when asked for by name.
    """
    raw = (query or "").strip()
    if not raw:
        return []

    cat = _catalog()
    scored: Dict[str, Tuple[int, int, int, int, str]] = {}

    def offer(entry: ICD11Code, tier: int, within: int = 0) -> None:
        if chapter and entry.chapter != chapter:
            return
        if (
            not include_non_diagnostic
            and chapter is None
            and entry.chapter in _NON_DIAGNOSTIC_CHAPTERS
        ):
            return
        if not include_residual and entry.is_residual:
            return
        # A residual ("...unspecified" / "other specified") drops a whole tier
        # rather than merely losing a tiebreak: searching "kidney" otherwise
        # led with "Kidney failure, unspecified" because that title happens to
        # start with the query, burying chronic kidney disease. An exact code
        # lookup (tier 0) is never demoted — asking for GB61.Z means GB61.Z.
        if entry.is_residual and tier > 0:
            tier += 1
        # A weaker chapter costs the same as a weaker match, so "Kidney donor"
        # (chapter 24) cannot outrank a real diagnosis just because its title
        # happens to start with the query.
        if tier > 0:
            tier += _CHAPTER_PENALTY.get(entry.chapter, 0)
        key = (
            tier,
            within,
            _code_depth(entry.code),
            len(entry.title),
            entry.code,
        )
        existing = scored.get(entry.code)
        if existing is None or key < existing:
            scored[entry.code] = key

    normalized = " ".join(_tokenize(raw))

    # 1. The query is a code, or the start of one.
    upper = raw.upper().replace(" ", "")
    if ICD11_CODE_RE.match(upper):
        exact = cat.codes.get(upper)
        if exact is not None:
            offer(exact, 0)
    if len(upper) >= 2 and re.fullmatch(r"[0-9A-Z.]+", upper):
        for entry in cat.all_entries():
            if entry.code.startswith(upper) and entry.code != upper:
                offer(entry, 1, 0 if not entry.is_residual else 1)

    # 2. Lay terms and abbreviations.
    aliases = _folded_aliases()
    for position, code in enumerate(aliases.get(normalized, ())):
        entry = cat.codes.get(code)
        if entry is not None:
            offer(entry, 2, position)

    # A type-ahead sees the query half-typed. "kidn" should already be pulling
    # the "kidney" aliases up rather than leading with "Kidney donor". Guarded
    # at 3 characters so a single letter does not drag in every alias.
    if normalized not in aliases and len(normalized) >= 3:
        for term, codes in aliases.items():
            if not term.startswith(normalized):
                continue
            for position, code in enumerate(codes):
                entry = cat.codes.get(code)
                if entry is not None:
                    offer(entry, 3, position)

    # 3. Title matching, token-wise so word order does not matter.
    tokens = _tokenize(raw)
    if tokens:
        for idx in cat.candidates(tokens):
            entry = cat.entry_at(idx)
            title_tokens = _tokenize(entry.title)
            # Compare folded-to-folded. Comparing the raw title against the
            # folded query silently never matched a British-spelled title, so
            # "anemia" could not exact-match "Iron deficiency anaemia".
            title_norm = " ".join(title_tokens)
            if title_norm == normalized:
                tier = 3
            elif title_norm.startswith(normalized):
                tier = 4
            elif all(
                any(t.startswith(tok) for t in title_tokens) for tok in tokens
            ):
                tier = 5
            else:
                tier = 6
            offer(entry, tier)

    ranked = sorted(scored.items(), key=lambda kv: kv[1])
    return [cat.codes[code] for code, _ in ranked[:limit]]
