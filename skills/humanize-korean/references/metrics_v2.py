"""Humanize KR v2.0 quantitative metrics calculator.

Extends v1.6 metrics.py with post-editese 3축 (simplification·normalisation·
interference) and 8 translation-type detection signals from the Korean
machine-translation/post-editing literature (Toral 2019; Schmaltz 2020;
보고서 T1~T8).

Hard rule: standard library ONLY (json/re/math/collections/os/sys/argparse/
statistics). No konlpy/bareun/mecab/spaCy. Morphological analysis is
approximated with regex + suffix dictionaries (한자어 -성·-적·-화·-도·-력·-감·-원,
평서형 -한다·-된다·-이다, 진행형 -고 있다, 이중 조사 -에서의·-에로의·-으로의·-에의·-으로부터의·-로부터의).

Versioning:
- v1.6 8 functions (comma_inclusion_rate ... lexical_diversity) are imported
  *as-is* from references/metrics.py (signature + return preserved). DO NOT
  redefine them here. Regression-safe.
- v2.0 adds 14 NEW pure functions for post-editese + T1~T8 detection,
  plus `change_rate()` — the SSOT for 철칙 #4 change-rate gating.

This file ships next to metrics.py at
`skills/humanize-korean/references/`.

CLI:
    python metrics_v2.py --input run/01_input.txt \
        --genre essay --output run/00_metrics_v2.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import os
import re
import sys
from collections import Counter
from statistics import StatisticsError, mean, pstdev
from typing import Any

# ---------------------------------------------------------------------------
# Import v1.6 metrics module (regression-safe — signatures untouched)
# ---------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
# metrics.py ships in the same references/ directory as this file.
_V1_METRICS_DIR = _HERE
if _V1_METRICS_DIR not in sys.path:
    sys.path.insert(0, _V1_METRICS_DIR)

import metrics as _v1  # noqa: E402  (sys.path mutation is intentional)

# Re-export the 8 v1.6 metric callables verbatim. They keep their original
# signatures and return shapes — `metrics_v2.comma_inclusion_rate(text)`
# is byte-identical to `metrics.comma_inclusion_rate(text)`.
comma_inclusion_rate = _v1.comma_inclusion_rate
comma_usage_rate = _v1.comma_usage_rate
ending_comma_rate = _v1.ending_comma_rate
comma_segment_length = _v1.comma_segment_length
conclusion_pivot_count = _v1.conclusion_pivot_count
safe_balance_count = _v1.safe_balance_count
hanja_nominalizer_density = _v1.hanja_nominalizer_density
lexical_diversity = _v1.lexical_diversity

# Reuse v1.6 internal helpers (private, regression-safe — we never mutate).
_split_sentences = _v1._split_sentences
_eojeols = _v1._eojeols
_strip_punct = _v1._strip_punct

VERSION = "v2.0"

# ---------------------------------------------------------------------------
# v2.0 module-level constants — sufix / lexicon dictionaries
# ---------------------------------------------------------------------------

# 한자어 명사화 접미사 v2.0 확장 — v1.6의 -성·-적·-화 + 보고서 T6 보강 4종.
# token-final 1글자 매칭. 토큰 길이 >= 2 가드는 함수 내부에서.
_HANJA_SUFFIXES_V2 = ("성", "적", "화", "도", "력", "감", "원")

# 평서형 종결 사전 — normalisation 축. 문장 마지막 어절의 어미를 매칭.
# 한자어 + 한다/된다/이다 형태가 가장 흔한 정규화 시그널.
_DECLARATIVE_ENDINGS = ("한다", "된다", "이다")

# 진행형 어미 — T8b. "~고 있다" 표층 매칭. 종결형/연결형 모두 포함.
# 부정형 "있지 않다", 의존명사 "있는" 은 별개. 정규식은 "고 있" 토큰
# 시작점 + 후속 "다/었/는" 등을 폭넓게 캡처.
_PROGRESSIVE_RE = re.compile(r"고\s*있(?:다|었|는|을|던|는다)")

# T2b 이중 피동 표층 어휘. 모두 "되어진/여진/혀진/려진" 등 피동 보조어간 +
# 피동 보조용언 중첩의 표층형. 단순 "되다" 는 정상 표현이므로 제외.
_DOUBLE_PASSIVE_TOKENS = (
    "되어진다",
    "되어졌다",
    "되어진",
    "되어지는",
    "여지다",
    "여진다",
    "여졌다",
    "여진",
    "잊혀진",
    "잊혀졌",
    "잊혀진다",
    "보여진다",
    "보여졌다",
    "보여진",
    "쓰여진다",
    "쓰여졌다",
    "쓰여진",
    "닫혀진",
    "열려진",
    "불려진",
    "놓여진",
)

# T2a "~에 의해 + 피동" — 피동 동사가 직후 N어절 안에 등장해야 매칭.
# 단순 "에 의해" 는 빈번한 자연 한국어이므로 제외 (보고서 T2 caveat).
_BY_PASSIVE_RE = re.compile(
    r"에\s*의(?:해|하여)\s+\S{0,12}?(?:되|받|당하|지)(?:다|었|어|ㄴ다|는다|는|ㄹ|을)"
)

# T3 인칭 대명사 — 영어 he/she/it/they 의 1대1 매핑.
# "그" 단독은 지시사·관형사로도 자주 쓰이므로 보수적으로 처리:
#   - "그" 뒤에 조사 "는/가/를/의/에게/에서/와/도/만" 이 붙은 경우만 인칭으로 본다.
#   - 그녀/그들/그것 은 거의 항상 인칭 대명사이므로 단독 매칭.
_PRONOUN_RE = re.compile(
    r"(?:그녀(?:는|가|를|의|에게|와|도|만)?"
    r"|그것(?:은|이|을|의|에|에게)?"
    r"|그들(?:은|이|을|의|에게|과|도)?"
    r"|그(?:는|가|를|의|에게|와|도|만)(?=\s|[\.,!?]|$))"
)

# T4 무정물·추상명사 + -들. 토큰 단위 매칭.
# 보고서 III.3.4.2 + pe_checklist PE5에서 "거의 모두 삭제 후보" 로 거론된
# 핵심 어휘셋. 사전은 보수적(false positive 줄임).
_INANIMATE_DEUL_TOKENS = (
    "데이터들",
    "정보들",
    "결과들",
    "연구들",
    "아이디어들",
    "방법들",
    "문제들",
    "의견들",
    "시스템들",
    "기술들",
    "사실들",
    "사례들",
    "이론들",
    "개념들",
    "현상들",
    "특징들",
    "요소들",
    "원인들",
    "영향들",
    "변화들",
    "기능들",
    "조건들",
    "기준들",
    "관점들",
    "원리들",
)

# T6 light verb construction — have/make 류 직역.
# "회의를 가지다·결정을 내리다" 식 light verb.
_HAVE_MAKE_LITERAL_TOKENS = (
    "가지고 있다",
    "가지고있다",
    "가지고 있는",
    "가지고있는",
    "가지고 있었",
    "가지고있었",
    "가지고 있으",
    "가지고있으",
    "갖고 있다",
    "갖고있다",
    "갖고 있는",
    "갖고있는",
    "을 가지다",
    "를 가지다",
    "을 가졌",
    "를 가졌",
    "을 가진다",
    "를 가진다",
    "을 만들다",
    "를 만들다",
    "을 만들었",
    "를 만들었",
    "을 만들어 낸",
    "를 만들어 낸",
    "을 만들어낸",
    "를 만들어낸",
    "회의를 가지",
    "회의를 가졌",
    "한번 봄을 가지",
    "결정을 내리",
    "결정을 내렸",
)

# T7 이중 조사 결합. caveat #5 (단순 ~의 제외) 정확히 반영.
# "에서의" 등 6종만 매칭 — 단일 ~의는 절대 매칭 안 됨.
_DOUBLE_PARTICLE_RE = re.compile(
    r"(?:에서의|에로의|으로의|에의|으로부터의|로부터의)"
)

# 단락 분리: 빈 줄 1개 이상.
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n")

# 종결어미 다양성 — 문장 마지막 종결어미 표층(보통 1~2음절 끝마디)을 키로 사용.
# verb stem(예: "결정한다"의 "결정") 부분은 제외하고 어미 부분(예: "한다")만 봐야
# 다양성 신호가 의미를 가진다. 따라서 마지막 2음절을 우선 키로 사용.
_ENDING_FINAL_RE = re.compile(r"([가-힣]{2})[\.!?]\s*$")
# 한 음절만 있는 문장(예: "와.")은 별도로 1음절 매칭.
_ENDING_FINAL_FALLBACK_RE = re.compile(r"([가-힣])[\.!?]\s*$")


# ---------------------------------------------------------------------------
# Local helpers (do not shadow v1.6)
# ---------------------------------------------------------------------------


def _split_paragraphs(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    return [p.strip() for p in _PARAGRAPH_SPLIT_RE.split(text) if p.strip()]


def _last_eojeol(sentence: str) -> str:
    toks = _eojeols(sentence)
    if not toks:
        return ""
    return _strip_punct(toks[-1])


def _all_tokens(text: str) -> list[str]:
    toks = [_strip_punct(t) for t in _eojeols(text)]
    return [t for t in toks if t]


# ---------------------------------------------------------------------------
# === v2.0 NEW METRICS ===
# Group A: simplification 축
# ---------------------------------------------------------------------------


def lexical_diversity_ttr(text: str) -> float:
    """Type-token ratio (TTR) over Korean eojeols — simplification axis.

    Identical computation to v1.6 ``lexical_diversity`` but exposed under the
    Toral 2019 simplification-axis name so the post-editese score can map
    cleanly. Returns 0.0 on empty input.
    """
    return lexical_diversity(text)


def lexical_density(text: str) -> float:
    """Content-word ratio — proxy for lexical density (simplification axis).

    Standard-library proxy: a token is counted as a *content word* if its
    final character is one of the v2.0 hanja nominalizer suffixes
    (-성·-적·-화·-도·-력·-감·-원), or if it ends with a verb/adjective
    declarative marker (-한다·-된다·-이다·-했다·-된다·-였다·-이었다·-답다·-스럽다·-롭다).
    Function words (조사·접속부사) are filtered out by length<2 and a small
    stopword list.

    Returns content_word_count / total_token_count in [0, 1].
    """
    tokens = _all_tokens(text)
    if not tokens:
        return 0.0
    stop = {
        "그리고", "그러나", "하지만", "또한", "또는", "혹은", "즉", "예를", "예컨대",
        "이는", "이것은", "그것은", "그러므로", "따라서",
    }
    content_suffixes = ("성", "적", "화", "도", "력", "감", "원")
    content_endings = (
        "한다", "된다", "이다", "했다", "였다", "었다",
        "답다", "스럽다", "롭다", "하다", "되다",
    )
    hits = 0
    for t in tokens:
        if len(t) < 2:
            continue
        if t in stop:
            continue
        if t[-1] in content_suffixes:
            hits += 1
            continue
        if any(t.endswith(end) for end in content_endings):
            hits += 1
    return hits / len(tokens)


def ending_diversity(text: str) -> float:
    """Sentence-ending diversity — unique endings / total sentences.

    Approximates 종결어미 다양성. Sentence is split via v1.6 helper; the
    last 1~3 syllables (Hangul only) before the terminal punctuation are
    used as the ending key. Higher = more diverse (more human-like).
    Returns 0.0 when no sentence ends with valid punctuation.
    """
    sents = _split_sentences(text)
    keys: list[str] = []
    for s in sents:
        m = _ENDING_FINAL_RE.search(s)
        if m:
            keys.append(m.group(1))
            continue
        m2 = _ENDING_FINAL_FALLBACK_RE.search(s)
        if m2:
            keys.append(m2.group(1))
    if not keys:
        return 0.0
    return len(set(keys)) / len(keys)


# ---------------------------------------------------------------------------
# Group B: normalisation 축
# ---------------------------------------------------------------------------


def normalisation_score(text: str) -> float:
    """Declarative-form (~한다/~된다/~이다) concentration — normalisation axis.

    Returns the ratio of sentences whose final eojeol ends with one of the
    three canonical declarative markers (~한다·~된다·~이다 — variants
    `-한다.`, `-한다!` 등은 punctuation-stripped). High values (>0.7) signal
    normalised, AI-like prose; very low values (<0.3) often signal informal
    speech (해체) or heterogeneous registers. Range [0, 1].
    """
    sents = _split_sentences(text)
    if not sents:
        return 0.0
    hits = 0
    for s in sents:
        last = _last_eojeol(s)
        if not last:
            continue
        for ending in _DECLARATIVE_ENDINGS:
            if last.endswith(ending):
                hits += 1
                break
    return hits / len(sents)


def da_streak_rate(text: str) -> int:
    """Count of '-다' streak runs of length >= 4 — T8a normalisation signal.

    A *streak* = consecutive sentences whose final eojeol ends in '다'
    (any '~다' — 한다·된다·이다·었다·았다·였다 등). Streaks of length 4+
    are reported. The return value is the number of distinct streaks
    (not the total streak length). Documents with one long uniform run
    of '-다' will return 1; truly diverse docs return 0.
    """
    sents = _split_sentences(text)
    streaks = 0
    cur = 0
    for s in sents:
        last = _last_eojeol(s)
        if last.endswith("다"):
            cur += 1
        else:
            if cur >= 4:
                streaks += 1
            cur = 0
    if cur >= 4:
        streaks += 1
    return streaks


# ---------------------------------------------------------------------------
# Group C: interference 축 — T1~T8 detection signals
# ---------------------------------------------------------------------------


def inanimate_subject_rate(text: str) -> float:
    """T1: inanimate-subject + universal-verb pattern rate.

    Approximation: count sentences whose first content noun ends with one
    of the v2.0 hanja suffixes (-성·-적·-화·-도·-력·-감·-원) OR matches a
    short list of inanimate/abstract subjects (`연구·데이터·분석·결과·시스템·
    기술·사례·현상·이론·정책·보고서`) AND whose verb is a universal
    cognitive/declarative verb (보여준다·시사한다·만든다·드러낸다·제시한다·
    나타낸다·증명한다·말해준다·의미한다·가져온다). Returns
    matching_sents / total_sents in [0, 1].
    """
    sents = _split_sentences(text)
    if not sents:
        return 0.0
    inanimate_subjects = (
        "연구", "데이터", "분석", "결과", "시스템", "기술", "사례",
        "현상", "이론", "정책", "보고서", "AI", "인공지능", "모델",
        "알고리즘", "변화", "위기", "혁신", "사회", "경제",
    )
    universal_verbs = (
        "보여준다", "보여줬다", "보여주는", "시사한다", "시사하는",
        "만든다", "만들어", "드러낸다", "드러냈다", "드러내는",
        "제시한다", "제시했다", "나타낸다", "나타냈다", "나타내는",
        "증명한다", "증명했다", "말해준다", "말해주는",
        "의미한다", "의미하는", "가져온다", "가져왔다", "가져오는",
    )
    hits = 0
    for s in sents:
        toks = _all_tokens(s)
        if not toks:
            continue
        head = toks[0]
        # Subject heuristic: first token, optionally followed by 은/는/이/가.
        head_stem = head
        for josa in ("은", "는", "이", "가", "도"):
            if head.endswith(josa) and len(head) > 1:
                head_stem = head[:-1]
                break
        is_inanimate = (
            head_stem in inanimate_subjects
            or (len(head_stem) >= 2 and head_stem[-1] in _HANJA_SUFFIXES_V2)
        )
        if not is_inanimate:
            continue
        # Verb heuristic: any later token in `universal_verbs`.
        if any(any(uv in t for uv in universal_verbs) for t in toks[1:]):
            hits += 1
    return hits / len(sents)


def by_passive_count(text: str) -> int:
    """T2a: ~에 의해 + passive-verb co-occurrence count.

    Bare '에 의해' is excluded. Only the regex-anchored
    '에 의해 ... 되/받/당하/지' pattern is counted. Returns int >= 0.
    """
    if not text.strip():
        return 0
    return len(_BY_PASSIVE_RE.findall(text))


def double_passive_count(text: str) -> int:
    """T2b: double-passive (잊혀지다·보여지다·되어진다·여지다·쓰여지다 …) count.

    Surface-form lexicon. 단순 '되다' 는 제외 (자연 표현). Returns int >= 0.
    """
    if not text.strip():
        return 0
    n = 0
    for tok in _DOUBLE_PASSIVE_TOKENS:
        n += text.count(tok)
    return n


def pronoun_density(text: str) -> float:
    """T3: personal-pronoun density per paragraph (avg).

    Counts 그/그녀/그것/그들 (+ 조사 fused forms). Bare '그' is only counted
    when followed by 는/가/를/의/에게/와/도/만 to filter out demonstrative use.
    Returns paragraph-mean of (pronoun_tokens / paragraph_eojeols).
    Range [0, 1]. Empty input returns 0.0.
    """
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return 0.0
    densities: list[float] = []
    for p in paragraphs:
        toks = _all_tokens(p)
        if not toks:
            continue
        pronoun_hits = len(_PRONOUN_RE.findall(p))
        densities.append(pronoun_hits / len(toks))
    if not densities:
        return 0.0
    try:
        return mean(densities)
    except StatisticsError:
        return 0.0


def deul_overuse_rate(text: str) -> float:
    """T4: inanimate / abstract noun + '-들' over-use ratio.

    Returns deul_overuse_hits / total_eojeols. The numerator counts
    occurrences of any token in `_INANIMATE_DEUL_TOKENS` (데이터들·정보들·
    결과들·연구들·아이디어들·방법들·문제들·의견들·시스템들·기술들 …).
    Range [0, 1] — practical AI text seldom exceeds ~0.05.
    """
    toks = _all_tokens(text)
    if not toks:
        return 0.0
    hits = 0
    for t in toks:
        # Match exact OR with one short josa suffix (-과/와/이/가/을/를/의/에/은/는/도)
        if t in _INANIMATE_DEUL_TOKENS:
            hits += 1
            continue
        for base in _INANIMATE_DEUL_TOKENS:
            if t.startswith(base) and len(t) - len(base) in (1, 2):
                # remaining tail must be hangul (likely josa)
                tail = t[len(base):]
                if all("가" <= ch <= "힣" for ch in tail):
                    hits += 1
                    break
    return hits / len(toks)


def relative_clause_nesting(text: str) -> int:
    """T5: count of sentences with relative-clause nesting depth >= 3.

    Approximation: a sentence is nested when it contains 3+ adnominal
    clause endings -ㄴ/-는/-ㄹ/-한/-된/-할 followed by a noun (heuristic:
    the syllable before whitespace). We check every sentence for the
    count of token endings in `(ㄴ|는|ㄹ|던|할|한|된|될)` followed by a
    short space-separated noun. Returns the *number of sentences*
    (not total nestings) with depth >= 3.
    """
    sents = _split_sentences(text)
    if not sents:
        return 0
    # 관형형 어미 종결 음절 매칭 — 어절 끝이 (ㄴ|는|ㄹ|던|한|된|할|될|온) 인 토큰 수.
    adnominal_re = re.compile(r"[가-힣]+(?:ㄴ|는|ㄹ|던|한|된|할|될|온|간)\s+[가-힣]")
    matches_per_sent = []
    for s in sents:
        m = adnominal_re.findall(s)
        matches_per_sent.append(len(m))
    return sum(1 for c in matches_per_sent if c >= 3)


def have_make_literal_count(text: str) -> int:
    """T6: count of literal have/make light-verb constructions.

    가지고 있다·갖고 있다·~을 가지다·~을 만들다·회의를 가지다·결정을 내리다 …
    Returns int >= 0.
    """
    if not text.strip():
        return 0
    n = 0
    for tok in _HAVE_MAKE_LITERAL_TOKENS:
        n += text.count(tok)
    return n


def double_particle_count(text: str) -> int:
    """T7: double-particle (에서의·에로의·으로의·에의·으로부터의·로부터의) count.

    Caveat #5 (single ~의 excluded) is *enforced by construction* — the
    regex never matches a bare ~의. Returns int >= 0.
    """
    if not text.strip():
        return 0
    return len(_DOUBLE_PARTICLE_RE.findall(text))


def progressive_aspect_rate(text: str) -> float:
    """T8b: progressive aspect '~고 있다' rate per sentence.

    Returns progressive_hits / total_sentences. Surface-form match; not
    every '~고 있다' is reducible (예: 진행 의미가 본질적인 동사) but
    high rates flag automatic 1대1 매핑. Range typically [0, 1+] — values
    >0.5 signal heavy literal mapping.
    """
    sents = _split_sentences(text)
    if not sents:
        return 0.0
    hits = sum(len(_PROGRESSIVE_RE.findall(s)) for s in sents)
    return hits / len(sents)


# ---------------------------------------------------------------------------
# === v2.0 INTERFERENCE INDEX ===
# Composite signal weighted across T1~T8.
# ---------------------------------------------------------------------------


# --- v2.4 로컬 확장 (2026-08-25): 포괄어·명사나열·빈동사 -----------------------
# 근거: RESEARCH/korean-word-precision_20260825_065209
#  - 포괄어 목록은 로컬 코퍼스 실측에서 유도했다(사용자 발화 27.7만자 대 에이전트 281만자).
#    한국어 문체론에서 이 목록을 금지어로 지목한 1차 출처는 찾지 못했으므로(A1),
#    이 지표는 학술 근거가 아니라 **사용자 취향 규칙**이다. 등급을 낮춰 다룬다.
#  - 명사 나열은 plainlanguage.gov 의 "3개를 넘어가면 참기 어려워진다"가 근거다(A3).

# 로컬 실측에서 사용자 대비 과다했던 것만 넣는다(10만자당 차이 +3 이상).
# 사용자도 즐겨 쓰는 말(구조·부분·방식·상황)은 넣지 않는다 — 넣으면 사람 글이 걸린다.
_VAGUE_NOUNS = ("상태", "대상", "축", "자리", "지점", "층", "기제", "모양", "측면", "차원", "셈")
_JOSA = r"(?:은|는|이|가|을|를|의|에|에서|로|으로|와|과|도|만|들|이라|이고)"
_VAGUE_RE = re.compile(r"(?<![가-힣])(?:" + "|".join(_VAGUE_NOUNS) + r")" + _JOSA)

# 지목 가능한 대상의 신호. Hayakawa 의 추상 사다리를 한국어로 옮기면
# "육안·측정·이름을 댈 수 있는가"이고(A3 4절), 문자열로는 이렇게 근사한다.
_CONCRETE_RE = re.compile(r"\d|[A-Za-z_./]{3,}|`[^`]+`|[가-힣]+님|\d+개|\d+건")

def vague_noun_rate(text: str) -> float:
    """10만자당 포괄어 빈도.

    실측(2026-08-25): 사용자 16.4 대 에이전트 54.5 로 **3.3배** 갈린다. 다만 1,500자
    조각 단위로 보면 양쪽 중앙값이 모두 0.0 이고, 사용자 상위 10% 임계(69.6)를 넘는
    에이전트 조각이 20% 다 — 분포가 한쪽으로 치우쳐 있다. **게이트가 아니라 진단
    신호로 쓴다.** 임계 하나로 자르면 다섯에 하나만 잡고 넷은 놓친다.
    """
    body = _strip_markup(text)
    if not body:
        return 0.0
    return len(_VAGUE_RE.findall(body)) / len(body) * 100000


def vague_noun_unsupported(text: str) -> int:
    """포괄어가 둘 이상인데 지목 가능한 대상이 하나도 없는 문장 수.

    실측 주의(A0): 이 판정은 **산문에만** 유효하다. 코드·경로·수치가 섞인 기술 문장은
    구체 신호가 항상 잡혀 무조건 통과한다 — 전수 적용하면 사람 글이 더 많이 걸린다
    (사용자 0.38% 대 에이전트 0.09%로 역전됐다). 그래서 이 값은 게이트가 아니라
    진단 입력이고, 임계 판정은 사람이나 진단 콜이 한다.
    """
    body = _strip_markup(text)
    hits = 0
    for sentence in re.split(r"[.!?\n]", body):
        s = sentence.strip()
        if not (20 <= len(s) <= 300):
            continue
        if len(_VAGUE_RE.findall(s)) >= 2 and not _CONCRETE_RE.search(s):
            hits += 1
    return hits


def noun_string_max(text: str) -> int:
    """조사 없이 이어 붙인 한글 명사의 최대 연쇄 길이.

    plainlanguage.gov: 명사가 셋을 넘어가면 읽기 어려워진다. 한국어도 같은 현상이다(A3).

    ⚠️ **이 코퍼스에서는 판별력이 없다** (2026-08-25 실측): 1,500자 조각 757개에서
    사용자와 에이전트의 중앙값이 4.0 으로 같았고, 사용자 상위 10% 임계를 넘는 에이전트
    조각이 1% 였다. 근거는 외부에 있지만 우리 글에서는 안 갈린다 — **게이트에 쓰지 말고
    관측만 한다.** 다른 장르(공문서, 기술 명세)에서는 다시 재 볼 값어치가 있다.
    """
    body = _strip_markup(text)
    longest = 0
    for run in re.findall(r"(?:[가-힣]{2,}\s+){2,}[가-힣]{2,}", body):
        words = run.split()
        # 조사로 끝나지 않는 어절만 명사 연쇄로 본다
        chain = 0
        for w in words:
            if re.search(_JOSA + r"$", w) or re.search(r"(?:다|요|고|며|서|만|면)$", w):
                chain = 0
            else:
                chain += 1
                longest = max(longest, chain)
    return longest


# ---------------------------------------------------------------------------
# v2.5 로컬 확장 — KatFishNet(ACL 2025) A등급 신호 둘
#
# 출처: Shinwoo Park 외, "KatFishNet: Detecting LLM-Generated Korean Text
# through Linguistic Feature Analysis", ACL 2025 (2025.acl-long.1030).
# 논문이 분리 측정한 세 특징 중 쉼표는 이미 C-11(comma_*)로 구현돼 있고,
# 나머지 둘 — 품사 다양성(명사 편중)과 띄어쓰기 균일성 — 이 여기다.
#
# ⚠️ **논문의 AUC(82.99 / 79.51)는 KatFish 코퍼스 숫자이지 우리 판별력이 아니다.**
#    2026-08-25 에 우리 코퍼스로 쟀더니 **둘 다 방향이 반대로 나왔다**(AUC 0.275 /
#    0.355). 왜 그런지는 **아직 모른다** — 코퍼스 화행 교란 가설을 검정했으나
#    지지받지 못했다. baseline 셀도 임계값도 만들지 않는다 — **관측용으로만 쓴다.**
#    `noun_string_max`가 외부 근거가 탄탄한데도 이 코퍼스에서
#    안 갈렸던 전례가 있다. 재기 전에는 게이트로 올리지 않는다.
#
# ⚠️ 형태소 분석기를 쓰지 않는다(이 파일의 철칙). 아래 둘 다 **어절 말미 형태로
#    근사**한 값이고 품사 태깅이 아니다. 그래서 이름도 `pos_diversity`가 아니라
#    재는 것 그대로 붙였다.

# 용언(동사·형용사)으로 끝나는 어절의 말미 신호. 종결·연결 어미를 함께 본다.
_PREDICATE_TAIL_RE = re.compile(
    r"(?:"
    # 종결. `자`(담당자·사용자), `네`, `군` 은 명사 꼬리와 충돌해 뺐다
    # — 2026-08-25 테스트가 "담당자"를 predicate 으로 잡아 드러났다.
    r"다|요|죠|까"
    r"|고|며|면|서|지만|는데|은데|아도|어도|아서|어서|니까|므로|도록|려고|거나"  # 연결
    r"|았|었|겠|한다|된다|한다면|했|됐"
    r")$"
)

# 부사·관형 수식어의 말미 신호.
_MODIFIER_TAIL_RE = re.compile(r"(?:히|이|게|적으로|처럼|보다|같이|째|만큼|없이)$")

# 어절에서 종결부호·따옴표 등을 털어내고 본체만 남긴다.
_EOJEOL_TRIM_RE = re.compile(r"^[\(\[\"\'`~*_]+|[\)\]\"\'`~*_,.!?;:…]+$")


def _eojeol_class(word: str) -> str:
    """어절 하나를 말미 형태로 거칠게 분류한다.

    반환값은 ``"predicate"`` / ``"modifier"`` / ``"nominal"`` / ``"other"``.

    ⚠️ **형태소 분석이 아니다.** `noun_string_max`가 인라인으로 쓰던 판정
    (조사 꼬리 + 용언 어미)을 함수로 뽑아 어휘를 넓힌 것이고, 오분류가 있다.
    예를 들어 "빠르게"는 modifier 로 잡히지만 "높이"(명사)도 modifier 로 잡힌다.
    관형형 어미 -는/-은/-을 은 동형 조사와 구별되지 않아 "먹는"이 nominal 로 간다 —
    형태소 없이는 못 가르는 자리이므로 그대로 두고 여기 적어 둔다.
    코퍼스 수준 비율을 볼 때만 쓰고 문장 단위 판정에 쓰지 않는다.
    """
    w = _EOJEOL_TRIM_RE.sub("", word)
    if not w or not re.search(r"[가-힣]", w):
        return "other"
    # 조사를 **먼저** 본다. 순서를 뒤집으면 "회의에서"의 조사 `에서`가 연결어미
    # `서`로 먼저 걸려 predicate 이 된다(2026-08-25 테스트가 잡았다).
    if re.search(_JOSA + r"$", w):
        return "nominal"
    if _PREDICATE_TAIL_RE.search(w):
        return "predicate"
    if _MODIFIER_TAIL_RE.search(w):
        return "modifier"
    return "nominal" if re.search(r"[가-힣]$", w) else "other"


def nominal_dominance(text: str) -> float:
    """명사류 어절 비율(0.0~1.0). 낮은 품사 다양성 = 명사 편중의 근사값.

    KatFishNet 이 "LLM 한국어는 품사 다양성이 낮다(명사 편중)"를 AUC 82.99% 로
    보고했다. 형태소 분석기 없이 품사 다양성 자체는 못 재므로, 논문이 서술한
    실체인 **명사 편중도**를 어절 말미 형태로 근사한다.

    ⚠️ **쟀더니 방향이 반대였고, 원인은 아직 모른다** (2026-08-25).
    홀드아웃 AUC 0.275 — 0.5 미만이니 뒤집혀 있다(사람 중앙값 0.901 대 AI 0.844).
    "우리 사람 코퍼스가 산문이 아니라 프롬프트라서"라는 **가설을 세워 검정했으나
    지지되지 않았다** — 사용자 조각을 명령형 밀도로 갈랐을 때 산문에 가까운 쪽이
    오히려 더 높았다(0.913 대 0.857). 그 검정의 대리지표도 튼튼하지 않다.
    **뒤집어 쓰면 된다고 읽지 말 것** — 왜 뒤집혔는지 모르는 채로 방향만 바꾸는 것이다.
    baseline 셀도 임계값도 만들지 않는다 — **관측만 한다.**
    전문: `docs/validation_2026-08-25_word-precision-signals.md`
    """
    body = _strip_markup(text)
    classes = [_eojeol_class(w) for w in body.split()]
    counted = [c for c in classes if c != "other"]
    if not counted:
        return 0.0
    return sum(1 for c in counted if c == "nominal") / len(counted)


def spacing_uniformity(text: str) -> float:
    """어절 길이의 변동계수(표준편차/평균). **낮을수록 기계적으로 균일하다.**

    KatFishNet 이 "LLM 한국어는 띄어쓰기가 기계적으로 균일하다"를 AUC 79.51% 로
    보고했다. 한국어 띄어쓰기 규칙이 느슨해 사람 글은 어절 길이가 들쭉날쭉한 반면
    생성문은 고르다는 관찰이다.

    측정 대상은 **한글을 포함한 어절만**이고 길이는 그 어절의 **한글 음절 수**다.
    경로·식별자·백틱 코드 같은 비한글 어절을 넣으면 길이 분포가 통째로 흔들리는데,
    이 코퍼스에는 그런 토큰이 흔하다(`_CONCRETE_RE` 가 그 증거다).

    ⚠️ **쟀더니 방향이 반대였다** (2026-08-25). 홀드아웃 AUC 0.355 —
    사람 쪽이 더 균일했다(0.459 대 AI 0.490). `nominal_dominance` 와 같은 처분이다:
    원인 미상, 관측만. 임계값도 baseline 셀도 만들지 않는다.
    전문: `docs/validation_2026-08-25_word-precision-signals.md`
    """
    body = _strip_markup(text)
    lengths = [
        len(re.findall(r"[가-힣]", w))
        for w in body.split()
        if re.search(r"[가-힣]", w)
    ]
    lengths = [n for n in lengths if n > 0]
    if len(lengths) < 2:
        return 0.0
    try:
        avg = mean(lengths)
        if avg == 0:
            return 0.0
        return pstdev(lengths) / avg
    except StatisticsError:
        return 0.0


# ---------------------------------------------------------------------------
# v2.6 리듬 축 — 문장 길이의 진폭
#
# 기존 지표는 어절과 어휘를 재지 **문장 리듬**을 안 잰다. `spacing_uniformity` 는
# 어절 길이이고 문장 길이가 아니다.
#
# 참조 자료(2026-08-25): 사용자가 "읽기 편하다"고 지목한 한국어 산문 한 권을 재보니
# 문장 길이 변동계수 0.61, 25자 이하 22.2%, 80자 이상 10.6% 로 **양쪽 꼬리가 다
# 두꺼웠다.** 같은 프롬프트로 뽑은 생성문은 한쪽만 두껍거나(클로드 0.55, 짧은 쪽만)
# 아예 평평했다(코덱스 0.38, 25자 이하 3.6%).
#
# ⚠️ **표본이 저자 한 명, 책 한 권이다.** "사람 산문"이 아니라 그 저자를 잰 것일 수
#    있다. baseline 셀도 임계값도 만들지 않는다 — **관측만 한다.** 기준선 스냅샷은
#    `docs/style_reference.json`, 다른 글을 대보는 도구는 `scripts/measure_style.py`.

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_LONG_SENT = 70   # "긴 문장"의 경계
_SHORT_SENT = 25  # "짧은 문장"의 경계


def _sentences(text: str) -> list[str]:
    body = _strip_markup(text)
    return [s.strip() for s in _SENT_SPLIT_RE.split(body) if len(s.strip()) > 5]


def sentence_length_cv(text: str) -> float:
    """문장 길이의 변동계수(표준편차/평균). **높을수록 리듬 진폭이 크다.**

    `spacing_uniformity` 와 헷갈리지 말 것 — 그쪽은 **어절** 길이이고 이쪽은 **문장**
    길이다. 어절이 고른 글과 문장이 고른 글은 다른 현상이다.

    ⚠️ 우리 코퍼스에서 미검증이다(2026-08-25). 참조값은 저자 한 명의 산문 하나뿐이다.
    """
    L = [len(s) for s in _sentences(text)]
    if len(L) < 2:
        return 0.0
    try:
        avg = mean(L)
        return pstdev(L) / avg if avg else 0.0
    except StatisticsError:
        return 0.0


def short_after_long_rate(text: str) -> float:
    """긴 문장 바로 뒤에 짧은 문장이 오는 비율(0.0~1.0).

    긴 문장으로 벌려 놓고 짧은 문장으로 못 박는 패턴을 센다. 참조 산문에서 0.163 이었다
    (70자 넘는 문장 369개 중 60개 뒤에 25자 이하가 왔다).

    분모는 **긴 문장의 수**이지 전체 문장이 아니다. 긴 문장이 없으면 0.0 을 돌려준다 —
    이때의 0.0 은 "리듬이 없다"가 아니라 **"잴 대상이 없다"** 이므로 그렇게 읽지 말 것.

    ⚠️ 우리 코퍼스에서 미검증이다(2026-08-25). 관측만 한다.
    """
    sents = _sentences(text)
    longs = 0
    hits = 0
    for a, b in zip(sents, sents[1:]):
        if len(a) >= _LONG_SENT:
            longs += 1
            if len(b) <= _SHORT_SENT:
                hits += 1
    return hits / longs if longs else 0.0


def short_sentence_rate(text: str) -> float:
    """25자 이하 문장의 비율(0.0~1.0). 참조 산문 0.222, 코덱스 산문 0.036.

    ⚠️ 우리 코퍼스에서 미검증이다(2026-08-25). 관측만 한다.
    """
    L = [len(s) for s in _sentences(text)]
    if not L:
        return 0.0
    return sum(1 for x in L if x <= _SHORT_SENT) / len(L)


def interference_index(text: str) -> dict[str, Any]:
    """T1~T8 weighted interference signal — interference axis composite.

    Returns a dict with each sub-signal score plus a `weighted_total`
    that sums per-type contributions (each capped to [0, 1] by simple
    rescaling). This is descriptive, not a z-score — calibration to
    baseline happens in compute_all_v2.
    """
    n_sents = max(len(_split_sentences(text)), 1)
    chars = max(len(text), 1)
    components = {
        "T1_inanimate_subject_rate": inanimate_subject_rate(text),
        "T2a_by_passive_per_1k": by_passive_count(text) / chars * 1000,
        "T2b_double_passive_per_1k": double_passive_count(text) / chars * 1000,
        "T3_pronoun_density": pronoun_density(text),
        "T4_deul_overuse_rate": deul_overuse_rate(text),
        "T5_nested_clause_count": relative_clause_nesting(text),
        "T6_have_make_per_1k": have_make_literal_count(text) / chars * 1000,
        "T7_double_particle_per_1k": double_particle_count(text) / chars * 1000,
        "T8b_progressive_rate": progressive_aspect_rate(text),
    }
    # Each component clamped to [0, 1] heuristically:
    weights = {
        "T1_inanimate_subject_rate": 1.0,        # already in [0,1]
        "T2a_by_passive_per_1k": 0.2,            # /5
        "T2b_double_passive_per_1k": 0.2,
        "T3_pronoun_density": 4.0,               # human <0.015, scale up
        "T4_deul_overuse_rate": 4.0,
        "T5_nested_clause_count": 0.05,          # /20
        "T6_have_make_per_1k": 0.2,
        "T7_double_particle_per_1k": 0.5,
        "T8b_progressive_rate": 1.0,
    }
    weighted_total = 0.0
    for k, v in components.items():
        weighted_total += min(1.0, max(0.0, v * weights[k]))
    return {
        "components": components,
        "weighted_total": weighted_total,
        "n_sentences": n_sents,
        "n_chars": chars,
    }


# ---------------------------------------------------------------------------
# === C-8 ANTITHESIS COUNTER (구조 게이트 — 전멸 판정 전용) ===
# ---------------------------------------------------------------------------

# C-8 부정-긍정 대구 표층형: "X가/이 아니라 Y", "~이기 이전에", "~되기 이전에",
# "~이기보다". 사람 글에도 흔한 정상 수사이므로 절대치로는 아무 판정도 못 한다.
_ANTITHESIS_RE = re.compile(r"(?:가|이)\s*아니라|이기\s*이전에|되기\s*이전에|이기보다")


def antithesis_count(text: str) -> int:
    """C-8 부정-긍정 대구("X가 아니라 Y" 류) 카운트. 전멸 게이트용.

    절대치 판정 금지 — 대구는 사람 글에도 흔한 정상 수사다. 이 카운트는
    ``before >= 5 AND after == 0`` (전멸 = 윤문이 수사 구조를 몰살) 판정
    전용이다. 문자 diff가 못 보는 구조 편집(C-8 -75% 뒤에 change_rate
    2.77%가 숨는 실측 사례)을 잡기 위한 진단 앵커.
    """
    if not text.strip():
        return 0
    return len(_ANTITHESIS_RE.findall(text))


# ---------------------------------------------------------------------------
# === CHANGE RATE (철칙 #4 게이트 SSOT) ===
# ---------------------------------------------------------------------------

# 철칙 #4 게이트 임계값. change_rate() 반환값과 직접 비교한다.
CHANGE_RATE_WARN = 0.30   # 30% 초과 — 경고, 과윤문 점검
CHANGE_RATE_ABORT = 0.50  # 50% 초과 — 강제 중단

# 마크업 전용 줄: 코드 펜스·수평선·표 구분선 등 — ignore_markup 모드에서 제거.
_MARKUP_ONLY_LINE_RE = re.compile(
    r"^\s*(?:```.*|~~~.*|-{3,}|\*{3,}|={3,}|\|[\s:\-|]*)\s*$"
)
# 줄머리 마크업 장식: 헤딩(#)·불릿(-·*·+)·번호 목록·인용(>) — 장식만 벗기고
# 텍스트 내용은 보존한다.
_MARKUP_PREFIX_RE = re.compile(r"^\s*(?:#{1,6}\s+|>\s?|[-*+]\s+|\d{1,3}[.)]\s+)")


def _strip_markup(text: str) -> str:
    """Drop markup-only lines and leading markup decoration, keep content."""
    kept: list[str] = []
    for line in text.splitlines():
        if _MARKUP_ONLY_LINE_RE.match(line):
            continue
        kept.append(_MARKUP_PREFIX_RE.sub("", line))
    return "\n".join(kept)


def change_rate(before: str, after: str, ignore_markup: bool = False) -> float:
    """윤문 전후 문자 기반 변경률 — 철칙 #4 게이트의 SSOT.

    이 함수의 반환값이 변경률의 단일 진실 원천(SSOT)이며, 에이전트의
    재량(눈대중) 자가 산출을 대체한다. 게이트 판정은 반드시 이 값과
    ``CHANGE_RATE_WARN``(0.30 경고) / ``CHANGE_RATE_ABORT``(0.50 강제 중단)
    상수를 비교해 내린다.

    계산: ``difflib.SequenceMatcher`` 문자 단위 유사도의 보수
    (``1 - ratio``). 0.0(동일) ~ 1.0(전면 교체) 범위.

    ``ignore_markup=True``이면 양쪽 텍스트에서 마크업 전용 줄(코드 펜스·
    수평선·표 구분선)을 제거하고 줄머리 장식(헤딩 #·불릿·번호·인용 >)을
    벗긴 뒤 비교한다 — 헤딩·마크업 삭제가 본문 변경률을 부풀리는 문제
    (2026-04-26-001 run에서 44.7% 중 상당분이 마크업 삭제)의 보정용.
    기본값은 순수 문자 diff.
    """
    if ignore_markup:
        before = _strip_markup(before)
        after = _strip_markup(after)
    if not before and not after:
        return 0.0
    matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
    return 1.0 - matcher.ratio()


# ---------------------------------------------------------------------------
# Baseline + z-score (v2.0 extension)
# ---------------------------------------------------------------------------


def _default_baseline_v2_path() -> str:
    return os.path.join(_HERE, "baseline_v2.json")


def _load_baseline_v2(path: str | None) -> dict[str, Any]:
    p = path or _default_baseline_v2_path()
    if not os.path.exists(p):
        return {}
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _z_simple(value: float, mean_v: float, stdev: float) -> float | None:
    if stdev is None or stdev <= 0:
        return None
    return (value - mean_v) / stdev


# ---------------------------------------------------------------------------
# Public entry point — v2.0 superset
# ---------------------------------------------------------------------------


def compute_all_v2(
    text: str,
    genre: str = "essay",
    baseline_path: str | None = None,
    baseline_v2_path: str | None = None,
) -> dict[str, Any]:
    """Compute v1.6 metrics + v2.0 post-editese + T1~T8 signals.

    Returns the v1.6 ``compute_all`` payload extended with:
        - ``v2_metrics``: dict of new metric values
        - ``v2_z_scores``: per-metric z against baseline_v2 (None if placeholder)
        - ``v2_baseline_warnings``: list of metric keys whose baseline cell
          carries `_placeholder: true`.
    """
    base = _v1.compute_all(text, genre=genre, baseline_path=baseline_path)
    v2_metrics: dict[str, float | int] = {
        "lexical_diversity_ttr": lexical_diversity_ttr(text),
        "lexical_density": lexical_density(text),
        "ending_diversity": ending_diversity(text),
        "normalisation_score": normalisation_score(text),
        "da_streak_rate": da_streak_rate(text),
        "inanimate_subject_rate": inanimate_subject_rate(text),
        "by_passive_count": by_passive_count(text),
        "double_passive_count": double_passive_count(text),
        "pronoun_density": pronoun_density(text),
        "deul_overuse_rate": deul_overuse_rate(text),
        "relative_clause_nesting": relative_clause_nesting(text),
        "have_make_literal_count": have_make_literal_count(text),
        "double_particle_count": double_particle_count(text),
        "progressive_aspect_rate": progressive_aspect_rate(text),
        # C-8 대구 카운트 — 진단 앵커로만 노출. baseline placeholder라 z는
        # None이어도 무방. 판정은 before/after 전멸 비교로만 한다.
        "antithesis_count": antithesis_count(text),
        # v2.5 KatFishNet A등급 신호 둘 — baseline 셀이 없어 z 는 None 이다.
        # antithesis_count 와 같은 취급: 진단 앵커로만 노출하고 게이트로 쓰지 않는다.
        "nominal_dominance": nominal_dominance(text),
        "spacing_uniformity": spacing_uniformity(text),
        # v2.6 리듬 축 — baseline 셀 없음, z 는 None. 관측 전용.
        "sentence_length_cv": sentence_length_cv(text),
        "short_after_long_rate": short_after_long_rate(text),
        "short_sentence_rate": short_sentence_rate(text),
        # v2.7 M절 과압축 축 — baseline 셀 없음, z 는 None. 관측 전용이며
        # route_hint 의 light 강등 방지에만 쓴다(게이트 아님).
        "nonfinal_sentence_rate": nonfinal_sentence_rate(text),
        "genitive_dense_count": genitive_dense_count(text),
    }
    compression = compression_signal(text)
    interference = interference_index(text)

    bv2 = _load_baseline_v2(baseline_v2_path)
    cells = {}
    warnings: list[str] = []
    if bv2:
        genres = bv2.get("genres", {}) or {}
        cells = genres.get(genre) or genres.get("essay") or {}
    z_scores: dict[str, float | None] = {}
    for k, v in v2_metrics.items():
        cell = cells.get(k)
        if not cell:
            z_scores[k] = None
            continue
        if cell.get("_placeholder"):
            warnings.append(k)
        z_scores[k] = _z_simple(
            float(v), float(cell.get("mean", 0.0)), float(cell.get("stdev", 0.0))
        )

    base["version"] = VERSION
    base["v2_metrics"] = v2_metrics
    base["v2_interference_index"] = interference
    base["v2_compression"] = compression
    base["v2_z_scores"] = z_scores
    base["v2_baseline_warnings"] = warnings
    return base


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Humanize KR v2.0 metric runner")
    parser.add_argument("--input", required=True, help="Input text file path")
    parser.add_argument("--genre", default="essay", help="essay/news/blog/qa/dialogue")
    parser.add_argument("--output", default=None, help="Output JSON path (optional)")
    parser.add_argument(
        "--baseline", default=None, help="Override v1.6 baseline JSON path"
    )
    parser.add_argument(
        "--baseline-v2", default=None, help="Override v2.0 baseline JSON path"
    )
    args = parser.parse_args(argv)

    with open(args.input, "r", encoding="utf-8") as f:
        text = f.read()

    result = compute_all_v2(
        text,
        genre=args.genre,
        baseline_path=args.baseline,
        baseline_v2_path=args.baseline_v2,
    )

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print(result["risk_band"])
    return 0


# ---------------------------------------------------------------------------
# v1.6 호환 별칭 (prepare_monolith_input.py가 _metrics_mod.compute_all 호출)
# ---------------------------------------------------------------------------
compute_all = compute_all_v2  # v2.0 출력은 v1.6의 상위집합 (integration_note §1)


if __name__ == "__main__":
    sys.exit(_main())


# ---------------------------------------------------------------------------
# v2.7 로컬 확장 — M절 과압축 계측 (2026-08-31)
#
# A~L 의 모든 지표는 **있는 것을 센다**(어휘 티, 피동, 대구, 장식). M절이 잡는
# 것은 조사·어미·서술어·성분이 **없는** 상태라, 기존 지표로는 구조적으로 세지
# 못한다. 실측(2026-08-31): 전형적 과압축 보고문 3문단이 risk_score=0 ·
# route_hint=light 로 나왔다 — 어휘 티가 하나도 없어서다. 여기 세 함수는 그
# 사각지대만 메운다.
#
# ⚠️ **형태소 분석이 아니다.** 어절 말미 음절로 근사한다. baseline 셀도 임계도
# 만들지 않는다 — route_hint 의 light 강등을 막는 용도로만 쓰고, 게이트로
# 승격하지 않는다.
# ---------------------------------------------------------------------------

# 완결 종결로 인정하는 마지막 음절. 한국어 종결어미의 말음이며, 여기에
# 없으면 명사형·부사구·연결어미 종결로 본다.
_FINITE_TAIL = set("다까요죠네군지자라오마니가랴세")

# 명시적 연결어미 종결 — 위 화이트리스트를 통과해도 비완결인 경우
# ("~하지만"은 '만', "~하고"는 '고'라 이미 걸리지만 "~하니"는 '니'로 통과한다)
_CONNECTIVE_TAILS = ("면서", "는데", "지만", "어서", "아서", "니까", "거나", "하고", "하며", "도록", "보다", "처럼", "대로")

_HEADING_OR_LIST_RE = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|\||>\s|```)")


def _prose_sentences(text: str) -> list[str]:
    """산문 문장만 반환한다. 헤딩·불릿·표·코드펜스 줄은 통째로 버린다.

    M절은 산문에만 적용된다 — 개조식 항목에 서술어를 붙이면 문서가 망가진다.
    그래서 계측도 같은 경계를 쓴다.
    """
    # ⚠️ 순서가 중요하다. `_strip_markup` 은 줄머리 마커(#, -, 1., >)를
    # **벗겨서** 내용을 살리므로, 그걸 먼저 돌리면 개조식 줄이 산문으로
    # 둔갑한다(2026-08-31 실측: 사람이 쓴 지침 문서 3편이 nonfinal 0.56~0.71
    # 로 오탐). 원문 라인에서 먼저 걸러내고 나서 마크업을 벗긴다.
    lines = [ln for ln in text.splitlines() if ln.strip() and not _HEADING_OR_LIST_RE.match(ln)]
    body = _strip_markup("\n".join(lines))
    out: list[str] = []
    for ln in lines:
        ln = re.sub(r"`[^`]*`|\*\*|\*|__|\[([^\]]*)\]\([^)]*\)", lambda m: m.group(1) or "", ln)
        for s in _SENT_SPLIT_RE.split(ln):
            s = s.strip().strip('"\'“”‘’()[]')
            if len(s) < 8 or len(s.split()) < 3:
                continue
            # 서지 인용·영문 조각 제외. 한글 음절이 절반에 못 미치면 산문
            # 문장이 아니다 (2026-08-31 실측: scholarship.md 오탐 41건이
            # 전부 영문 저자명·연도·출판사 줄이었다).
            hangul = sum(1 for ch in s if "가" <= ch <= "힣")
            letters = sum(1 for ch in s if ch.isalpha())
            if letters and hangul / letters < 0.5:
                continue
            out.append(s)
    return out


def nonfinal_sentence_rate(text: str) -> float:
    """M-2. 서술어·종결어미 없이 끝나는 산문 문장의 비율(0.0~1.0)."""
    sents = _prose_sentences(text)
    if not sents:
        return 0.0
    bad = 0
    for s in sents:
        core = s.rstrip(".!?…·,;: \t")
        if not core:
            continue
        last = core.split()[-1] if core.split() else core
        if last.endswith(_CONNECTIVE_TAILS) or (last[-1] not in _FINITE_TAIL):
            bad += 1
    return bad / len(sents)


def genitive_dense_count(text: str) -> int:
    """M-4. 관형격 '~의'가 2회 이상 나오는 산문 문장의 수."""
    n = 0
    for s in _prose_sentences(text):
        if len(re.findall(r"(?<=[가-힣])의(?=[\s가-힣])", s)) >= 2:
            n += 1
    return n


def compression_signal(text: str) -> dict[str, float | int]:
    """M절 합성 신호. **route_hint 의 light 강등 방지에만** 쓴다.

    ⚠️ **판별력의 한계를 정직하게 적는다** (2026-08-31 실측, 표본 6편).
    사람이 쓴 기술 지침 문서의 ``nonfinal_rate`` 가 0.20~0.58 로 넓게 퍼진다 —
    기술 문서는 원래 명사 종결 메모가 많아서다. 인공 과압축 샘플은 0.75 였고,
    표본이 작아 임계 0.60 은 **잠정값**이다. 그래서:

    - 게이트로 승격하지 않는다. baseline 셀도 만들지 않는다.
    - route_hint 의 **light 판정에만** 건다. 손익이 비대칭이라서다 — 오탐하면
      진단 콜 한 번 더 도는 손해로 끝나고, 놓치면 과압축 글이 최소 파이프라인으로
      그대로 나간다.
    - ``genitive_rate`` 는 절대 건수가 아니라 문장 대비 비율이다. 절대값은 긴
      문서에서 자동으로 커져 길이를 재게 된다.
    """
    sents = _prose_sentences(text)
    n = len(sents)
    nonfinal = nonfinal_sentence_rate(text)
    gen = genitive_dense_count(text)
    return {
        "prose_sentence_count": n,
        "nonfinal_rate": round(nonfinal, 4),
        "genitive_dense_count": gen,
        "genitive_rate": round(gen / n, 4) if n else 0.0,
        "noun_string_max": noun_string_max(text),
        "compressed": bool(n >= 4 and (nonfinal >= 0.60 or (gen / n if n else 0) >= 0.15)),
    }
