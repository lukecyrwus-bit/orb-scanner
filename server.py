import os
import requests
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = FastAPI()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SECRET_TOKEN = os.getenv("SECRET_TOKEN")

MIN_SETUPS = 5
MIN_SCORE_IMPROVEMENT = 5

open_trades = {}
last_top_symbols = []
last_top_score = 0


def calculate_score(data):
    score = 0
    reasons = []

    if data.get("range_quality") == "tight":
        score += 25
        reasons.append("Tight opening range")

    if data.get("volume_expansion") == "true":
        score += 25
        reasons.append("Volume expansion")

    if data.get("sweep") == "true":
        score += 20
        reasons.append("Liquidity sweep")

    if data.get("momentum") == "strong":
        score += 20
        reasons.append("Strong momentum")

    try:
        rr = float(data.get("rr", 0))
        if rr >= 2:
            score += 10
            reasons.append(f"RR {rr}")
    except:
        pass

    return score, reasons


def send_discord_report(top_setups, reason="TOP 2 ORB SETUPS"):
    message = f"🔥 **{reason} — NY OPEN**\n\n"

    for i, setup in enumerate(top_setups, start=1):
        message += f"""
{i}. **{setup['symbol']}**
Direction: **{setup['direction']}**
Score: **{setup['score']}/100**

Entry: `{setup['entry']}`
SL: `{setup['sl']}`
TP1: `{setup['tp1']}`
TP2: `{setup['tp2']}`

Reasons:
"""

        for r in setup["reasons"]:
            message += f"\n+ {r}"

        message += "\n\n"

    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})


def should_send_new_report(top_2):
    global last_top_symbols, last_top_score

    current_symbols = [x["symbol"] for x in top_2]
    current_score = sum(x["score"] for x in top_2)

    if not last_top_symbols:
        last_top_symbols = current_symbols
        last_top_score = current_score
        return True, "INITIAL TOP 2 ORB SETUPS"

    if current_symbols != last_top_symbols and current_score >= last_top_score:
        last_top_symbols = current_symbols
        last_top_score = current_score
        return True, "UPDATED TOP 2 — BETTER SETUPS FOUND"

    if current_score >= last_top_score + MIN_SCORE_IMPROVEMENT:
        last_top_symbols = current_symbols
        last_top_score = current_score
        return True, "UPDATED TOP 2 — SCORE IMPROVED"

    return False, ""


def process_ranking():
    if len(open_trades) < MIN_SETUPS:
        return

    sorted_setups = sorted(
        open_trades.values(),
        key=lambda x: x["score"],
        reverse=True
    )

    top_2 = sorted_setups[:2]
    send_update, reason = should_send_new_report(top_2)

    if send_update:
        send_discord_report(top_2, reason)


@app.get("/")
async def home():
    return {"status": "ORB scanner online"}


@app.post("/tv-webhook")
async def tv_webhook(request: Request):
    data = await request.json()

    if data.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    symbol = data.get("symbol")
    direction = data.get("direction")

    if not symbol or direction not in ["LONG", "SHORT"]:
        return {"status": "ignored", "reason": "missing symbol or direction"}

    score, reasons = calculate_score(data)

    open_trades[symbol] = {
        "symbol": symbol,
        "direction": direction,
        "entry": data.get("entry"),
        "sl": data.get("sl"),
        "tp1": data.get("tp1"),
        "tp2": data.get("tp2"),
        "score": score,
        "reasons": reasons,
        "status": "OPEN",
        "created_at": datetime.now().isoformat()
    }

    process_ranking()

    return {
        "status": "stored",
        "symbol": symbol,
        "score": score,
        "open_trades": len(open_trades)
    }


@app.get("/status")
async def status():
    return {
        "open_trades": len(open_trades),
        "symbols": list(open_trades.keys()),
        "last_top_symbols": last_top_symbols,
        "last_top_score": last_top_score
    }


@app.get("/send-report")
async def send_report():
    if not open_trades:
        return {"status": "no data"}

    sorted_setups = sorted(
        open_trades.values(),
        key=lambda x: x["score"],
        reverse=True
    )

    top_2 = sorted_setups[:2]
    send_discord_report(top_2, "MANUAL TOP 2 ORB REPORT")

    return {
        "status": "report sent",
        "top_2": top_2
    }


@app.get("/reset")
async def reset():
    global open_trades, last_top_symbols, last_top_score

    open_trades = {}
    last_top_symbols = []
    last_top_score = 0

    return {"status": "reset done"}
