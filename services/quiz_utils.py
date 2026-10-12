"""
Pure helpers for quiz questions (no network / no AI / no aiogram imports, so they are easy to test).

Main job: FIX "correct answer is always option A".
AI models love to put the right answer first, so we never trust the position the AI chose.
After questions are generated / fetched we re-place the correct option ourselves, and we do it in a
balanced way (a quiz of 4 questions gets the correct answer in A, B, C and D once each, in random order).
"""
import random
import re

# Options that only make sense in a fixed position ("All of the above", "Both A and B" ...).
# Shuffling those would break the question, so such questions are not moved.
_PINNED_RE = re.compile(
    r"\b(all|none|both|neither)\b[^.]{0,20}\b(above|these|options?|of them)\b"
    r"|\b[A-D]\s*(?:and|&|,|or)\s*[A-D]\b"
    r"|\b(?:option|options|statement)\s*\(?[A-D1-4]\)?"
    r"|\bsab\s+sahi\b|\bkoi\s+nahi\b",
    re.IGNORECASE,
)


def has_positional_option(options) -> bool:
    return any(_PINNED_RE.search(str(o)) for o in options)


def _balanced_targets(n: int, rng: random.Random) -> list:
    """n target slots (0-3) where every slot is used as evenly as possible, in random order."""
    targets = []
    while len(targets) < n:
        cycle = [0, 1, 2, 3]
        rng.shuffle(cycle)
        # avoid the same slot twice in a row at a cycle boundary
        if targets and cycle[0] == targets[-1]:
            cycle.append(cycle.pop(0))
        targets.extend(cycle)
    return targets[:n]


def randomize_positions(questions: list, rng: random.Random = None) -> list:
    """
    Returns NEW question dicts where the correct option sits at a random-but-balanced position.
    `correct_index` is updated to match, so scoring stays correct.
    Questions that have 'All of the above' style options are returned unchanged.
    """
    rng = rng or random.Random()
    targets = _balanced_targets(len(questions), rng)
    out = []
    for q, target in zip(questions, targets):
        opts = [str(o) for o in q["options"]]
        ci = q["correct_index"]
        new_q = dict(q)
        if len(opts) != 4 or not (0 <= ci < len(opts)) or has_positional_option(opts):
            out.append(new_q)
            continue
        correct = opts[ci]
        others = [o for i, o in enumerate(opts) if i != ci]
        rng.shuffle(others)
        others.insert(target, correct)
        new_q["options"] = others
        new_q["correct_index"] = target
        out.append(new_q)
    return out
