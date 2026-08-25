#!/usr/bin/env python3
"""문체 축을 재고 기준선 스냅샷과 대조한다.

새 참고 자료가 생기면 이 스크립트로 재서 `docs/style_reference.json` 에 한 행 더한다.
그러면 "사람 산문은 이런 값이다"가 표본 하나에 매달리지 않게 된다.

    python3 scripts/measure_style.py <파일...> [--label 이름] [--add]

⚠️ 축은 전부 **관측 전용**이다. baseline 셀도 임계값도 없다. 어느 값이 "좋다"고
   판정하지 않는다 — 참조와 얼마나 떨어져 있는지만 보여 준다.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "skills", "humanize-korean", "references"))

import metrics as m1  # noqa: E402
import metrics_v2 as m2  # noqa: E402

REFERENCE = os.path.join(_ROOT, "docs", "style_reference.json")

AXES = [
    ("sentence_length_cv", m2.sentence_length_cv, "문장 길이 변동계수 — 높을수록 리듬 진폭"),
    ("short_sentence_rate", m2.short_sentence_rate, "25자 이하 비율"),
    ("short_after_long_rate", m2.short_after_long_rate, "긴 문장 뒤 짧은 문장"),
    ("comma_inclusion_rate", m1.comma_inclusion_rate, "쉼표 포함 문장 비율"),
    ("ending_comma_rate", m1.ending_comma_rate, "종결 직전 쉼표"),
    ("vague_noun_rate", m2.vague_noun_rate, "포괄어 10만자당"),
    ("nominal_dominance", m2.nominal_dominance, "명사류 어절 비율"),
    ("ending_diversity", m2.ending_diversity, "종결어미 다양성"),
    ("lexical_diversity", m1.lexical_diversity, "어휘 다양성"),
]

# 문두 접속사 — 역접 계열과 순접·결론 계열을 갈라 센다.
_ADVERSATIVE = ("그러나", "그런데", "하지만", "오히려", "다만")
_CONSECUTIVE = ("그리고", "그래서", "따라서", "또한", "즉", "한편", "물론")
_SENT = re.compile(r"(?<=[.!?])\s+")


def conjunction_profile(text: str) -> dict[str, float]:
    body = m2._strip_markup(text)
    sents = [s.strip() for s in _SENT.split(body) if len(s.strip()) > 5]
    if not sents:
        return {"adversative": 0.0, "consecutive": 0.0}
    adv = sum(1 for s in sents if s.startswith(_ADVERSATIVE))
    con = sum(1 for s in sents if s.startswith(_CONSECUTIVE))
    return {"adversative": adv / len(sents), "consecutive": con / len(sents)}


def measure(text: str) -> dict[str, float]:
    out = {name: round(fn(text), 4) for name, fn, _ in AXES}
    out.update({k: round(v, 4) for k, v in conjunction_profile(text).items()})
    out["chars"] = len(text)
    return out


def _load() -> dict:
    if not os.path.exists(REFERENCE):
        return {"samples": []}
    with open(REFERENCE, encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--label", default=None, help="스냅샷에 적을 이름")
    ap.add_argument("--kind", default="unknown", choices=["human", "generated", "unknown"])
    ap.add_argument("--add", action="store_true", help="측정값을 style_reference.json 에 추가")
    args = ap.parse_args(argv)

    text = "\n\n".join(open(p, encoding="utf-8").read().strip() for p in args.paths)
    got = measure(text)
    ref = _load()

    human = [s for s in ref["samples"] if s.get("kind") == "human"]
    print(f"{'축':<24}{'이 글':>10}{'사람 참조':>12}{'차이':>10}")
    print("-" * 58)
    for name, _, desc in AXES:
        base = None
        if human:
            vals = [s["metrics"][name] for s in human if name in s.get("metrics", {})]
            if vals:
                base = sum(vals) / len(vals)
        if base is None:
            print(f"{name:<24}{got[name]:>10}{'—':>12}{'—':>10}")
        else:
            print(f"{name:<24}{got[name]:>10}{base:>12.4f}{got[name]-base:>+10.4f}")
    print(f"\n문두 접속사 — 역접 {got['adversative']:.3f} / 순접·결론 {got['consecutive']:.3f}")
    if human:
        a = sum(s["metrics"]["adversative"] for s in human) / len(human)
        c = sum(s["metrics"]["consecutive"] for s in human) / len(human)
        print(f"  사람 참조    — 역접 {a:.3f} / 순접·결론 {c:.3f}")
    print(f"\n사람 참조 표본 {len(human)}개. **표본이 적으면 참조를 규범으로 읽지 말 것.**")

    if args.add:
        ref["samples"].append({
            "label": args.label or os.path.basename(args.paths[0]),
            "kind": args.kind,
            "metrics": got,
        })
        with open(REFERENCE, "w", encoding="utf-8") as f:
            json.dump(ref, f, ensure_ascii=False, indent=2)
        print(f"\n-> {REFERENCE} 에 추가됨 (표본 {len(ref['samples'])}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
