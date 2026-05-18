import os
import requests
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

app = FastAPI()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
SECRET_TOKEN = os.getenv("SECRET_TOKEN")

EXPECTED_SYMBOLS = 5
market_data = {}
last_report_date = None


def calculate_score(data):
    score = 0
    reasons = []

    if data.get("htf_bias") == "bullish":
        score += 20
        reasons.append("HTF bullish")

    if data.get("htf_bias") == "bearish":
        score += 20
        reasons.append("HTF bearish")

    if data.get("range_quality") == "tight":
        score += 20
        reasons.append("Tight opening range")

    if data.get("volume_expansion") == "true":
        score += 20
        reasons.append("Volume expansion")

    if data.get("sweep") == "true":
        score += 15
        reasons.append("Liquidity sweep")

    if data.get("momentum") == "strong":
        score += 15
        reasons.append("Strong momentum")

    try:
        rr = float(data.get("rr", 0))
        if rr >= 2:
            score += 10
            reasons.append(f"RR {rr}")
    except:
        pass

    return score, reasons


def send_discord_report(top_setups):
    message = "🔥 **TOP 2 ORB SETUPS — NY OPEN**\n\n"

    for i, setup in enumerate(top_setups, start=1):
        message += f"""
{i}. **{setup['symbol']}**
Direction: {setup['direction']}
Score: {setup['score']}/100

Reasons:
"""

        for r in setup["reasons"]:
            message += f"\n+ {r}"

        message += "\n\n"

    requests.post(DISCORD_WEBHOOK_URL, json={"content": message})


def maybe_send_auto_report():
    global last_report_date

    today = datetime.now().date()

    if last_report_date == today:
        return

    if len(market_data) < EXPECTED_SYMBOLS:
        return

    sorted_setups = sorted(
        market_data.values(),
        key=lambda x: x["score"],
        reverse=True
    )

    top_2 = sorted_setups[:2]
    send_discord_report(top_2)

    last_report_date = today


@app.get("/")
async def home():
    return {"status": "ORB scanner online"}


@app.post("/tv-webhook")
async def tv_webhook(request: Request):
    data = await request.json()

    if data.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    symbol = data.get("symbol")
    score, reasons = calculate_score(data)

    market_data[symbol] = {
        "symbol": symbol,
        "direction": data.get("direction"),
        "score": score,
        "reasons": reasons,
        "timestamp": datetime.now().isoformat()
    }

    maybe_send_auto_report()

    return {
        "status": "stored",
        "symbol": symbol,
        "score": score,
        "stored_symbols": len(market_data)
    }


@app.get("/send-report")
async def send_report():
    if not market_data:
        return {"status": "no data"}

    sorted_setups = sorted(
        market_data.values(),
        key=lambda x: x["score"],
        reverse=True
    )

    top_2 = sorted_setups[:2]
    send_discord_report(top_2)

    return {
        "status": "report sent",
        "top_2": top_2
    }


@app.get("/status")
async def status():
    return {
        "stored_symbols": len(market_data),
        "symbols": list(market_data.keys())
    }
