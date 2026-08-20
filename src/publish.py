"""검증 통과한 신규 PDF를 실제 지식파일 폴더에 반영 (기존 파일은 archive로 이동 후 교체)."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger("srs_automation")


def archive_and_publish(
    *, knowledge_folder: Path, archive_dir: Path, generated_pdfs: list[Path], file_date: str
) -> None:
    if not knowledge_folder:
        logger.warning("knowledge_folder 설정이 비어 있어 지식파일 폴더 반영을 건너뜁니다.")
        return

    knowledge_folder.mkdir(parents=True, exist_ok=True)
    archive_target = archive_dir / file_date
    archive_target.mkdir(parents=True, exist_ok=True)

    # 같은 날 재실행하면 지식파일 폴더에 이미 '오늘 날짜' 산출물이 들어 있다. 그것은
    # 교체 대상인 '이전 버전'이 아니라 같은 버전이므로 archive로 옮기지 않는다. 옮기면
    # archive/<date>/ 안에서 진짜 이전 버전(예: 260731)이 같은 날 재실행 사본들에 묻히고,
    # 3회 이상 실행하면 _dup 파일까지 쌓인다.
    new_names = {pdf.name for pdf in generated_pdfs}
    existing = list(knowledge_folder.glob("(사양서)*.pdf"))
    for f in existing:
        if f.name in new_names:
            logger.info("같은 이름의 산출물로 갱신되므로 백업하지 않고 덮어씁니다: %s", f.name)
            continue
        dest = archive_target / f.name
        if dest.exists():
            dest = archive_target / f"{f.stem}_dup{f.suffix}"
        shutil.move(str(f), str(dest))
        logger.info("기존 사양서 백업: %s -> %s", f.name, dest)

    for pdf in generated_pdfs:
        dest = knowledge_folder / pdf.name
        shutil.copy2(pdf, dest)
        logger.info("신규 사양서 반영: %s", dest)
