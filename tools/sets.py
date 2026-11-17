"""표시 도구가 다루는 그림 묶음 (2026-11-17). 도구마다 `--set 이름` 으로 고른다. 안 주면 quadruped.

  quadruped   data/testset/quadruped   네 발 시험 세트 (정답, 아이 그림 포함이라 로컬만)        http://127.0.0.1:8765/
  qd_pilot    data/qd_pilot            Quick, Draw! 시험 100장 (학습 정답 모으기가 되는지 재기)  http://127.0.0.1:8766/
  qd_300      data/qd_300              Quick, Draw! 300장 (줄인 표시 방식으로 학습 정답 모으기)   http://127.0.0.1:8767/
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SETS = {
    "quadruped": ("data/testset/quadruped", 8765, "네 발 시험 세트"),
    "qd_pilot": ("data/qd_pilot", 8766, "Quick, Draw! 시험 100장"),
    "qd_300": ("data/qd_300", 8767, "Quick, Draw! 300장"),
}


def pick() -> tuple[str, Path, int, str]:
    """(이름, 그림 폴더, 포트, 화면 제목)"""
    name = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "quadruped"
    if name not in SETS:
        sys.exit(f"모르는 묶음: {name} (있는 것: {', '.join(SETS)})")
    folder, port, title = SETS[name]
    return name, ROOT / folder, port, title


def page_path(folder: Path, kind: str = "label") -> Path:
    return folder.parent / f"{kind}_{folder.name}.html"
