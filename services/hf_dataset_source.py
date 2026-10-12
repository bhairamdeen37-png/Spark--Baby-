"""
Hugging Face datasets as an online question source (JEE / NEET ...), via the official
Dataset Viewer API:  https://huggingface.co/docs/dataset-viewer/en/quick_start
    GET https://datasets-server.huggingface.co/splits?dataset=<id>
    GET https://datasets-server.huggingface.co/rows?dataset=<id>&config=<c>&split=<s>&offset=<n>&length=<=100>

Different datasets use different column names, so rows are mapped with a tolerant column detector
(question / options / answer / subject / explanation). Rows that are not clean 4-option single-answer
MCQs (numerical, image-based, multi-correct, no answer key) are skipped.
Run tools/check_hf_dataset.py once (with internet) to see what each dataset actually yields.

Questions from here are marked trusted=False: quiz_bank re-solves them with a second AI model
(QUIZ_VERIFY) before use, because community datasets can contain wrong answer keys.
"""
import asyncio
import json
import logging
import random
import re

import aiohttp

from config import HF_ENABLED, HF_TOKEN, HF_PAGES, HF_DATASETS_OVERRIDE
from services.math_format import plain_math

log = logging.getLogger("spark_baby.hf")

API = "https://datasets-server.huggingface.co"
PAGE = 100   # the viewer API allows at most 100 rows per request

# exam key -> dataset ids (override with HF_DATASETS_JEE / HF_DATASETS_NEET / ... env vars)
DEFAULT_DATASETS = {
    "jee": ["eQOURSE/jee-main-questions"],
    "neet": ["Kshitij-PES/NEET_Dataset", "catchshubham/neet-dataset"],
}

_Q_KEYS = ("question", "question_text", "query", "problem", "prompt", "stem", "text")
_OPT_LIST_KEYS = ("options", "choices", "answers", "option_list", "answer_choices")
_OPT_COLS = (("option_a", "option_b", "option_c", "option_d"), ("a", "b", "c", "d"),
             ("opa", "opb", "opc", "opd"), ("option1", "option2", "option3", "option4"),
             ("option_1", "option_2", "option_3", "option_4"), ("choice_a", "choice_b", "choice_c", "choice_d"),
             ("optiona", "optionb", "optionc", "optiond"), ("op1", "op2", "op3", "op4"))
_ANS_KEYS = ("answer", "correct_answer", "correct_option", "correct_index", "correct", "cop", "ans",
             "answer_key", "correct_choice", "answer_idx", "label", "key")
_SUBJ_KEYS = ("subject", "section", "category")
_EXP_KEYS = ("explanation", "solution", "rationale", "exp")
_NEEDS_PICTURE = re.compile(r"\b(figure|fig\.|diagram|image|picture|graph shown|shown below|given below in the figure)\b", re.I)

_SUBJECTS = {"physics": "physics", "phy": "physics", "chemistry": "chemistry", "chem": "chemistry",
             "maths": "maths", "math": "maths", "mathematics": "maths",
             "biology": "biology", "bio": "biology", "botany": "biology", "zoology": "biology"}


def datasets_for(exam):
    ids = HF_DATASETS_OVERRIDE.get(exam)
    return ids if ids is not None else DEFAULT_DATASETS.get(exam, [])


def enabled_for(exam) -> bool:
    return HF_ENABLED and bool(datasets_for(exam))


def _lower_keys(row):
    return {str(k).strip().lower().replace(" ", "_"): v for k, v in row.items()}


def _first(row, keys):
    for k in keys:
        v = row.get(k)
        if v is not None and v != "":
            return v
    return None


def _clean(s):
    return plain_math(" ".join(str(s).split()))


def _options(row):
    for k in _OPT_LIST_KEYS:
        v = row.get(k)
        if isinstance(v, str) and v.strip().startswith(("[", "{")):
            try:
                v = json.loads(v)
            except ValueError:
                continue
        if isinstance(v, dict):
            v = [v[x] for x in sorted(v)]
        if isinstance(v, (list, tuple)) and len(v) == 4:
            out = [(o.get("text") if isinstance(o, dict) else o) for o in v]
            if all(isinstance(o, (str, int, float)) for o in out):
                return [str(o) for o in out]
    for cols in _OPT_COLS:
        if all(c in row and row[c] not in (None, "") for c in cols):
            return [str(row[c]) for c in cols]
    return None


