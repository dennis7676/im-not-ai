#!/usr/bin/env python3
"""1차(out) 대 3차(out3) 대조 채점 — M-7 신설 전후."""
import os, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, "/Users/1109698/.claude/forks/im-not-ai/skills/humanize-korean/references")
import metrics_v2 as m  # noqa: E402

PROTECTED = {"fx_m1": ["3건", "120초", "김민수"], "fx_m2": ["62퍼센트"], "fx_legacy": ["2026년", "47조 원"]}
AGENTS = ["claude", "codex", "agy"]


def row(fx, ag, text, src):
    c = m.compression_signal(text)
    missing = [t for t in PROTECTED[fx] if t not in text]
    return (fx, ag, len(text), c["nonfinal_rate"], m.register_mix_rate(text),
            round(m.change_rate(src, text), 3) if src else "-",
            "OK" if not missing else "유실")


def main():
    out = os.environ.get("OUTDIR", "out")
    print(f"{'픽스처':<11}{'에이전트':<9}{'글자':>5}{'비완결':>8}{'격식혼재':>9}{'변경률':>8}  보호")
    print("-" * 60)
    for fx in ["fx_m1", "fx_m2", "fx_legacy"]:
        src = (ROOT / "input" / f"{fx}.txt").read_text(encoding="utf-8")
        r = row(fx, "(원문)", src, None)
        print(f"{r[0]:<11}{r[1]:<9}{r[2]:>5}{r[3]:>8}{r[4]:>9}{str(r[5]):>8}  -")
        for ag in AGENTS:
            p = ROOT / out / f"{fx}.{ag}.md"
            if not p.exists():
                print(f"{fx:<11}{ag:<9}  결과 없음"); continue
            r = row(fx, ag, p.read_text(encoding="utf-8").strip(), src)
            print(f"{r[0]:<11}{r[1]:<9}{r[2]:>5}{r[3]:>8}{r[4]:>9}{str(r[5]):>8}  {r[6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
