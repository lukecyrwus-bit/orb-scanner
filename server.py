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
closed_trades = []

last_top_symbols = []
last_top_score = 0


def calculate_score(data):

    score = 0
    reasons = []

    symbol = data.get("symbol")
    direction = data.get("direction")

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

    # ===== ADAPTIVE SYMBOL EDGE =====

    key = f"{symbol}_{direction}"

    symbol_trades = [
        t for t in closed_trades
        if f"{t['symbol']}_{t['direction']}" == key
    ]

    if len(symbol_trades) >= 5:

        wins = len([
            t for t in symbol_trades
            if t["result"] == "TP2"
        ])

        wr = (wins / len(symbol_trades)) * 100

        if wr >= 60:
            score += 10
            reasons.append(f"Historical edge {round(wr,1)}%")

        elif wr <= 40:
            score -= 10
            reasons.append(f"Weak history {round(wr,1)}%")

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

    requests.post(
        DISCORD_WEBHOOK_URL,
        json={"content": message}
    )


def should_send_new_report(top_2):

    global last_top_symbols
    global last_top_score

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

    return {
        "status": "ORB scanner online"
    }


@app.post("/tv-webhook")
async def tv_webhook(request: Request):

    data = await request.json()

    if data.get("token") != SECRET_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

    symbol = data.get("symbol")
    direction = data.get("direction")

    if not symbol or direction not in ["LONG", "SHORT"]:

        return {
            "status": "ignored",
            "reason": "missing symbol or direction"
        }

    score, reasons = calculate_score(data)

    open_trades[symbol] = {
        "symbol": symbol,
        "direction": direction,
        "entry": float(data.get("entry")),
        "sl": float(data.get("sl")),
        "tp1": float(data.get("tp1")),
        "tp2": float(data.get("tp2")),
        "score": score,
        "reasons": reasons,
        "status": "OPEN",
        "tp1_hit": False,
        "tp2_hit": False,
        "sl_hit": False,
        "created_at": datetime.now().isoformat()
    }

    trade = open_trades[symbol]

    price = float(data.get("price"))

    if trade["direction"] == "LONG":

        if not trade["tp1_hit"] and price >= trade["tp1"]:

            trade["tp1_hit"] = True

            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"✅ {symbol} LONG — TP1 HIT"
                }
            )

        if not trade["tp2_hit"] and price >= trade["tp2"]:

            trade["tp2_hit"] = True
            trade["status"] = "CLOSED"

            closed_trades.append({
                "symbol": symbol,
                "direction": trade["direction"],
                "result": "TP2",
                "score": trade["score"]
            })

            if len(closed_trades) > 50:
                closed_trades.pop(0)

            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"🏆 {symbol} LONG — TP2 HIT"
                }
            )

        if not trade["sl_hit"] and price <= trade["sl"]:

            trade["sl_hit"] = True
            trade["status"] = "CLOSED"

            closed_trades.append({
                "symbol": symbol,
                "direction": trade["direction"],
                "result": "SL",
                "score": trade["score"]
            })

            if len(closed_trades) > 50:
                closed_trades.pop(0)

            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"❌ {symbol} LONG — SL HIT"
                }
            )

    if trade["direction"] == "SHORT":

        if not trade["tp1_hit"] and price <= trade["tp1"]:

            trade["tp1_hit"] = True

            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"✅ {symbol} SHORT — TP1 HIT"
                }
            )

        if not trade["tp2_hit"] and price <= trade["tp2"]:

            trade["tp2_hit"] = True
            trade["status"] = "CLOSED"

            closed_trades.append({
                "symbol": symbol,
                "direction": trade["direction"],
                "result": "TP2",
                "score": trade["score"]
            })

            if len(closed_trades) > 50:
                closed_trades.pop(0)

            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"🏆 {symbol} SHORT — TP2 HIT"
                }
            )

        if not trade["sl_hit"] and price >= trade["sl"]:

            trade["sl_hit"] = True
            trade["status"] = "CLOSED"

            closed_trades.append({
                "symbol": symbol,
                "direction": trade["direction"],
                "result": "SL",
                "score": trade["score"]
            })

            if len(closed_trades) > 50:
                closed_trades.pop(0)

            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"❌ {symbol} SHORT — SL HIT"
                }
            )

    process_ranking()

    return {
        "status": "stored",
        "symbol": symbol,
        "score": score,
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades)
    }


@app.get("/status")
async def status():

    return {
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades),
        "symbols": list(open_trades.keys()),
        "last_top_symbols": last_top_symbols,
        "last_top_score": last_top_score
    }


@app.get("/stats")
async def stats():

    total = len(closed_trades)

    tp2_wins = len([
        t for t in closed_trades
        if t["result"] == "TP2"
    ])

    sl_losses = len([
        t for t in closed_trades
        if t["result"] == "SL"
    ])

    overall_winrate = 0

    if total > 0:
        overall_winrate = round((tp2_wins / total) * 100, 2)

    symbol_stats = {}

    for trade in closed_trades:

        key = f"{trade['symbol']}_{trade['direction']}"

        if key not in symbol_stats:

            symbol_stats[key] = {
                "total": 0,
                "wins": 0,
                "losses": 0,
                "winrate": 0
            }

        symbol_stats[key]["total"] += 1

        if trade["result"] == "TP2":
            symbol_stats[key]["wins"] += 1

        if trade["result"] == "SL":
            symbol_stats[key]["losses"] += 1

    for key in symbol_stats:

        s = symbol_stats[key]

        if s["total"] > 0:
            s["winrate"] = round(
                (s["wins"] / s["total"]) * 100,
                2
            )

    return {
        "overall": {
            "total_trades": total,
            "tp2_wins": tp2_wins,
            "sl_losses": sl_losses,
            "winrate": overall_winrate
        },
        "symbols": symbol_stats
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

    send_discord_report(
        top_2,
        "MANUAL TOP 2 ORB REPORT"
    )

    return {
        "status": "report sent",
        "top_2": top_2
    }


@app.get("/reset")
async def reset():

    global open_trades
    global closed_trades
    global last_top_symbols
    global last_top_score

    open_trades = {}
    closed_trades = []

    last_top_symbols = []
    last_top_score = 0

    return {
        "status": "reset done"
    }
