import asyncio
import contextlib
import functools
import logging
import signal

from httpx import AsyncClient, Timeout
from pyrogram.errors import MessageDeleteForbidden

from .database import Database
from .dispatcher import Dispatcher
from .extender import Extender
from .telegram import Telegram


class Selfbot(Database, Dispatcher, Extender, Telegram):
    def __init__(self, config: dict) -> None:
        self.config = config
        self.logger = logging.getLogger(self.__class__.__name__)
        self.__idle__ = None
        super().__init__()

    @classmethod
    async def launch(cls, config: dict, loop: asyncio.AbstractEventLoop) -> Selfbot:
        selfbot = cls(config)
        try:
            selfbot.loop = loop
            selfbot.http = AsyncClient(
                http2=True, timeout=Timeout(timeout=None), follow_redirects=True
            )
            await selfbot.run()
        finally:
            await selfbot.stop()

        return selfbot

    async def run(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError(f"{self.__class__.__name__} Running")

        await self.initdb()
        rows = await self.db.fetch(
            "SELECT name, chat_id, message_id FROM restart.msgs;"
        )
        self.logger.info(f"Starting {self.__class__.__name__}...")
        try:
            await self.start()
            for row in rows:
                name, chat_id, message_id = (
                    row["name"],
                    row["chat_id"],
                    row["message_id"],
                )
                match name:
                    case "app":
                        await self.app.delete_messages(chat_id, message_id)
                    case "bot":
                        with contextlib.suppress(MessageDeleteForbidden):
                            await self.bot.delete_messages(chat_id, message_id)

                await self.db.execute("DELETE FROM restart.msgs WHERE name = $1;", name)

            new = await self.bot.send_sticker(
                self.app.me.id,
                self.config["sticker_file_id"],
                disable_notification=True,
            )
            await self.db.execute(
                """
                INSERT INTO restart.msgs AS r (
                    name,
                    chat_id,
                    message_id
                )
                VALUES ($1, $2, $3)
                ON CONFLICT (name)
                DO UPDATE SET
                    chat_id     = EXCLUDED.chat_id,
                    message_id  = EXCLUDED.message_id
                WHERE
                    r.chat_id       IS DISTINCT FROM EXCLUDED.chat_id
                OR  r.message_id    IS DISTINCT FROM EXCLUDED.message_id;
                """,
                "bot",
                new.chat.id,
                new.id,
            )
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            raise

        self.logger.info(f"{self.__class__.__name__} Started")
        await self.idle()

    async def idle(self) -> None:
        if self.__idle__ and not self.__idle__.is_set():
            raise RuntimeError(f"{self.__class__.__name__} Idling")

        signames = (signal.SIGINT, signal.SIGTERM, signal.SIGABRT)

        def sighandler(signum: int) -> None:
            if self.__idle__:
                self.__idle__.set()

        for signame in signames:
            self.loop.add_signal_handler(
                signame, functools.partial(sighandler, signame)
            )

        self.__idle__ = asyncio.Event()
        try:
            await self.__idle__.wait()
        finally:
            for signame in signames:
                with contextlib.suppress(Exception):
                    self.loop.remove_signal_handler(signame)

    async def stop(self) -> None:
        try:
            await asyncio.gather(
                self.dispatch("stopping"),
                self.app.stop(),
                self.bot.stop(),
                self.http.aclose(),
                return_exceptions=True,
            )
            await self.db.close()
        except Exception as e:
            self.logger.error(f"{e.__class__.__name__}: {e}")
            raise

        self.logger.info(f"{self.__class__.__name__} Stopped")
