"""回测后台任务编排。

启动时立即返回 task_id；任务在 daemon 线程中执行；
每 100 只股票推一次进度（done/total/trade_count）到 WebSocket。

进度只在内存中维护（_running_progress 全局 dict），任务完成时统一落库 + summary，
避免每次 progress 都触发 SQLite 写入造成抖动。
"""
from __future__ import annotations

import multiprocessing as mp
import sys
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime
from queue import Empty
from typing import Any

import pandas as pd
from sqlalchemy import select

from model.backtest import BacktestConfig, run_backtest
from model.backtest.engine import compute_extended_metrics
from model.strategies import get_strategy

from ..core.database import session_scope
from ..models.backtest import BacktestTask, BacktestTrade, TaskStatus
from .cache_service import get_cache
from .ws_manager import manager


# 全局进程内进度表：task_id -> {done, total, trade_count}
_running_progress: dict[str, dict[str, Any]] = {}
_progress_lock = threading.Lock()


def _set_progress(task_id: str, done: int, total: int, trade_count: int) -> None:
    with _progress_lock:
        _running_progress[task_id] = {
            "done": done,
            "total": total,
            "trade_count": trade_count,
        }


def _clear_progress(task_id: str) -> None:
    with _progress_lock:
        _running_progress.pop(task_id, None)


def _merge_progress(t: BacktestTask) -> None:
    """把内存进度合并到 ORM 对象（task 已 expunge 后再调用）。"""
    with _progress_lock:
        mem = _running_progress.get(t.id)
    if mem:
        t.progress = mem["done"]
        t.total = mem["total"]
        t.trade_count = mem["trade_count"]


# task_id -> 仅运行时使用的额外参数（不持久化）
_task_extras: dict[str, dict[str, Any]] = {}


def create_task(
    *,
    name: str | None,
    strategy_name: str,
    strategy_params: dict,
    start_date: str,
    end_date: str,
    take_profit: float,
    stop_loss: float,
    max_hold: int,
    split_tp: float | None,
    max_codes: int | None = None,
    num_workers: int | None = None,
    engine: str = "legacy",
    initial_capital: float = 1_000_000.0,
    position_pct: float = 1.0,
    max_concurrent: int = 1,
    t_plus_1: bool = True,
) -> str:
    """创建任务记录 + 在后台线程中启动回测；返回 task_id。"""
    task_id = uuid.uuid4().hex[:12]
    with session_scope() as s:
        task = BacktestTask(
            id=task_id,
            name=name,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            start_date=start_date,
            end_date=end_date,
            take_profit=take_profit,
            stop_loss=stop_loss,
            max_hold=max_hold,
            split_tp=split_tp,
            initial_capital=initial_capital,
            position_pct=position_pct,
            max_concurrent=max_concurrent,
            t_plus_1=t_plus_1,
            status=TaskStatus.pending.value,
        )
        s.add(task)
    extras: dict[str, Any] = {}
    if max_codes:
        extras["max_codes"] = max_codes
    if num_workers:
        extras["num_workers"] = num_workers
    if engine and engine != "legacy":
        extras["engine"] = engine
    if extras:
        _task_extras[task_id] = extras

    workers = extras.get("num_workers") or 0
    use_subprocess = sys.platform == "win32" and int(workers) > 1

    if use_subprocess:
        progress_q: mp.Queue = mp.Queue()
        proc = mp.Process(
            target=_spawn_backtest_worker,
            args=(task_id, dict(extras), progress_q),
            daemon=False,  # 子进程内还要 ProcessPoolExecutor，不能是 daemon
            name=f"backtest-proc-{task_id}",
        )
        proc.start()
        threading.Thread(
            target=_relay_progress_queue,
            args=(task_id, progress_q, proc),
            daemon=True,
            name=f"backtest-relay-{task_id}",
        ).start()
    else:
        t = threading.Thread(
            target=execute_backtest_task,
            args=(task_id,),
            kwargs={"extras": extras, "progress_queue": None},
            daemon=True,
            name=f"backtest-{task_id}",
        )
        t.start()
    return task_id


def _spawn_backtest_worker(task_id: str, extras: dict[str, Any], progress_queue: mp.Queue) -> None:
    from .backtest_worker import run

    run(task_id, extras, progress_queue)


