from __future__ import annotations

import unittest
from pathlib import Path


SKILL_PATH = Path(__file__).parents[1] / "skills" / "humanize-korean" / "SKILL.md"


class TestSkillGateWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL_PATH.read_text(encoding="utf-8")

    def section(self, heading: str, next_heading: str | None = None) -> str:
        start = self.skill.index(heading)
        end = self.skill.index(next_heading, start) if next_heading else len(self.skill)
        return self.skill[start:end]

    def test_each_execution_path_inlines_verify_gates_command(self) -> None:
        sections = {
            "fast": self.section("## Light 경로", "## Standard 경로"),
            "standard": self.section("## Standard 경로", "## Heavy 경로"),
            "heavy": self.section("## Heavy 경로", "## Finalize 승급 규칙"),
        }

        for path_name, section in sections.items():
            with self.subTest(path=path_name):
                command_lines = [
                    line for line in section.splitlines() if "verify_gates.py" in line
                ]
                self.assertTrue(
                    command_lines,
                    f"{path_name} 경로에 인라인 게이트 명령이 없습니다.",
                )

    def test_phase_2_5_documents_mktemp_fallback(self) -> None:
        phase = self.section("## Phase 2.5", "## 결과 전달")

        self.assertIn("mktemp", phase)


if __name__ == "__main__":
    unittest.main()
