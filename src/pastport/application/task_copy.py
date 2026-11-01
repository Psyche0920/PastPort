"""Reject repeated inventory counts that contradict the canonical task requirements."""

import re

from pastport.domain.modules import NarrativeDraft

_WORDS = dict(
    zip(
        (
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
        ),
        range(1, 17),
        strict=True,
    )
)
_DIGITS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ENGLISH = re.compile(
    r"\b(\d+|" + "|".join(_WORDS) + r")\s+(?:(?:transparent|opaque|rectangular|model)\s+)*"
    r"(?:pieces?|panels?|strips?|rectangles?)\b",
    re.IGNORECASE,
)
_CHINESE = re.compile(
    r"([一二两三四五六七八九十\d]+)\s*[块条片](?:透明|不透明|长条|矩形|模型|木)*板"
)


def _count(value: str) -> int | None:
    if value.isdecimal():
        return int(value)
    if value.lower() in _WORDS:
        return _WORDS[value.lower()]
    if value in _DIGITS:
        return _DIGITS[value]
    if "十" in value:
        before, after = value.split("十", 1)
        if before and before not in _DIGITS or after and after not in _DIGITS:
            return None
        return _DIGITS.get(before, 1) * 10 + _DIGITS.get(after, 0)
    return None


def task_copy_issues(draft: NarrativeDraft) -> tuple[str, ...]:
    issues: list[str] = []
    for exercise in draft.tiling_intents:
        scene = next(
            (
                s
                for s in draft.package.game.scenes
                if any(t.task_id == exercise.task_id for t in s.tasks)
            ),
            None,
        )
        if scene is None:
            continue
        task = next(t for t in scene.tasks if t.task_id == exercise.task_id)
        keys = {scene.body_key, task.objective_key, task.feedback_key, *task.hint_keys}
        texts = [exercise.learning_goal, exercise.fiction_notice]
        texts.extend(
            entry.text
            for locale in draft.package.game.locales
            for entry in locale.entries
            if entry.key in keys
        )
        expected = len(exercise.rules.pieces)
        for text in texts:
            for pattern in (_ENGLISH, _CHINESE):
                if any(
                    _count(match.group(1)) not in (None, expected)
                    for match in pattern.finditer(text)
                ):
                    issues.append(
                        f"Task {exercise.task_id} copy contradicts its structured inventory"
                    )
                    break
    return tuple(dict.fromkeys(issues))
