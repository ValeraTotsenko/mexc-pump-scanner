import asyncio
import logging
import time
from typing import Iterable
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import load_config
from .symbols import fetch_all_pairs
from .scanner import Scanner
from .volume_scout import VolumeScout
from .features import FeatureVector
from .storage import save_signal, save_action
from .metrics import LATENCY, record_signal, start_metrics_server
from .logging_setup import setup_logging


logger = logging.getLogger(__name__)


class AlertBot:
    """Telegram bot sending pump alerts and handling actions."""

    def __init__(self, symbols: Iterable[str]) -> None:
        self.config = load_config()
        self.allowed_ids = set(self.config.get("telegram", {}).get("allowed_ids", []))
        self.scanner = Scanner(list(symbols))
        logger.info("AlertBot initialized for %d symbols", len(list(symbols)))
        start_metrics_server()
        self.app = Application.builder().token(self.config["telegram"]["token"]).build()

        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("help", self.cmd_help))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("reload", self.cmd_reload))
        self.app.add_handler(CommandHandler("cfg", self.cmd_cfg))
        self.app.add_handler(CallbackQueryHandler(self.on_callback))

    def _is_allowed(self, update: Update) -> bool:
        user = update.effective_user
        return user and user.id in self.allowed_ids

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.message.reply_text("Welcome to Pump Scanner Bot. Use /help for commands.")

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.message.reply_text(
            "/start - start bot\n/help - this help\n/status - scanner status\n/reload - reload config\n/cfg key value - set config value"
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        await update.message.reply_text("Running")

    async def cmd_reload(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        self.scanner.reload_thresholds()
        self.config = load_config()
        self.allowed_ids = set(self.config.get("telegram", {}).get("allowed_ids", []))
        await update.message.reply_text("Configuration reloaded")

    async def cmd_cfg(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            return
        if not context.args or len(context.args) < 2:
            await update.message.reply_text("Usage: /cfg key value")
            return
        key, value = context.args[0], context.args[1]
        self.config.setdefault("scanner", {}).setdefault("metrics", {})[key] = float(value)
        await update.message.reply_text(f"Set {key} = {value}")

    async def on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._is_allowed(update):
            await update.callback_query.answer()
            return
        data = update.callback_query.data
        if data.startswith("buy_"):
            sid = int(data[4:])
            save_action(sid, "buy")
            await update.callback_query.answer("Buy disabled", show_alert=True)
        elif data.startswith("skip_"):
            sid = int(data[5:])
            save_action(sid, "skip")
            await update.callback_query.answer("Ignored")
        else:
            await update.callback_query.answer()


    async def send_alert(self, fv: FeatureVector, prob: float, start_ts: float) -> None:
        LATENCY.observe((time.time() - start_ts) * 1000)
        record_signal()
        text = (
            f"\ud83d\ude80 *{fv.symbol}*  — VSR {fv.vsr:.1f}  PM {fv.pm:.2%}  Prob {prob:.2f}\n"
            f"Time: {time.strftime('%H:%M:%S')}"
        )
        signal_id = save_signal(fv, prob)
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("Buy $100", callback_data=f"buy_{signal_id}"),
                    InlineKeyboardButton("Skip", callback_data=f"skip_{signal_id}"),
                ]
            ]
        )
        for chat_id in self.allowed_ids:
            await self.app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )

    async def _scanner_loop(self) -> None:
        async for fv, prob, ts in self.scanner.run():
            await self.send_alert(fv, prob, ts)

    async def run(self) -> None:
        logger.info("Bot event loop starting")
        task = asyncio.create_task(self._scanner_loop())
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        try:
            await task
        finally:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()


def main() -> None:
    import sys
    import asyncio as _aio

    setup_logging()
    cfg = load_config()
    symbols = sys.argv[1:]
    if not symbols:
        scout_cfg = cfg.get("scout", {})
        logger.info("Selecting hot pairs using Volume Scout")
        try:
            pairs = _aio.run(VolumeScout(cfg["mexc"]["rest_url"], scout_cfg).poll())
            symbols = [p.symbol for p in pairs]
            logger.info("Volume Scout returned %d pairs", len(symbols))
        except Exception as exc:  # pragma: no cover - network
            logger.error("Volume Scout failed: %s", exc)
            logger.info("Fetching full symbol list from MEXC")
            try:
                symbols = _aio.run(fetch_all_pairs(cfg["mexc"]["rest_url"]))
            except Exception as exc2:  # pragma: no cover - network
                logger.error("Failed to fetch symbols: %s", exc2)
                sys.exit(1)
    logger.info("Starting AlertBot with %d symbols", len(symbols))
    bot = AlertBot(symbols)
    _aio.run(bot.run())


if __name__ == "__main__":
    main()
