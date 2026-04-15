from datetime import datetime
from typing import Any

import akshare as ak
import pandas as pd
from fastapi import FastAPI, HTTPException, Query


app = FastAPI(
    title="guwang-ak-api",
    description="AKShare-backed endpoints for A-share market data.",
    version="0.1.0",
)


def normalize_value(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    normalized = df.copy()
    normalized = normalized.where(pd.notnull(normalized), None)
    return [
        {column: normalize_value(value) for column, value in record.items()}
        for record in normalized.to_dict(orient="records")
    ]


def normalize_a_share_symbol(symbol: str) -> str:
    if symbol.startswith(("sh", "sz", "bj")):
        return symbol
    if symbol.startswith(("5", "6", "9")):
        return f"sh{symbol}"
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    return f"sz{symbol}"


@app.get("/a-share/spot")
def get_a_share_spot() -> dict[str, Any]:
    try:
        df = ak.stock_zh_a_spot_em()
    except Exception:
        try:
            # Fallback to the legacy spot interface when the EM source is unstable.
            df = ak.stock_zh_a_spot()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AKShare spot request failed: {exc}") from exc

    return {"count": len(df), "items": dataframe_to_records(df)}


@app.get("/a-share/hist")
def get_a_share_hist(
    symbol: str = Query(..., description="A-share symbol, e.g. 000001"),
    period: str = Query("daily", pattern="^(daily|weekly|monthly)$"),
    start_date: str = Query(..., description="Start date in YYYYMMDD format"),
    end_date: str = Query(..., description="End date in YYYYMMDD format"),
    adjust: str = Query("", description="Adjust type: qfq, hfq, or empty string"),
) -> dict[str, Any]:
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol,
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
    except Exception:
        if period != "daily":
            raise HTTPException(
                status_code=502,
                detail="AKShare history request failed and fallback is only available for daily period",
            )

        try:
            tx_symbol = normalize_a_share_symbol(symbol)
            df = ak.stock_zh_a_hist_tx(
                symbol=tx_symbol,
                start_date=start_date,
                end_date=end_date,
                adjust=adjust,
            )
            df = df.rename(
                columns={
                    "date": "日期",
                    "open": "开盘",
                    "close": "收盘",
                    "high": "最高",
                    "low": "最低",
                    "amount": "成交量",
                }
            )
            df.insert(1, "股票代码", symbol)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"AKShare history request failed: {exc}") from exc

    if df.empty:
        raise HTTPException(status_code=404, detail="No historical data found for the given query")

    return {
        "symbol": symbol,
        "period": period,
        "start_date": start_date,
        "end_date": end_date,
        "adjust": adjust,
        "count": len(df),
        "items": dataframe_to_records(df),
    }


@app.get("/zt-pool")
def get_zt_pool(
    date: str = Query(..., description="Trading date in YYYYMMDD format"),
) -> dict[str, Any]:
    try:
        df = ak.stock_zt_pool_em(date=date)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AKShare zt pool request failed: {exc}") from exc

    return {"date": date, "count": len(df), "items": dataframe_to_records(df)}
