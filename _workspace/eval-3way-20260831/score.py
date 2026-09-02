import os
#!/usr/bin/env python3
"""3자 윤문 eval 채점기 — 결정론 지표만 쓴다.

주관 판정(자연스러운가)은 여기서 하지 않는다. 세 에이전트가 같은 픽스처를
윤문한 결과를 같은 계측기로 재고, 축별로 나란히 놓는 것까지가 이 스크립트의
일이다. 품질 판정은 사람이 표를 보고 한다.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent
REFS = pathlib.Path("/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references")
sys.path.insert(0, str(REFS))
import metrics_v2 as m  # noqa: E402

# 픽스처별 보호 토큰 — 하나라도 사라지면 의미 보존 실패
PROTECTED = {
    "fx_m1": ["3건", "120초", "김민수"],
    "fx_m2": ["62퍼센트"],
    "fx_legacy": ["2026년", "47조 원"],
}
AGENTS = ["claude", "codex", "agy"]
OUTDIR = os.environ.get("OUTDIR","out")


def measure(text: str) -> dict:
    comp = m.compression_signal(text)
    full = m.compute_all_v2(text, genre="report")
    return {
        "chars": len(text),
        "nonfinal_rate": comp["nonfinal_rate"],
        "genitive_dense": comp["genitive_dense_count"],
        "compressed": comp["compressed"],
        "risk_score": full.get("risk_score"),
        "risk_band": full.get("risk_band"),
        "reg_mix": m.register_mix_rate(text),
    }


def main() -> int:
    rows = []
    for fx in sorted(PROTECTED):
        src = (ROOT / "input" / f"{fx}.txt").read_text(encoding="utf-8")
        base = measure(src)
        rows.append({"fixture": fx, "agent": "(원문)", **base, "kept": "-", "change_rate": "-"})
        for ag in AGENTS:
            p = ROOT / OUTDIR / f"{fx}.{ag}.md"
            if not p.exists():
                rows.append({"fixture": fx, "agent": ag, "chars": None, "note": "결과 없음"})
                continue
            out = p.read_text(encoding="utf-8").strip()
            got = measure(out)
            missing = [t for t in PROTECTED[fx] if t not in out]
            rows.append({
                "fixture": fx, "agent": ag, **got,
                "kept": "OK" if not missing else f"유실 {missing}",
                "change_rate": round(m.change_rate(src, out), 4),
            })
    (ROOT / "report" / "scores.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    hdr = f"{'픽스처':<12}{'에이전트':<10}{'글자':>6}{'비완결':>8}{'격식혼재':>8}{'과압축':>7}{'risk':>6}{'변경률':>8}  보호토큰"
    print(hdr); print("-" * len(hdr))
    for r in rows:
        if r.get("chars") is None:
            print(f"{r['fixture']:<12}{r['agent']:<10}  {r.get('note')}"); continue
        print(f"{r['fixture']:<12}{r['agent']:<10}{r['chars']:>6}{r['nonfinal_rate']:>8}"
              f"{r["reg_mix"]:>7}{str(r['compressed']):>7}{str(r['risk_score']):>6}"
              f"{str(r['change_rate']):>8}  {r['kept']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
