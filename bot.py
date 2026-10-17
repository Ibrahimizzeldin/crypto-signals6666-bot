import os
import asyncio
import json
import time
import websockets
import httpx
from telegram import Bot
from aiohttp import web

# من Environment Variables
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

# متغيرات
signals_sent = {}

async def send_signal(text):
    bot = Bot(token=TELEGRAM_TOKEN)
    try:
        await bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending message: {e}")

async def get_klines(symbol, interval, limit=100):
    url = f"https://fapi.binance.com/fapi/v1/klines?symbol={symbol}&interval={interval}&limit={limit}"
    async with httpx.AsyncClient() as client:
        r = await client.get(url, timeout=10)
        return r.json()

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains = []
    losses = []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_ema(values, period):
    if len(values) < period:
        return values[-1] if values else 0
    k = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = v * k + ema * (1 - k)
    return ema

async def analyze_symbol(symbol):
    try:
        klines = await get_klines(symbol, "15m", 100)
        closes = [float(k[4]) for k in klines]
        highs = [float(k[2]) for k in klines]
        lows = [float(k[3]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        current_price = closes[-1]
        rsi = calc_rsi(closes)
        ema20 = calc_ema(closes, 20)
        ema50 = calc_ema(closes, 50)
        avg_volume = sum(volumes[-20:]) / 20
        last_volume = volumes[-1]

        signal = None
        confidence = 0
        reason = []

        # إشارة شراء
        if rsi < 35 and ema20 > ema50 and last_volume > avg_volume * 1.2:
            signal = "BUY"
            confidence = 70
            reason.append(f"RSI={rsi:.1f} (تشبع بيعي)")
            reason.append(f"EMA20 > EMA50")
            reason.append(f"حجم {last_volume/avg_volume:.1f}x")

        # إشارة بيع
        elif rsi > 65 and ema20 < ema50 and last_volume > avg_volume * 1.2:
            signal = "SELL"
            confidence = 70
            reason.append(f"RSI={rsi:.1f} (تشبع شرائي)")
            reason.append(f"EMA20 < EMA50")
            reason.append(f"حجم {last_volume/avg_volume:.1f}x")

        if signal and confidence >= 70:
            key = f"{symbol}_{signal}"
            now = time.time()
            if key in signals_sent and now - signals_sent[key] < 3600:
                return
            signals_sent[key] = now

            emoji = "🟢" if signal == "BUY" else "🔴"
            text = f"""{emoji} *إشارة {signal}*

📊 *العملة:* {symbol}
💰 *السعر:* {current_price}
📈 *الثقة:* {confidence}%

🔍 *السبب:*
""" + "\n".join([f"• {r}" for r in reason])

            await send_signal(text)
            print(f"Signal sent: {symbol} {signal}")

    except Exception as e:
        print(f"Error analyzing {symbol}: {e}")

async def scan_market():
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
               "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT"]
    while True:
        try:
            for symbol in symbols:
                await analyze_symbol(symbol)
                await asyncio.sleep(1)
        except Exception as e:
            print(f"Scan error: {e}")
        await asyncio.sleep(60)

# --- دالة الويب لإبقاء الخدمة تعمل على Render ---
async def handle(request):
    return web.Response(text="Bot is running 24/7")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

async def main():
    print("Starting bot...")
    # تشغيل البوت وخادم الويب في نفس الوقت
    asyncio.create_task(scan_market())
    asyncio.create_task(web_server())
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
