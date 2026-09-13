import os
import threading
import asyncio
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from flask import Flask
from http.server import SimpleHTTPRequestHandler, HTTPServer


# ==============================================================================
# CONFIGURACIÓN INICIAL P2P
# ==============================================================================
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

TOKEN_CRIPTO = "USDT"         # Criptoactivo a comprar
MONEDA_FIAT = "COP"           # Moneda local en pesos colombianos
PRECIO_MAX_COMPRA = 3900.0    # Alerta si hay oferta a $3,900 COP o menos
INTERVALO_SEGUNDOS = 60       # Frecuencia de consulta en segundos


def obtener_mejor_precio_p2p_bybit(tokenId="USDT", currencyId="COP"):
    """Consulta la API P2P de Bybit y devuelve la oferta más económica."""
    url = "https://api.bybit.com/v5/fiat/p2p/item/online"
    payload = {
        "tokenId": tokenId,
        "currencyId": currencyId,
        "side": "1",        # 1 = Vendedores (para que tú les compres)
        "page": "1",
        "size": "10"
    }
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        data = response.json()
        
        if data.get("retCode") == 0:
            items = data.get("result", {}).get("items", [])
            if items:
                mejor_oferta = items[0]
                precio = float(mejor_oferta.get("price"))
                vendedor = mejor_oferta.get("nickName", "Anónimo")
                min_monto = mejor_oferta.get("minAmount", "N/A")
                max_monto = mejor_oferta.get("maxAmount", "N/A")
                return precio, vendedor, min_monto, max_monto
    except Exception as e:
        print(f"Error consultando API P2P Bybit: {e}")
        
    return None, None, None, None
# ==============================================================================
# COMANDOS DE TELEGRAM
# ==============================================================================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🇨🇴 Bot de Rastreo P2P Bybit (USDT / COP)\n\n"
        "Comandos disponibles:\n"
        "• /compra [valor] - Define el precio máximo en COP (Ej: /compra 3950)\n"
        "• /intervalo [seg] - Frecuencia de consulta (Ej: /intervalo 30)\n"
        "• /estado - Consulta inmediata del mejor precio P2P en Bybit"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_set_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global PRECIO_MAX_COMPRA
    try:
        nuevo_val = float(context.args[0])
        PRECIO_MAX_COMPRA = nuevo_val
        await update.message.reply_text(
            f"🎯 Tope MÁXIMO P2P actualizado: ${PRECIO_MAX_COMPRA:,.2f} COP\n"
            f"Te avisaré cuando haya ofertas de USDT a este precio o inferior.",
            parse_mode="Markdown"
        )
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso correcto: /compra 3920", parse_mode="Markdown")


async def cmd_set_intervalo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global INTERVALO_SEGUNDOS
    try:
        nuevo_val = int(context.args[0])
        if nuevo_val < 5:
            await update.message.reply_text("⚠️ El intervalo mínimo es de 5 segundos.")
            return
        INTERVALO_SEGUNDOS = nuevo_val
        await update.message.reply_text(f"⏱️ Periodicidad ajustada a: {INTERVALO_SEGUNDOS} segundos.", parse_mode="Markdown")
    except (IndexError, ValueError):
        await update.message.reply_text("❌ Uso correcto: /intervalo 30", parse_mode="Markdown")


async def cmd_estado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    precio, vendedor, min_m, max_m = obtener_mejor_precio_p2p_bybit(TOKEN_CRIPTO, MONEDA_FIAT)
    
    if precio:
        diferencia = precio - PRECIO_MAX_COMPRA
        if diferencia <= 0:
            situacion = "🟢 ¡EN ZONA DE OFERTA!"
        else:
            situacion = f"🔴 Faltan ${diferencia:,.2f} COP para llegar a tu tope."
        
        msg = (
            f"📊 Estado Actual Mercado P2P Bybit\n\n"
            f"• Par: {TOKEN_CRIPTO} / {MONEDA_FIAT}\n"
            f"• Mejor Tasa P2P: ${precio:,.2f} COP\n"
            f"• Comerciante: {vendedor}\n"
            f"• Límites del anuncio: ${min_m} - ${max_m} COP\n"
            f"• Tu Umbral Configurado: ${PRECIO_MAX_COMPRA:,.2f} COP\n\n"
            f"Estado: {situacion}"
        )
    else:
        msg = "❌ No se pudo obtener respuesta del mercado P2P de Bybit en este momento."
        
    await update.message.reply_text(msg, parse_mode="Markdown")
# ==============================================================================
# RASTREO EN SEGUNDO PLANO Y EJECUCIÓN
# ==============================================================================
async def tarea_rastreo_p2p(app: Application):
    while True:
        precio, vendedor, min_m, max_m = obtener_mejor_precio_p2p_bybit(TOKEN_CRIPTO, MONEDA_FIAT)
        if precio:
            if precio <= PRECIO_MAX_COMPRA:
                await app.bot.send_message(
                    chat_id=CHAT_ID,
                    text=(
                        f"🚨 ¡OFERTA P2P DETECTADA EN BYBIT!\n\n"
                        f"💵 Precio oferta: ${precio:,.2f} COP\n"
                        f"🎯 Tu tope máximo: ${PRECIO_MAX_COMPRA:,.2f} COP\n"
                        f"👤 Vendedor: {vendedor}\n"
                        f"💳 Límites: ${min_m} - ${max_m} COP"
                    ),
                    parse_mode="Markdown"
                )
        await asyncio.sleep(INTERVALO_SEGUNDOS)


async def post_init(app: Application):
    asyncio.create_task(tarea_rastreo_p2p(app))

# --- Servidor Flask ligero para pasar el chequeo de Render ---
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Bot Online", 200

# --- 1. CONFIGURACIÓN DEL SERVIDOR WEB PARA ENGAÑAR A RENDER ---
def run_dummy_server():
    port = int(os.environ.get("PORT", 8000))
    # Ejecuta Flask de forma silenciosa
    flask_app.run(host="0.0.0.0", port=port)


def main():
    if not TOKEN or not CHAT_ID:
        print("ERROR: Faltan las variables TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID.")
        return

    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("compra", cmd_set_compra))
    app.add_handler(CommandHandler("intervalo", cmd_set_intervalo))
    app.add_handler(CommandHandler("estado", cmd_estado))

    # Arranca el servidor Flask en segundo plano antes de ejecutar el bot
    threading.Thread(target=run_dummy_server, daemon=True).start()

    print("Bot P2P USDT/COP en marcha...")
    app.run_polling()

if __name__ == "__main__":
    main()
