# A 股回测平台

本地化 A 股形态识别 + 回测可视化平台。读通达信 `.day` 历史数据，扫描洗盘突破等形态，多进程并行全市场回测，输出夏普 / Calmar / 月度收益热力图，配套多因子 IC 分析与参数对比页。

> 个人单机版，前后端分离。后端纯本地（FastAPI + SQLite）；前端 React 18 + Ant Design。

---

## 项目结构

```
curosr/                          仓库根
├── model/                        算法层（纯 Python，无网络）
│   ├── data/
│   │   ├── tdx_parser.py         通达信 .day 二进制解析（struct + numpy）
│   │   ├── indicators.py         MA/MACD/Volume + 向量化 ma_spread_pct
│   │   └── cache.py              DataCache：Parquet 持久化 + 懒加载 + load_no_cache
│   ├── strategies/
│   │   ├── base.py               Strategy 基类 + ScanResult dataclass
│   │   └── breakout_washout.py   洗盘突破策略（13 条规则 + 综合评分）
│   ├── backtest/
│   │   ├── engine.py             串行 + multiprocessing 并行 + 风险指标
│   │   ├── parallel.py           ProcessPoolExecutor worker
│   │   ├── simulate_legacy.py    手写单笔模拟（精确，sl/tp 用 high/low）
│   │   └── vbt_engine.py         VectorBT 引擎（实验性，sl/tp 用 close）
│   ├── factor_analysis/
│   │   ├── ic.py                 Spearman 秩相关 IC
│   │   ├── quantile.py           N 分位收益统计
│   │   └── scoring.py            评分公式权重
│   └── diagnose/
│       └── check.py              逐规则 PASS/FAIL 诊断
│
├── backend/                      FastAPI 服务层
│   └── app/
│       ├── main.py               入口；挂载 /api 与 /ws 路由
│       ├── api/
│       │   ├── health.py         /api/health
│       │   ├── scan.py           /api/strategies, /api/scan
│       │   ├── diagnose.py       /api/diagnose/{code}, /api/kline/{code}
│       │   ├── data.py           /api/data/stats, /api/data/build
│       │   ├── backtest.py       /api/backtest（POST/GET/DELETE）+ /metrics + /trades.csv
│       │   │                     + WebSocket /ws/backtest/{task_id}
│       │   └── factor.py         /api/factor/analysis
│       ├── core/                 配置 + SQLAlchemy 引擎
│       ├── models/               ORM：BacktestTask / BacktestTrade
│       ├── schemas/              Pydantic 模型
│       └── services/
│           ├── cache_service.py  缓存构建后台任务
│           ├── backtest_service.py 回测任务编排（线程池 + 内存进度 + SQLite 落库）
│           ├── factor_service.py
│           ├── ws_manager.py     WebSocket 广播器
│           └── name_service.py   股票名称缓存
│
├── Web/                          React 18 + Vite + TS 前端
│   └── src/
│       ├── pages/
│       │   ├── Health.tsx        系统状态 / 数据概览
│       │   ├── Scan.tsx          策略扫描（动态参数表单 + 结果表）
│       │   ├── Diagnose.tsx      个股诊断（K 线图 + 13 规则 PASS/FAIL）
│       │   ├── Backtest.tsx      回测主页（参数 + 进度 WS + 净值 + 月度热力图 + trades）
│       │   ├── Factor.tsx        多因子分析（IC 表 + 因子×分位 热力图）
│       │   ├── Compare.tsx       双任务并排对比（指标 / 净值叠加 / IC 对照）
│       │   └── DataManage.tsx    缓存管理 + 单股查询
│       ├── components/
│       │   ├── KlineChart.tsx          TradingView Lightweight Charts
│       │   ├── EquityCurve.tsx         单/多曲线净值图（ECharts）
│       │   ├── MonthlyHeatmap.tsx
│       │   ├── FactorQuantileHeatmap.tsx
│       │   ├── TradesTable.tsx
│       │   ├── ParamForm.tsx           动态参数表单
│       │   └── RulesTable.tsx
│       ├── api/                  axios + WebSocket 封装 + TS 类型
│       └── store/                Zustand store（暗色主题持久化）
│
├── scripts/                      一次性运维脚本
│   ├── build_stock_names.py      从沪深交易所拉取股票名映射
│   ├── bench_backtest.py         全市场并行回测基准
│   ├── bench_scan.py             串行扫描基准
│   ├── verify_parallel.py        串/并行结果一致性验证
│   ├── compare_vbt_legacy.py     vbt vs legacy 引擎语义对比
│   ├── test_phase3_full.py       端到端：回测 + metrics + factor 全链路
│   ├── test_factor.py            因子分析 API 烟雾测试
│   ├── test_parallel_api.py      并行回测 API 烟雾测试
│   ├── cleanup_stale_tasks.py    重置卡死的 running/pending 任务
│   └── smoke_test.py             小样本回归（5 个已知样本）
│
└── pyproject.toml                依赖（uv 管理；可选 backtest extra 含 vectorbt + numba）
```

