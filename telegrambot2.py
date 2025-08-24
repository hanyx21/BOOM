# telegram_trader_bot.py
# Dépendances: python-telegram-bot>=22,<23

import os, sys, asyncio, pathlib
from typing import Final, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    CallbackQueryHandler, filters
)

# ========= CONFIG =========
TOKEN = "8355563985:AAEx4B2zS6kJL1uLL-dPUdCEdv0KZRG-J08"  # ← ton token BotFather
BOT_USERNAME: Final = "@TB00M_BOT"

# Dossier où tourne ton script de trading
TRADER_CWD = pathlib.Path(r"C:\Users\rania\OneDrive\Bureau\SCRAP\bot\BOOM")  # adapte si besoin
# Nom du fichier script de trading (ex: "my_trading_bot.py")
TRADER_SCRIPT = TRADER_CWD / "main.py"                     # <-- mets le tien
# (Optionnel) arguments à passer à ton script
TRADER_ARGS = []  # ex: ["--exchange", "binance", "--pair", "BTCUSDT"]

# Fichier log produit par ton bot de trading
LOG_JSON_PATH = TRADER_CWD / "trade_log.json"

# Fichier pour logger la sortie du sous-processus (stdout/stderr)
RUNTIME_LOG_PATH = TRADER_CWD / "trader_stdout.log"


# ========= UI =========
def main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Buy (Start)", callback_data="BUY_START"),
        InlineKeyboardButton("🔴 Sell (Stop)", callback_data="SELL_STOP"),
        InlineKeyboardButton("📊 Positions (log.json)", callback_data="POSITIONS_FILE"),
    ]])

# ========= Utils état sous-processus =========
def _proc_running(app: Application) -> bool:
    proc: Optional[asyncio.subprocess.Process] = app.bot_data.get("trader_proc")
    return (proc is not None) and (proc.returncode is None)

async def _start_trader(app: Application) -> str:
    if _proc_running(app):
        return "ℹ️ Le bot de trading est déjà en cours d’exécution."

    if not TRADER_SCRIPT.exists():
        return f"❌ Script introuvable: {TRADER_SCRIPT}"

    # Ouvre (ou crée) un fichier log pour la sortie du sous-processus
    logf = open(RUNTIME_LOG_PATH, "ab", buffering=0)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(TRADER_SCRIPT), *TRADER_ARGS,
            cwd=str(TRADER_CWD),
            stdout=logf,
            stderr=logf,
        )
        app.bot_data["trader_proc"] = proc
        app.bot_data["trader_logf"] = logf
        return f"✅ Trading bot démarré (PID={proc.pid})."
    except Exception as e:
        logf.close()
        return f"❌ Échec démarrage: {e}"

async def _stop_trader(app: Application) -> str:
    proc: Optional[asyncio.subprocess.Process] = app.bot_data.get("trader_proc")
    logf = app.bot_data.get("trader_logf")

    if not proc or proc.returncode is not None:
        # déjà stoppé
        if logf:
            try: logf.close()
            except: pass
        app.bot_data.pop("trader_proc", None)
        app.bot_data.pop("trader_logf", None)
        return "ℹ️ Aucun bot de trading en cours."

    try:
        # Stop “soft”
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=8)
        except asyncio.TimeoutError:
            # Kill fort si ça ne s’arrête pas
            proc.kill()
            await proc.wait()
        code = proc.returncode
        return f"🛑 Trading bot stoppé (code={code})."
    finally:
        if logf:
            try: logf.close()
            except: pass
        app.bot_data.pop("trader_proc", None)
        app.bot_data.pop("trader_logf", None)


# ========= Commandes =========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello! I'm your trading bot.\nChoisis une action :", reply_markup=main_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Buy = démarrer le script de trading\n"
        "Sell = arrêter le script de trading\n"
        "Positions = envoyer le log.json"
    )

# (Optionnel) tes réponses libres
def handle_response(text: str) -> str:
    t = (text or "").lower()
    if "hello" in t: return "Hello! How can I assist you today?"
    if "how are you" in t: return "I'm just a bot, but thanks for asking!"
    if "what is your name" in t: return "I'm a Telegram bot created to assist you with trading."
    return "I'm sorry, I didn't understand that. Can you please rephrase?"

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Réponses libres + rappel du panel
    response = handle_response(update.message.text)
    await update.message.reply_text(response, reply_markup=main_keyboard())

# ========= Boutons =========
async def on_action_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "BUY_START":
        msg = await _start_trader(context.application)
        await query.message.reply_text(msg, reply_markup=main_keyboard())
        return

    if action == "SELL_STOP":
        msg = await _stop_trader(context.application)
        await query.message.reply_text(msg, reply_markup=main_keyboard())
        return

    if action == "POSITIONS_FILE":
        if LOG_JSON_PATH.exists() and LOG_JSON_PATH.is_file():
            try:
                with open(LOG_JSON_PATH, "rb") as f:
                    await query.message.reply_document(
                        document=f,
                        filename=LOG_JSON_PATH.name,
                        caption="Voici ton log.json",
                    )
            except Exception as e:
                await query.message.reply_text(f"❌ Impossible d’envoyer log.json: {e}")
        else:
            await query.message.reply_text(f"❗ Fichier introuvable: {LOG_JSON_PATH}")
        return

# ========= Erreurs =========
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    # Log minimal d’erreur côté serveur
    print(f"[ERROR] {context.error}")

# ========= Main =========
async def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(on_action_click, pattern=r"^(BUY_START|SELL_STOP|POSITIONS_FILE)$"))
    app.add_error_handler(error_handler)

    await app.initialize()
    await app.start()
    print("Polling… (Ctrl+C pour stopper)")
    await app.updater.start_polling()

    try:
        # attente “infinie”
        await asyncio.Future()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        # Si le trader tourne encore, on l’arrête proprement
        if _proc_running(app):
            await _stop_trader(app)
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
