"""把残留的 running/pending 状态改为 cancelled。"""
import sqlite3
from pathlib import Path

DB = Path(r"C:\Users\66470\Desktop\stockmodel\data\db\stockmodel.db")

c = sqlite3.connect(DB)
n = c.execute(
    "UPDATE backtest_task SET status='cancelled' WHERE status IN ('running','pending')"
).rowcount
c.commit()
c.close()
print(f"cancelled {n} stale tasks")
