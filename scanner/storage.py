import sqlite3
import time
from pathlib import Path
from typing import List, Optional, Dict, Any

import pandas as pd

from .features import FeatureVector

_DATA_DIR = Path('data')
_DB_PATH = _DATA_DIR / 'pump.db'


def init_db(path: Path | str = _DB_PATH) -> None:
    """Initialize database and ensure tables exist."""
    _DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            vsr REAL,
            pm REAL,
            probability REAL,
            ts INTEGER
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_id INTEGER,
            action TEXT,
            ts INTEGER
        )
        """
    )
    conn.commit()
    conn.close()


def _parquet_path() -> Path:
    return _DATA_DIR / f"signals_{time.strftime('%Y%m')}.parquet"


def _append_parquet(df: pd.DataFrame) -> None:
    path = _parquet_path()
    if path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_parquet(path, index=False)


def save_signal(fv: FeatureVector, prob: float, db_path: Path | str = _DB_PATH) -> int:
    """Insert signal and duplicate to Parquet. Returns row id."""
    init_db(db_path)
    ts = int(time.time())
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO signals(symbol, vsr, pm, probability, ts) VALUES(?,?,?,?,?)",
        (fv.symbol, fv.vsr, fv.pm, prob, ts),
    )
    signal_id = cur.lastrowid
    conn.commit()
    conn.close()

    df = pd.DataFrame([
        {
            "id": signal_id,
            "symbol": fv.symbol,
            "vsr": fv.vsr,
            "pm": fv.pm,
            "probability": prob,
            "ts": ts,
        }
    ])
    _append_parquet(df)
    return signal_id


def save_action(signal_id: int, action: str, db_path: Path | str = _DB_PATH) -> None:
    """Insert user action linked to a signal."""
    init_db(db_path)
    ts = int(time.time())
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO actions(signal_id, action, ts) VALUES(?,?,?)",
        (signal_id, action, ts),
    )
    conn.commit()
    conn.close()


def fetch_signals(limit: Optional[int] = None, db_path: Path | str = _DB_PATH) -> List[Dict[str, Any]]:
    """Return signals ordered by newest first."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    sql = "SELECT id, symbol, vsr, pm, probability, ts FROM signals ORDER BY ts DESC"
    if limit:
        cur.execute(sql + " LIMIT ?", (limit,))
    else:
        cur.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def fetch_actions(signal_id: int, db_path: Path | str = _DB_PATH) -> List[Dict[str, Any]]:
    """Return actions for a given signal."""
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, signal_id, action, ts FROM actions WHERE signal_id=? ORDER BY ts",
        (signal_id,),
    )
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows
