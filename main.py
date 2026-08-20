#!/usr/bin/env python
"""VXvue / License Manager SRS 사양서 자동 최신화.

사용 예:
    python main.py                 # 전체 파이프라인 (수집 -> PDF -> Diff -> 리포트 -> 반영)
    python main.py --crawl-only    # Polarion 수집 + Snapshot 저장만
    python main.py --export-only   # 이미 저장된 오늘자 Snapshot으로 HTML/PDF만 재생성
    python main.py --diff-only     # 오늘자 vs 이전 Snapshot Diff + 리포트만 재생성
    python main.py --force         # 오늘자 Snapshot이 이미 있어도 다시 수집
    python main.py --dry-run       # 지식파일 폴더 반영(archive/copy) 단계만 생략
    python main.py --recheck-known-problems
                                   # 이미 문제로 등록된 SRS도 정상 렌더링 가능해졌는지 재확인
"""
from __future__ import annotations

import argparse
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

from src.collector import CollectStats, collect_project
from src.config import ConfigError, load_config
from src.diff import diff_snapshots
from src.logging_setup import setup_logging
from src.partition import assign_file_groups
from src.polarion_client import PolarionApiError, PolarionClient
from src.problem_state import ProblemState
from src.publish import archive_and_publish
from src.render_recovery import render_group_pdf_with_recovery
from src.report import save_reports
from src.snapshot_store import (
    find_previous_snapshot_date,
    load_snapshot,
    save_manifest,
    save_snapshot,
)
from src.util import build_pdf_filename, ensure_dir
from src.validate import validate_run


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="VXvue/License Manager SRS 사양서 자동 최신화")
    p.add_argument("--crawl-only", action="store_true", help="Polarion 수집 + Snapshot 저장만 수행")
    p.add_argument("--export-only", action="store_true", help="오늘자 Snapshot으로 HTML/PDF만 재생성")
    p.add_argument("--diff-only", action="store_true", help="오늘자 vs 이전 Snapshot Diff/리포트만 재생성")
    p.add_argument("--force", action="store_true", help="오늘자 Snapshot이 있어도 다시 수집")
    p.add_argument("--dry-run", action="store_true", help="지식파일 폴더 반영 단계를 생략(archive/copy 안 함)")
    p.add_argument(
        "--recheck-known-problems",
        action="store_true",
        help="config의 render.known_problem_srs 캐시를 무시하고 모든 SRS를 정상 렌더링부터 재확인",
    )
    return p.parse_args()


def _load_all_records_from_disk(config, run_date: str, logger) -> list[dict]:
    all_records: list[dict] = []
    for project in config.projects:
        snap = load_snapshot(config.snapshots_dir, run_date, project.id)
        if not snap:
            logger.error("오늘자(%s) Snapshot이 없습니다: %s. 먼저 --crawl-only 또는 전체 실행을 하세요.", run_date, project.id)
            raise SystemExit(2)
        all_records.extend(snap.values())
    return all_records


