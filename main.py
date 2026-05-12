import os
import requests
from datetime import date, timedelta
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

FINMIND_TOKEN = os.environ.get("FINMIND_TOKEN", "")
FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"


def finmind_get(dataset: str, stock_id: str, start_date: str, end_date: str) -> list:
    """呼叫 FinMind REST API，回傳 data 陣列"""
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "end_date": end_date,
        "token": FINMIND_TOKEN,
    }
    try:
        resp = requests.get(FINMIND_BASE, params=params, timeout=30)
        resp.raise_for_status()
        body = resp.json()
        if body.get("status") == 200:
            return body.get("data", [])
        print(f"FinMind error for {stock_id}: {body.get('msg')}")
        return []
    except Exception as e:
        print(f"FinMind request failed for {stock_id}: {e}")
        return []


# ── 股票名稱快取，避免重複查詢 ──────────────────────────────
_name_cache: dict[str, str] = {}

def get_stock_name(stock_id: str) -> str:
    if stock_id in _name_cache:
        return _name_cache[stock_id]
    try:
        params = {"dataset": "TaiwanStockInfo", "token": FINMIND_TOKEN}
        resp = requests.get(FINMIND_BASE, params=params, timeout=15)
        body = resp.json()
        for item in body.get("data", []):
            _name_cache[item["stock_id"]] = item["stock_name"]
    except Exception as e:
        print(f"Fetch stock name failed: {e}")
    return _name_cache.get(stock_id, stock_id)


# ── Models ──────────────────────────────────────────────────

class QuoteResponse(BaseModel):
    symbol: str
    price: float
    name: str

class KbarResponse(BaseModel):
    date: str
    close: float


# ── /api/quote  (用最近一個交易日的收盤價模擬即時報價) ──────

@app.get("/api/quote", response_model=QuoteResponse)
def get_quote(symbol: str):
    # 往前查 7 天，確保能涵蓋假日
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=7)).isoformat()
    rows = finmind_get("TaiwanStockPrice", symbol, start, end)
    if not rows:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的報價資料")
    latest = rows[-1]  # 最後一筆即最新交易日
    name = get_stock_name(symbol)
    return QuoteResponse(symbol=symbol, price=float(latest["close"]), name=name)


# ── /api/kbars  (歷史日 K 線) ───────────────────────────────

@app.get("/api/kbars", response_model=List[KbarResponse])
def get_kbars(symbol: str, start: str, end: str):
    rows = finmind_get("TaiwanStockPrice", symbol, start, end)
    result = []
    for row in rows:
        try:
            result.append(KbarResponse(date=row["date"], close=float(row["close"])))
        except Exception:
            continue
    return result


# ── 健康檢查 ─────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "token_set": bool(FINMIND_TOKEN)}
