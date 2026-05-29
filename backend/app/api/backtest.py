"""回测 API + WebSocket 进度推送。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

import csv
import io

from ..schemas.backtest import (
    BacktestCreateResponse,
    BacktestListResponse,
    BacktestMetrics,
    BacktestRequest,
    BacktestTaskOut,
    BacktestTradeOut,
    LedgerPage,
    TradesPage,
)
from ..services import backtest_service
from ..services.name_service import get_name
from ..services.strategy_service import resolve_strategy_params
from ..services.ws_manager import manager

router = APIRouter()


@router.post("/backtest", response_model=BacktestCreateResponse)
def create_backtest(req: BacktestRequest) -> BacktestCreateResponse:
    task_id = backtest_service.create_task(
        name=req.name,
        strategy_name=req.strategy,
        strategy_params=resolve_strategy_params(req.strategy, req.params),
        start_date=req.start_date,
        end_date=req.end_date,
        take_profit=req.take_profit,
        stop_loss=req.stop_loss,
        max_hold=req.max_hold,
        split_tp=req.split_tp,
        max_codes=req.max_codes,
        num_workers=req.num_workers,
        engine=req.engine,
        initial_capital=req.initial_capital,
        position_pct=req.position_pct,
        max_concurrent=req.max_concurrent,
        t_plus_1=req.t_plus_1,
    )
    return BacktestCreateResponse(task_id=task_id, status="pending")


@router.get("/backtest/history", response_model=BacktestListResponse)
def list_history(limit: int = Query(default=50, ge=1, le=500)) -> BacktestListResponse:
    tasks = backtest_service.list_tasks(limit=limit)
    return BacktestListResponse(tasks=[BacktestTaskOut.model_validate(t) for t in tasks])


@router.get("/backtest/{task_id}", response_model=BacktestTaskOut)
def get_task(task_id: str) -> BacktestTaskOut:
    t = backtest_service.get_task(task_id)
    if t is None:
        raise HTTPException(404, "task not found")
    return BacktestTaskOut.model_validate(t)


@router.get("/backtest/{task_id}/trades", response_model=TradesPage)
def list_trades(
    task_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=10000),
    sort_by: str = Query(default="score"),
    desc: bool = Query(default=True),
) -> TradesPage:
    if backtest_service.get_task(task_id) is None:
        raise HTTPException(404, "task not found")
    rows, total = backtest_service.list_trades(
        task_id, page=page, page_size=page_size, sort_by=sort_by, desc=desc
    )
    out: list[BacktestTradeOut] = []
    for r in rows:
        trade = BacktestTradeOut.model_validate(r)
        trade.name = get_name(trade.code)
        out.append(trade)
    return TradesPage(
        rows=out,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/backtest/{task_id}/ledger", response_model=LedgerPage)
def list_ledger(
    task_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=1000),
) -> LedgerPage:
    data = backtest_service.list_ledger(task_id, page=page, page_size=page_size)
    if data is None:
        raise HTTPException(404, "task not found")
    rows = []
    for r in data["rows"]:
        row = dict(r)
        row["name"] = get_name(row["code"])
        rows.append(row)
    return LedgerPage(rows=rows, **{k: data[k] for k in data if k != "rows"})


@router.get("/backtest/{task_id}/trades.csv")
def export_trades_csv(task_id: str) -> StreamingResponse:
    """导出指定任务的 trades 为 UTF-8 BOM CSV（Excel 直开中文不乱码）。"""
    if backtest_service.get_task(task_id) is None:
        raise HTTPException(404, "task not found")
    rows, _ = backtest_service.list_trades(task_id, page=1, page_size=100_000,
                                           sort_by="signal_date", desc=False)
    cols = [
        "code", "name", "signal_date", "tier", "market", "score",
        "breakout_pct", "is_limit_up", "vol_ratio", "macd", "dif",
        "pullback_pct", "ma_spread_pct", "days_since_test",
        "close_to_ma30", "close_to_low60", "body_ratio", "day_change_pct",
        "bull_ma_count", "buy_price", "buy_date", "quantity", "buy_amount",
        "sell_price", "sell_date", "sell_amount", "profit_amount",
        "sell_reason", "return_pct", "max_up_pct", "max_dn_pct", "hold_days",
    ]
    buf = io.StringIO()
    buf.write("\ufeff")  # UTF-8 BOM
    w = csv.writer(buf)
    w.writerow(cols)
    for r in rows:
        name = get_name(r.code)
        w.writerow([
            r.code, name, r.signal_date, r.tier, r.market, r.score,
            r.breakout_pct, r.is_limit_up, r.vol_ratio, r.macd, r.dif,
            r.pullback_pct, r.ma_spread_pct, r.days_since_test,
            r.close_to_ma30, r.close_to_low60, r.body_ratio, r.day_change_pct,
            r.bull_ma_count, r.buy_price, r.buy_date, r.quantity, r.buy_amount,
            r.sell_price, r.sell_date, r.sell_amount, r.profit_amount,
            r.sell_reason, r.return_pct, r.max_up_pct, r.max_dn_pct, r.hold_days,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="trades_{task_id}.csv"'},
    )


@router.get("/backtest/{task_id}/metrics", response_model=BacktestMetrics)
def get_metrics(task_id: str) -> BacktestMetrics:
    m = backtest_service.get_metrics(task_id)
    if m is None:
        raise HTTPException(404, "task not found")
    return BacktestMetrics(**m)


@router.delete("/backtest/{task_id}")
def delete_task(task_id: str) -> dict:
    if not backtest_service.delete_task(task_id):
        raise HTTPException(404, "task not found")
    return {"deleted": task_id}


# ---------------- WebSocket ----------------

ws_router = APIRouter()


@ws_router.websocket("/ws/backtest/{task_id}")
async def ws_backtest(ws: WebSocket, task_id: str) -> None:
    await manager.connect(task_id, ws)
    try:
        # 立即推一次当前状态，避免 race condition（任务可能已经完成）
        t = backtest_service.get_task(task_id)
        if t is None:
            await ws.send_json({"type": "error", "task_id": task_id, "error": "task not found"})
            await ws.close()
            return
        await ws.send_json({
            "type": "snapshot",
            "task_id": task_id,
            "status": t.status,
            "done": t.progress,
            "total": t.total,
            "trade_count": t.trade_count,
            "summary": t.summary,
            "error": t.error,
            "elapsed_seconds": t.elapsed_seconds,
        })

        # 保持连接直到客户端断开（后台广播由 manager 主动 push）
        while True:
            try:
                _ = await ws.receive_text()  # 心跳/ack；忽略内容
            except WebSocketDisconnect:
                break
    finally:
        manager.disconnect(task_id, ws)