---

## 数据流

```
通达信 .day (5500+ 文件)
        │
        ▼ tdx_parser.parse_day_file
   raw DataFrame (date/open/high/low/close/volume)
        │
        ▼ indicators.add_indicators
   带指标的 DataFrame (+ ma5/10/20/30/60, dif/dea/macd, vol_ma5/20, ma_spread_pct)
        │
        ▼ cache.DataCache.save  (一次性，写入 ../data/cache/{sh,sz}/*.parquet)
   Parquet 列存
        │  load_no_cache (回测/扫描时用)
        ▼
   ┌─────────────┬────────────────┬──────────────┐
   ▼             ▼                ▼              ▼
 strategy.scan  diagnose.check  simulate(legacy/vbt)  factor.ic_table
   │             │                │              │
   ▼             ▼                ▼              ▼
 ScanResult   DiagnoseReport    SimResult      ICRow + Quantile

回测任务：scan(扫所有日期) → 收集 hits → simulate_batch（按 code 批量）
            → SQLite (BacktestTask + BacktestTrade)
            → WebSocket 推 progress → 前端 Backtest 页
            → /metrics（夏普/Calmar/月度热力图）→ 前端图表
            → /factor/analysis → 前端因子分析页
            → /trades.csv → 浏览器下载
```

---

## 性能数据

| 场景 | 配置 | 耗时 |
|---|---|---|
| 全市场扫描 + 模拟 | 串行（单进程） | **256s** |
| 全市场扫描 + 模拟 | multiprocessing 6 worker | **57s** |
| 1500 只 + API 路径 | 6 worker | **24s** |
| 1500 只 + vbt 引擎 | 6 worker（含 numba JIT 6×5.4s） | 17s |

multiprocessing 加速 4.5x；瓶颈是外层 `5481 codes × 100 days = 548k` 次 scan，已通过向量化 `ma_spread_pct` 消除内层 `apply axis=1`。

---

## 快速启动

### 安装依赖

```powershell
# Python（默认含 fastapi / pandas / pyarrow）
uv sync

# 可选：装 VectorBT + Numba（实验性引擎）
uv sync --extra backtest

# 前端
cd Web
npm install --registry=https://registry.npmmirror.com
```

### 配置数据目录

把通达信 `.day` 文件放到 `../data/raw/sh/lday/*.day` 与 `../data/raw/sz/lday/*.day`（仓库外）。配置可在 `backend/app/core/config.py` 调整。

### 启动后端

```powershell
uv run uvicorn backend.app.main:app --reload --port 8000
```

打开 http://localhost:8000/docs 看 OpenAPI。

### 启动前端

```powershell
cd Web
npm run dev
```

打开 http://localhost:5173

### 首次构建缓存

进入 `数据管理` 或 `仪表盘` 页面，点 **重建全市场缓存** —— 5–8 分钟生成 5481 只 Parquet（约 350 MB）。

### 拉取股票名称（5500+ 只）

```powershell
uv run python scripts/build_stock_names.py
```

写入 `../data/cache/stock_names.json`，前端各页就能在代码旁显示中文名了。

---