def _relay_progress_queue(task_id: str, progress_queue: mp.Queue, proc: mp.Process) -> None:
    """子进程 progress/done/error → 主进程 WebSocket。"""
    try:
        while proc.is_alive() or not progress_queue.empty():
            try:
                msg = progress_queue.get(timeout=0.5)
            except Empty:
                continue
            msg_type = msg.get("type")
            if msg_type == "progress":
                _set_progress(
                    task_id,
                    int(msg["done"]),
                    int(msg["total"]),
                    int(msg["trade_count"]),
                )
                manager.broadcast(task_id, msg)
            elif msg_type in ("done", "error"):
                manager.broadcast(task_id, msg)
                break
    finally:
        proc.join(timeout=5)
        _clear_progress(task_id)


def execute_backtest_task(
    task_id: str,
    *,
    extras: dict[str, Any] | None = None,
    progress_queue: mp.Queue | None = None,
) -> None:
    """执行单个回测任务（线程或子进程内调用）。"""
    cache = get_cache()

    with session_scope() as s:
        task = s.get(BacktestTask, task_id)
        if task is None:
            return
        task.status = TaskStatus.running.value
        task.started_at = datetime.utcnow()
        s.flush()
        task_extras = extras if extras is not None else _task_extras.pop(task_id, {})
        cfg = BacktestConfig(
            start_date=task.start_date,
            end_date=task.end_date,
            strategy_name=task.strategy_name,
            strategy_params=task.strategy_params,
            take_profit=task.take_profit,
            stop_loss=task.stop_loss,
            max_hold=task.max_hold,
            split_tp=task.split_tp,
            max_codes=task_extras.get("max_codes"),
            num_workers=task_extras.get("num_workers"),
            engine=task_extras.get("engine", "legacy"),
            initial_capital=task.initial_capital,
            position_pct=task.position_pct,
            max_concurrent=task.max_concurrent,
            t_plus_1=getattr(task, "t_plus_1", True),
        )

    t0 = time.time()
    try:
        strategy = get_strategy(cfg.strategy_name, cfg.strategy_params)

        def progress_cb(done: int, total: int, trade_count: int) -> None:
            payload = {
                "type": "progress",
                "task_id": task_id,
                "done": done,
                "total": total,
                "trade_count": trade_count,
                "elapsed_seconds": round(time.time() - t0, 2),
            }
            if progress_queue is not None:
                progress_queue.put(payload)
            else:
                _set_progress(task_id, done, total, trade_count)
                manager.broadcast(task_id, payload)

        trades_df, summary = run_backtest(cfg, strategy, cache, progress_cb=progress_cb)

        # 落库 trades + 汇总
        with session_scope() as s:
            t = s.get(BacktestTask, task_id)
            if t is None:
                return
            if not trades_df.empty:
                rows = trades_df.to_dict("records")
                s.bulk_insert_mappings(
                    BacktestTrade,
                    [{**r, "task_id": task_id} for r in rows],
                )
            t.summary = asdict(summary)
            t.trade_count = len(trades_df)
            t.status = TaskStatus.done.value
            t.finished_at = datetime.utcnow()
            t.elapsed_seconds = round(time.time() - t0, 2)

        done_payload = {
            "type": "done",
            "task_id": task_id,
            "summary": asdict(summary),
            "trade_count": len(trades_df),
            "elapsed_seconds": round(time.time() - t0, 2),
        }
        if progress_queue is not None:
            progress_queue.put(done_payload)
        else:
            manager.broadcast(task_id, done_payload)

    except Exception as e:  # noqa: BLE001 后台任务必须吞掉所有异常
        with session_scope() as s:
            t = s.get(BacktestTask, task_id)
            if t is not None:
                t.status = TaskStatus.error.value
                t.error = f"{type(e).__name__}: {e}"
                t.finished_at = datetime.utcnow()
                t.elapsed_seconds = round(time.time() - t0, 2)
        err_payload = {
            "type": "error",
            "task_id": task_id,
            "error": f"{type(e).__name__}: {e}",
        }
        if progress_queue is not None:
            progress_queue.put(err_payload)
        else:
            manager.broadcast(task_id, err_payload)
    finally:
        if progress_queue is None:
            _clear_progress(task_id)


def list_tasks(limit: int = 50) -> list[BacktestTask]:
    with session_scope() as s:
        rows = s.execute(
            select(BacktestTask).order_by(BacktestTask.created_at.desc()).limit(limit)
        ).scalars().all()
        for r in rows:
            s.expunge(r)
    # 离开 session 后合并内存进度
    for r in rows:
        _merge_progress(r)
    return list(rows)


def get_task(task_id: str) -> BacktestTask | None:
    with session_scope() as s:
        t = s.get(BacktestTask, task_id)
        if t is not None:
            s.expunge(t)
    if t is not None:
        _merge_progress(t)
    return t