def detect_zero_based(rows) -> bool:
    """Integer answer keys: 0-3 (zero based) or 1-4 (one based)? If any row has 0, it is zero based."""
    ints = set()
    for r in rows:
        v = _first(_lower_keys(r), _ANS_KEYS)
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)) and float(v).is_integer():
            ints.add(int(v))
        elif isinstance(v, str) and v.strip().isdigit():
            ints.add(int(v.strip()))
    return 0 in ints


def _answer_index(v, options, zero_based):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        if not float(v).is_integer():
            return None
        i = int(v) if zero_based else int(v) - 1
        return i if 0 <= i < 4 else None
    s = str(v).strip()
    if s.isdigit():
        return _answer_index(int(s), options, zero_based)
    t = re.sub(r"^(option|ans(wer)?)\s*[:\-]?\s*", "", s, flags=re.I).strip(" ().[]")
    if len(t) == 1 and t.upper() in "ABCD":
        return "ABCD".index(t.upper())
    for i, o in enumerate(options):
        if o.strip().lower() == s.lower():
            return i
    return None          # "A, C", numerical values, free text ... -> not a clean single-answer MCQ


def canon_subject(v):
    return _SUBJECTS.get(str(v or "").strip().lower(), "")


def normalize_row(row, zero_based=False):
    """Raw dataset row -> question dict (trusted=False) or None when unusable."""
    r = _lower_keys(row)
    q = _first(r, _Q_KEYS)
    opts = _options(r)
    if not isinstance(q, str) or not q.strip() or not opts or _NEEDS_PICTURE.search(q):
        return None
    ci = _answer_index(_first(r, _ANS_KEYS), opts, zero_based)
    if ci is None:
        return None
    opts = [_clean(o) for o in opts]
    if any(not o for o in opts) or len({o.lower() for o in opts}) < 4:
        return None
    exp = _first(r, _EXP_KEYS)
    return {"question": _clean(q), "options": opts, "correct_index": ci,
            "explanation": _clean(exp) if isinstance(exp, str) else "",
            "subject": canon_subject(_first(r, _SUBJ_KEYS)), "level": "", "trusted": False}


def normalize_rows(rows):
    zb = detect_zero_based(rows)
    return [n for n in (normalize_row(r, zb) for r in rows) if n]


async def _get_json(session, path, params):
    headers = {"Authorization": f"Bearer {HF_TOKEN}"} if HF_TOKEN else {}
    async with session.get(f"{API}/{path}", params=params, headers=headers) as r:
        if r.status != 200:
            raise RuntimeError(f"HF {path} HTTP {r.status}")
        return await r.json(content_type=None)


async def fetch_rows(dataset, pages=None):
    """A random sample of raw rows (up to `pages` x 100) from one dataset, via the Dataset Viewer API."""
    pages = pages or HF_PAGES
    timeout = aiohttp.ClientTimeout(total=25)
    async with aiohttp.ClientSession(timeout=timeout) as s:
        splits = (await _get_json(s, "splits", {"dataset": dataset})).get("splits", [])
        if not splits:
            return []
        pick = next((x for x in splits if x.get("split") == "train"), splits[0])
        base = {"dataset": dataset, "config": pick["config"], "split": pick["split"], "length": PAGE}
        first = await _get_json(s, "rows", {**base, "offset": 0})
        total = int(first.get("num_rows_total") or 0)
        rows = [x["row"] for x in first.get("rows", [])]
        offsets = list(range(PAGE, max(total - PAGE, PAGE) + 1, PAGE))
        random.shuffle(offsets)
        extra = await asyncio.gather(*[_get_json(s, "rows", {**base, "offset": o}) for o in offsets[:pages - 1]],
                                     return_exceptions=True)
        for page in extra:
            if isinstance(page, dict):
                rows += [x["row"] for x in page.get("rows", [])]
    return rows


async def load(exam):
    """Usable MCQs for an exam from all its configured HF datasets (failures of one dataset are skipped)."""
    if not enabled_for(exam):
        return []
    out = []
    for ds in datasets_for(exam):
        try:
            qs = normalize_rows(await fetch_rows(ds))
            log.info(f"[hf] {ds}: {len(qs)} usable MCQs")
            out += qs
        except Exception as e:
            log.warning(f"[hf] {ds} failed: {e}")
    return out