def main() -> int:
    args = parse_args()
    run_date = date.today().isoformat()
    file_date_placeholder = "temp"

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"[설정 오류] {exc}", file=sys.stderr)
        return 2

    logger = setup_logging(config.logs_dir, run_date.replace("-", ""))
    file_date = date.today().strftime(config.filename_date_format)
    logger.info("=== SRS 사양서 자동화 시작 (run_date=%s) ===", run_date)

    out_dir = config.base_dir / run_date
    html_dir = ensure_dir(out_dir / "html")
    pdf_dir = ensure_dir(out_dir / "pdf")
    reports_dir = ensure_dir(out_dir / "reports")
    images_root = ensure_dir(config.snapshots_dir / run_date / "_images")

    all_records: list[dict] = []
    collect_stats: list[CollectStats] = []
    exit_code = 0

    try:
        if args.diff_only:
            all_records = _load_all_records_from_disk(config, run_date, logger)
        elif args.export_only:
            all_records = _load_all_records_from_disk(config, run_date, logger)
        else:
            existing_snapshot_present = all(
                bool(load_snapshot(config.snapshots_dir, run_date, p.id)) for p in config.projects
            )
            if existing_snapshot_present and not args.force:
                logger.info("오늘자 Snapshot이 이미 존재합니다. --force 없이 재수집을 건너뜁니다.")
                all_records = _load_all_records_from_disk(config, run_date, logger)
            else:
                client = PolarionClient(
                    host=config.host,
                    token=config.token,
                    verify_ssl=config.verify_ssl,
                    timeout_seconds=config.timeout_seconds,
                    request_interval_seconds=config.request_interval_seconds,
                )
                for project in config.projects:
                    logger.info("Polarion 접속 확인: %s", project.id)
                    client.ping(project.id)
                    logger.info("Polarion 접속 성공: %s", project.id)

                    stats = CollectStats(project_id=project.id)
                    records = collect_project(client, project, config, images_root, stats)
                    collect_stats.append(stats)
                    all_records.extend(records)
                    save_snapshot(config.snapshots_dir, run_date, project.id, records)

                save_manifest(
                    config.snapshots_dir,
                    run_date,
                    {
                        "run_date": run_date,
                        "generated_at": datetime.now().isoformat(),
                        "stats": [vars(s) for s in collect_stats],
                    },
                )

            if args.crawl_only:
                logger.info("--crawl-only: 수집/Snapshot 저장까지만 수행하고 종료합니다.")
                return 0

        # ---- Partition + Render + PDF ----
        pdf_results = []
        groups = []
        fallback_records: list[dict] = []
        if not args.diff_only:
            groups, partition_warnings = assign_file_groups(all_records, config)
            known_problem_srs = set(config.known_problem_srs)
            problem_state = ProblemState.load(config.snapshots_dir)
            if known_problem_srs and not args.recheck_known_problems:
                logger.info(
                    "이미 확인된 렌더링 문제 SRS %d건 - 본문 변경이 없으면 이분 탐색을 생략합니다: %s",
                    len(known_problem_srs),
                    sorted(known_problem_srs),
                )
            elif args.recheck_known_problems:
                logger.info("--recheck-known-problems: 문제 SRS 캐시를 무시하고 전부 정상 렌더링부터 재확인합니다.")

            for group in groups:
                if not group.records:
                    logger.warning("빈 그룹 (%s) - PDF를 생성하지 않습니다.", group.display_name)
                    continue
                project_label = group.records[0]["project_id"]
                pdf_filename = build_pdf_filename(config.filename_prefix, group.display_name, file_date)
                pdf_path = pdf_dir / pdf_filename

                pdf_result, isolated = render_group_pdf_with_recovery(
                    group,
                    project_label=project_label,
                    html_dir=html_dir,
                    pdf_path=pdf_path,
                    known_problem_srs=known_problem_srs,
                    problem_state=problem_state,
                    recheck_known=args.recheck_known_problems,
                    timeout_seconds=config.pdf_timeout_seconds,
                )
                pdf_results.append(pdf_result)
                fallback_records.extend(isolated)

            problem_state.save()

            if fallback_records:
                logger.warning(
                    "렌더링 시간 초과로 서식이 단순화된 SRS %d건: %s",
                    len(fallback_records),
                    [r["uid"] for r in fallback_records],
                )

            if args.export_only:
                ok_all = all(r.ok for r in pdf_results)
                logger.info("--export-only 완료. PDF 생성 성공 여부: %s", ok_all)
                return 0 if ok_all else 1
        else:
            partition_warnings = []

        # ---- Diff ----
        previous_date = find_previous_snapshot_date(config.snapshots_dir, run_date)
        current_by_uid = {r["uid"]: r for r in all_records}
        previous_by_uid: dict[str, dict] = {}
        if previous_date:
            for project in config.projects:
                previous_by_uid.update(load_snapshot(config.snapshots_dir, previous_date, project.id))

        diffs = diff_snapshots(previous_by_uid, current_by_uid)

        pdf_sanity = []
        for pr in pdf_results:
            status = "OK" if pr.ok else "FAIL"
            pdf_sanity.append(
                {"file": pr.path.name, "status": status, "detail": f"{pr.page_count} pages, {pr.size_bytes} bytes, err={pr.error}"}
            )
        for reason, label in (
            ("bisect_timeout", "(렌더링 시간 초과 - 이분 탐색으로 신규 격리)"),
            ("known_problem_cache", "(기존 확인된 렌더링 문제 - 본문 변경 없어 서식 단순화 유지)"),
        ):
            matched = [r for r in fallback_records if r.get("render_fallback_reason") == reason]
            if matched:
                pdf_sanity.append(
                    {
                        "file": label,
                        "status": "WARN",
                        "detail": ", ".join(f"{r['uid']} ({r.get('title')})" for r in matched),
                    }
                )

        md_path, html_path = save_reports(
            reports_dir, run_date, diffs, previous_date=previous_date, current_date=run_date, pdf_sanity=pdf_sanity
        )
        logger.info("변경 리포트 생성: %s / %s", md_path, html_path)

        if args.diff_only:
            return 0

        # ---- Validation ----
        validation = validate_run(
            collect_stats=collect_stats or [CollectStats(project_id=p.id, total_items=0, expected_total=0) for p in config.projects],
            all_records=all_records,
            pdf_results=pdf_results,
            expected_pdf_count=len(groups),
            partition_warnings=partition_warnings,
        )

        if not validation.ok:
            logger.error("실행 성공 판정 실패 - 기존 지식파일 폴더는 변경하지 않습니다.")
            exit_code = 1
        elif args.dry_run:
            logger.info("--dry-run: 지식파일 폴더 반영을 생략합니다.")
        else:
            archive_and_publish(
                knowledge_folder=config.knowledge_folder,
                archive_dir=config.archive_dir,
                generated_pdfs=[pr.path for pr in pdf_results if pr.ok],
                file_date=file_date,
            )

        logger.info("=== SRS 사양서 자동화 종료 (exit_code=%d) ===", exit_code)
        return exit_code

    except PolarionApiError as exc:
        logger.error("Polarion 접근 실패: %s", exc)
        return 3
    except Exception:
        logger.error("예상치 못한 오류 발생:\n%s", traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main())