def list_trades(
    task_id: str,
    *,
    page: int = 1,
    page_size: int = 50,
    sort_by: str = "score",
    desc: bool = True,
) -> tuple[list[BacktestTrade], int]:
    with session_scope() as s:
        total = s.query(BacktestTrade).filter(BacktestTrade.task_id == task_id).count()
        col = getattr(BacktestTrade, sort_by, BacktestTrade.score)
        order = col.desc() if desc else col.asc()
        rows = (
            s.query(BacktestTrade)
            .filter(BacktestTrade.task_id == task_id)
            .order_by(order)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        for r in rows:
            s.expunge(r)
        return rows, total


def _build_trades_dataframe(
    rows: list[BacktestTrade],
    *,
    initial_capital: float,
    position_pct: float,
    max_concurrent: int,
    t_plus_1: bool,
) -> pd.DataFrame:
    """把 ORM 成交记录转为 metrics/ledger 所需的 DataFrame。"""
    if not rows:
        return pd.DataFrame()

    records = [
        {
            "code": r.code,
            "signal_date": r.signal_date,
            "buy_date": r.buy_date,
            "buy_price": r.buy_price,
            "sell_date": r.sell_date,
            "sell_price": r.sell_price,
            "sell_reason": r.sell_reason,
            "return_pct": r.return_pct,
            "quantity": r.quantity,
            "buy_amount": r.buy_amount,
            "sell_amount": r.sell_amount,
            "profit_amount": r.profit_amount,
        }
        for r in rows
    ]
    df = pd.DataFrame(records)
    if (df["quantity"] == 0).all() and initial_capital > 0:
        from model.backtest.position import apply_portfolio_simulation

        df, _ = apply_portfolio_simulation(
            df,
            initial_capital=initial_capital,
            position_pct=position_pct,
            max_concurrent=max_concurrent,
            t_plus_1=t_plus_1,
        )
    return df


def list_ledger(
    task_id: str,
    *,
    page: int = 1,
    page_size: int = 100,
) -> dict | None:
    """按时间排序的买/卖流水（每笔 trade 展开为 buy + sell 两行）。"""
    from model.backtest.position import trades_to_ledger

    with session_scope() as s:
        task = s.get(BacktestTask, task_id)
        if task is None:
            return None
        rows = (
            s.query(BacktestTrade)
            .filter(BacktestTrade.task_id == task_id)
            .all()
        )
        ic = float(task.initial_capital or 0)
        pos_pct = float(task.position_pct or 1.0)
        max_conc = int(task.max_concurrent or 1)
        t_plus_1 = bool(getattr(task, "t_plus_1", True))
        summary = task.summary or {}

    if not rows:
        return {
            "rows": [],
            "total": 0,
            "page": page,
            "page_size": page_size,
            "initial_capital": ic,
            "total_profit": 0.0,
            "final_capital": ic,
        }

    df = _build_trades_dataframe(
        rows,
        initial_capital=ic,
        position_pct=pos_pct,
        max_concurrent=max_conc,
        t_plus_1=t_plus_1,
    )

    ledger = trades_to_ledger(df)
    total = len(ledger)
    start = (page - 1) * page_size
    page_rows = ledger[start: start + page_size]
    total_profit = float(summary.get("total_profit", df["profit_amount"].sum()))
    return {
        "rows": page_rows,
        "total": total,
        "page": page,
        "page_size": page_size,
        "initial_capital": ic,
        "total_profit": total_profit,
        "final_capital": ic + total_profit,
    }


def delete_task(task_id: str) -> bool:
    with session_scope() as s:
        t = s.get(BacktestTask, task_id)
        if t is None:
            return False
        s.delete(t)
        return True


def get_metrics(task_id: str) -> dict | None:
    """计算指定任务的扩展指标（夏普/Calmar/月度/净值曲线）。"""
    with session_scope() as s:
        task = s.get(BacktestTask, task_id)
        if task is None:
            return None
        rows = s.query(BacktestTrade).filter(BacktestTrade.task_id == task_id).all()
        ic = float(task.initial_capital or 0)
        pos_pct = float(task.position_pct or 1.0)
        max_conc = int(task.max_concurrent or 1)
        t_plus_1 = bool(getattr(task, "t_plus_1", True))

    df = _build_trades_dataframe(
        rows,
        initial_capital=ic,
        position_pct=pos_pct,
        max_concurrent=max_conc,
        t_plus_1=t_plus_1,
    )
    return compute_extended_metrics(df, initial_capital=ic)