## API 速查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 后端 + 数据状态 |
| GET | `/api/strategies` | 列出可用策略 + 参数 schema |
| POST | `/api/scan` | 给定日期跑一次扫描 |
| GET | `/api/diagnose/{code}?date=` | 个股逐规则诊断 |
| GET | `/api/kline/{code}?last_n=` | K 线 + MA + 成交量 |
| GET | `/api/data/stats` | 缓存统计 |
| POST | `/api/data/build` | 触发重建缓存（异步） |
| GET | `/api/data/build/status` | 查询构建进度 |
| POST | `/api/backtest` | 创建回测任务（含 `engine: legacy/vectorbt`、`num_workers`、`max_codes`） |
| GET | `/api/backtest/history?limit=` | 历史任务列表 |
| GET | `/api/backtest/{id}` | 任务详情 |
| GET | `/api/backtest/{id}/trades` | 成交记录分页 |
| GET | `/api/backtest/{id}/metrics` | 月度热力图 + 净值曲线 |
| GET | `/api/backtest/{id}/trades.csv` | 导出 CSV（UTF-8 BOM，Excel 直开不乱码） |
| DELETE | `/api/backtest/{id}` | 删除任务 |
| GET | `/api/factor/analysis?task_id=` | IC 表 + 因子×分位 收益结构 |
| WS | `/ws/backtest/{id}` | 实时进度推送 |

---

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | FastAPI + uvicorn + SQLAlchemy 2 + SQLite |
| 回测 | 自写 multiprocessing 并行 + 可选 VectorBT |
| 数据 | PyArrow Parquet + 通达信二进制解析 |
| 包管 | uv（Python） / npm（Node） |
| 前端 | React 18 + Vite + TypeScript + Ant Design 5 |
| 图表 | ECharts（指标/热力图）+ TradingView Lightweight Charts（K 线） |
| 状态 | TanStack Query（服务端状态）+ Zustand（客户端状态，含暗色主题） |

---

## 设计要点

### multiprocessing 并行

- `ProcessPoolExecutor` + `chunk_size=100`（28 chunks / 5481 只），进度推送平滑
- 每个 worker 进程内 `_WORKER_STATE` 缓存 `DataCache + Strategy` 实例，避免重复初始化
- 主线程 `as_completed` 接收 chunk 结果，把内存进度合并写 SQLite（避免高频 DB 写造成锁表）
- WebSocket 由主线程的 `manager.broadcast` 异步推送（捕获 asyncio.run_coroutine_threadsafe）

### 风险指标

净值曲线用 trade-by-trade 等权累加（不复利），避免日内复利造成 CAGR 虚高 1000%+：

```python
daily_pct = trades.groupby(sell_date)[return_pct].mean()
cum_pct = daily_pct.cumsum()
sharpe  = (daily_pct/100).mean() / (daily_pct/100).std() * sqrt(252)
max_dd  = (cum_pct - cum_pct.cummax()).min()
cagr_pct = cum_pct.iloc[-1] * 365 / span_days
calmar  = cagr_pct / |max_dd|
```

### 引擎切换

`BacktestConfig.engine`：

- `"legacy"`（默认）：手写循环。`sl/tp` 用 `high/low` 触发，与人工交易语义一致
- `"vectorbt"`（实验）：VectorBT `Portfolio.from_signals`。`sl/tp` 仅基于 `close`，结果与 legacy 偏差 5-10%，但具备未来参数寻优潜力

worker 通过 `cfg["engine"]` 条件 `import vectorbt`，不用时不加载（避免 5s+ JIT 编译开销）。

### 因子分析

13 个因子（综合评分、突破幅度、量比、MACD、回踩幅度、均线粘合、收盘相对 MA30/60 日低、实体比、当日涨幅、多头组数等）：

- IC：Spearman 秩相关 vs 单笔收益 / 最大上涨
- 分位：N 分位组内 平均/中位/胜率/大赚率
- 热力图：13 因子 × 5 分位 一图直观对比

---

## 已知限制 / 后续

- VectorBT 引擎语义不严格匹配 legacy（前端已 tooltip 标注实验性）
- 缓存增量更新尚未实现（每次重建都是全量）
- 股票名称依赖 akshare，遇企业改名需重跑 `build_stock_names.py`
- 暂未支持港股 / 美股；通达信数据格式仅适用 A 股 6 位代码
- `split_tp`（分批止盈）在 vectorbt 引擎上会自动 fallback 到 legacy

---

## 开发常用脚本

```powershell
# 串/并行结果一致性验证
uv run python scripts/verify_parallel.py

# 全市场并行基准
$env:WORKERS = "8"; uv run python scripts/bench_backtest.py

# 端到端测试（回测 + metrics + factor + 引擎对比）
uv run python scripts/test_phase3_full.py

# 重置卡死的 running 任务
uv run python scripts/cleanup_stale_tasks.py

# 5 个已知样本回归
uv run python scripts/smoke_test.py
```
