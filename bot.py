"""
Stone FFA Discord Bot - Main entry point.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import discord
from discord.ext import commands

from config import settings
from database.database import Database

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path("bot.log"), encoding="utf-8"),
    ],
)
logger = logging.getLogger("stoneffa")

# Reduce noise from discord.py and aiosqlite
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)
logging.getLogger("aiosqlite").setLevel(logging.WARNING)


class StoneFFABot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.moderation = True  # for audit log related events if needed
        intents.guilds = True

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,  # we provide /help
            case_insensitive=True,
        )

        self.db = Database(settings.database_path)
        self.settings = settings

    async def setup_hook(self) -> None:
        await self.db.connect()

        # Load cogs
        cogs = [
            "cogs.moderation",
            "cogs.tickets",
            "cogs.logging",
            "cogs.utility",
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info("Loaded cog: %s", cog)
            except Exception:
                logger.exception("Failed to load cog: %s", cog)
                raise

        # Sync slash commands
        if settings.guild_id:
            guild = discord.Object(id=settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logger.info("Synced application commands to guild %s", settings.guild_id)
        else:
            await self.tree.sync()
            logger.info("Synced application commands globally (may take up to 1 hour)")

    async def on_ready(self) -> None:
        if self.user is None:
            return
        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=settings.bot_activity,
        )
        await self.change_presence(activity=activity, status=discord.Status.online)
        logger.info(
            "Logged in as %s (ID: %s) | Guilds: %s",
            self.user,
            self.user.id,
            len(self.guilds),
        )

    async def close(self) -> None:
        await self.db.close()
        await super().close()


async def main() -> None:
    bot = StoneFFABot()
    try:
        async with bot:
            await bot.start(settings.discord_token)
    except discord.LoginFailure:
        logger.critical("Invalid Discord token. Check DISCORD_TOKEN in .env")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    except Exception:
        logger.exception("Fatal error while running the bot")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
