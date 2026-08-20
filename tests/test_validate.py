import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.collector import CollectStats
from src.pdf import PdfResult
from src.validate import check_duplicates, validate_run


def test_check_duplicates_finds_repeated_uid():
    records = [{"uid": "VXvue/VP-1"}, {"uid": "VXvue/VP-2"}, {"uid": "VXvue/VP-1"}]
    assert check_duplicates(records) == ["VXvue/VP-1"]


def test_validate_run_fails_when_srs_count_mismatch_protects_existing_pdfs():
    stats = [CollectStats(project_id="VXvue", total_items=350, expected_total=360)]
    result = validate_run(
        collect_stats=stats,
        all_records=[{"uid": f"VXvue/VP-{i}", "id": f"VP-{i}"} for i in range(350)],
        pdf_results=[PdfResult(path=Path("a.pdf"), size_bytes=100, page_count=5, ok=True)],
        expected_pdf_count=1,
        partition_warnings=[],
    )
    assert result.ok is False
    failed_names = [c["name"] for c in result.checks if not c["passed"]]
    assert "srs_count_match:VXvue" in failed_names


def test_validate_run_fails_when_pdf_is_empty():
    stats = [CollectStats(project_id="VXvue", total_items=1, expected_total=1)]
    result = validate_run(
        collect_stats=stats,
        all_records=[{"uid": "VXvue/VP-1", "id": "VP-1"}],
        pdf_results=[PdfResult(path=Path("a.pdf"), size_bytes=0, page_count=0, ok=False, error="empty")],
        expected_pdf_count=1,
        partition_warnings=[],
    )
    assert result.ok is False


def test_validate_run_passes_when_all_checks_ok():
    stats = [CollectStats(project_id="VXvue", total_items=2, expected_total=2)]
    result = validate_run(
        collect_stats=stats,
        all_records=[{"uid": "VXvue/VP-1", "id": "VP-1"}, {"uid": "VXvue/VP-2", "id": "VP-2"}],
        pdf_results=[PdfResult(path=Path("a.pdf"), size_bytes=100, page_count=3, ok=True)],
        expected_pdf_count=1,
        partition_warnings=[],
    )
    assert result.ok is True


# ---------- 같은 날 재실행 시 archive 오염 방지 ----------


def test_publish_does_not_archive_same_named_output(tmp_path):
    """같은 날 재실행하면 지식파일 폴더의 '오늘자' 산출물은 이전 버전이 아니므로
    archive로 옮기지 않는다. 옮기면 진짜 이전 버전이 같은 날 사본에 묻힌다."""
    from src.publish import archive_and_publish

    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    archive = tmp_path / "archive"
    generated_dir = tmp_path / "out"
    generated_dir.mkdir()

    # 이전 버전(260731) + 같은 날 재실행 대상(260820)이 함께 있는 상태
    (knowledge / "(사양서) VXvue 사양서1(260731).pdf").write_bytes(b"old")
    (knowledge / "(사양서) VXvue 사양서1(260820).pdf").write_bytes(b"same-day-previous")
    new_pdf = generated_dir / "(사양서) VXvue 사양서1(260820).pdf"
    new_pdf.write_bytes(b"new")

    archive_and_publish(
        knowledge_folder=knowledge, archive_dir=archive, generated_pdfs=[new_pdf], file_date="260820"
    )

    archived = sorted(p.name for p in (archive / "260820").iterdir())
    assert archived == ["(사양서) VXvue 사양서1(260731).pdf"], "같은 이름 산출물은 백업 대상이 아니다"
    assert (knowledge / "(사양서) VXvue 사양서1(260820).pdf").read_bytes() == b"new"
    # _dup 파일이 생기지 않는다.
    assert not any("_dup" in name for name in archived)
