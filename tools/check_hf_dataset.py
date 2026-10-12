"""
Run this ONCE on your PC / Render shell (needs internet) to see how each Hugging Face dataset maps to quiz questions:
    python -m tools.check_hf_dataset                      # all default datasets
    python -m tools.check_hf_dataset user/dataset-name    # one dataset
Prints the raw columns, how many rows became usable MCQs, subjects found, and 2 sample questions.
If 'usable' is 0 or very low, the dataset has a different layout (or no answer key) — don't rely on it.
"""
import asyncio
import collections
import sys

from services import hf_dataset_source as hf


async def check(ds):
    print("=" * 70, f"\n{ds}")
    try:
        rows = await hf.fetch_rows(ds, pages=1)
    except Exception as e:
        print("  fetch failed:", e)
        return
    print(f"  sampled rows: {len(rows)}")
    if not rows:
        return
    print("  columns:", list(rows[0].keys()))
    qs = hf.normalize_rows(rows)
    print(f"  usable single-answer MCQs: {len(qs)}/{len(rows)}   (integer answers zero-based: {hf.detect_zero_based(rows)})")
    print("  subjects:", dict(collections.Counter(q['subject'] or '(unknown)' for q in qs)))
    for q in qs[:2]:
        print("  •", q["question"][:120], "|", q["options"], "| correct:", q["options"][q["correct_index"]])


async def main():
    targets = sys.argv[1:] or sorted({d for ids in hf.DEFAULT_DATASETS.values() for d in ids})
    for ds in targets:
        await check(ds)


if __name__ == "__main__":
    asyncio.run(main())
