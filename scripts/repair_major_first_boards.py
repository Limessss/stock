"""按实际三连板重算历史主要首板；适用于没有人工勾选的历史数据。

预览：python -m scripts.repair_major_first_boards
执行：python -m scripts.repair_major_first_boards --apply
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from sqlalchemy import select

from backend.app.core.database import SessionLocal
from backend.app.core.time_utils import utc_now
from backend.app.models.sentiment import SentimentDaily, SentimentLadderItem
from backend.app.services import sentiment_service


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="备份后应用修复；默认仅预览")
    args = parser.parse_args()
    with SessionLocal() as session:
        changes = sentiment_service.plan_major_first_board_repair(session)
        report = {
            "add": sum(change["after"] for change in changes),
            "remove": sum(not change["after"] for change in changes),
            "changes": changes,
            "applied": False,
        }
        if args.apply and changes:
            # 保存逐条修改前后的值，确保历史标记可以恢复。
            log_dir = Path(__file__).resolve().parents[1] / ".codex-logs"
            log_dir.mkdir(exist_ok=True)
            backup = log_dir / f"major-first-boards-{utc_now().strftime('%Y%m%d-%H%M%S-%f')}.json"
            with backup.open("x", encoding="utf-8") as output:
                json.dump(report, output, ensure_ascii=False, indent=2)
            days = session.scalars(select(SentimentDaily)).all()
            negative_before = [sentiment_service._negative_feedback_for_day(session, day) for day in days]
            for change in changes:
                item = session.get(SentimentLadderItem, change["id"])
                if item is None or item.is_major_first_board != change["before"]:
                    raise RuntimeError("修复期间数据发生变化，请重新预览")
                item.is_major_first_board = change["after"]
                item.updated_at = utc_now()
            session.flush()
            negative_after = [sentiment_service._negative_feedback_for_day(session, day) for day in days]
            if negative_after != negative_before:
                raise RuntimeError("负反馈结果发生变化，取消本次修复")
            session.commit()
            report.update(applied=True, backup=str(backup), negative_feedback_unchanged=True)
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
