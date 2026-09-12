"""
Utility slash commands for Stone FFA Bot.
"""

from __future__ import annotations

import platform
import time
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config


class Utility(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.start_time = time.time()

    @app_commands.command(name="ping", description="Check the bot's latency.")
    @app_commands.checks.cooldown(1, 5.0)
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        embed = discord.Embed(
            title="Pong!",
            description=f"Latency: **{latency_ms} ms**",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="serverinfo", description="Show information about this server.")
    @app_commands.checks.cooldown(1, 10.0)
    async def serverinfo(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "This command can only be used in a server.", ephemeral=True
            )
            return

        owner = guild.owner
        created = discord.utils.format_dt(guild.created_at, style="F")
        member_count = guild.member_count or len(guild.members)
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)
        roles = len(guild.roles)
        boosts = guild.premium_subscription_count
        boost_level = guild.premium_tier

        embed = discord.Embed(
            title=guild.name,
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(name="Owner", value=str(owner) if owner else "Unknown", inline=True)
        embed.add_field(name="Server ID", value=str(guild.id), inline=True)
        embed.add_field(name="Created", value=created, inline=False)
        embed.add_field(name="Members", value=str(member_count), inline=True)
        embed.add_field(name="Text Channels", value=str(text_channels), inline=True)
        embed.add_field(name="Voice Channels", value=str(voice_channels), inline=True)
        embed.add_field(name="Roles", value=str(roles), inline=True)
        embed.add_field(
            name="Boosts",
            value=f"Level {boost_level} ({boosts} boosts)",
            inline=True,
        )
        if guild.description:
            embed.add_field(name="Description", value=guild.description, inline=False)

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Show information about a user.")
    @app_commands.describe(user="The user to inspect (defaults to yourself).")
    @app_commands.checks.cooldown(1, 8.0)
    async def userinfo(
        self, interaction: discord.Interaction, user: Optional[discord.Member] = None
    ) -> None:
        member = user or interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message(
                "Could not fetch member information in this context.", ephemeral=True
            )
            return

        roles = [r.mention for r in member.roles if r != interaction.guild.default_role]  # type: ignore
        roles_str = ", ".join(roles[-10:]) if roles else "None"
        if len(roles) > 10:
            roles_str += f" (+{len(roles) - 10} more)"

        joined = (
            discord.utils.format_dt(member.joined_at, style="F")
            if member.joined_at
            else "Unknown"
        )
        created = discord.utils.format_dt(member.created_at, style="F")

        embed = discord.Embed(
            title=str(member),
            color=member.color if member.color.value else discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        if member.display_avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Nickname", value=member.nick or "None", inline=True)
        embed.add_field(name="Bot", value="Yes" if member.bot else "No", inline=True)
        embed.add_field(name="Account Created", value=created, inline=False)
        embed.add_field(name="Joined Server", value=joined, inline=False)
        embed.add_field(name="Roles", value=roles_str, inline=False)
        embed.add_field(
            name="Top Role",
            value=member.top_role.mention if member.top_role else "None",
            inline=True,
        )

        if member.timed_out_until:
            embed.add_field(
                name="Timed Out Until",
                value=discord.utils.format_dt(member.timed_out_until, style="F"),
                inline=False,
            )

        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="avatar", description="Show a user's avatar.")
    @app_commands.describe(user="The user whose avatar to show (defaults to yourself).")
    @app_commands.checks.cooldown(1, 5.0)
    async def avatar(
        self, interaction: discord.Interaction, user: Optional[discord.User] = None
    ) -> None:
        target = user or interaction.user
        embed = discord.Embed(
            title=f"{target.display_name}'s Avatar",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_image(url=target.display_avatar.url)
        embed.set_footer(text=f"Requested by {interaction.user}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="botinfo", description="Show information about the bot.")
    @app_commands.checks.cooldown(1, 10.0)
    async def botinfo(self, interaction: discord.Interaction) -> None:
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        embed = discord.Embed(
            title="Stone FFA Bot",
            description="Official Discord bot for the Stone FFA Minecraft server.",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        if self.bot.user and self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)} ms", inline=True)
        embed.add_field(name="Uptime", value=uptime_str, inline=True)
        embed.add_field(name="Guilds", value=str(len(self.bot.guilds)), inline=True)
        embed.add_field(name="Python", value=platform.python_version(), inline=True)
        embed.add_field(name="discord.py", value=discord.__version__, inline=True)
        embed.add_field(
            name="Library",
            value="[discord.py](https://github.com/Rapptz/discord.py)",
            inline=True,
        )
        embed.set_footer(text="Built for Stone FFA")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="help", description="List available commands.")
    @app_commands.checks.cooldown(1, 5.0)
    async def help_command(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(
            title="Stone FFA Bot — Commands",
            description="Slash commands available on this server.",
            color=discord.Color.blurple(),
            timestamp=datetime.now(timezone.utc),
        )

        embed.add_field(
            name="Utility",
            value=(
                "`/ping` — Latency check\n"
                "`/serverinfo` — Server information\n"
                "`/userinfo [user]` — User information\n"
                "`/avatar [user]` — Show avatar\n"
                "`/botinfo` — Bot information\n"
                "`/help` — This message"
            ),
            inline=False,
        )
        embed.add_field(
            name="Moderation (Staff)",
            value=(
                "`/ban` `/unban` `/kick`\n"
                "`/timeout` `/untimeout`\n"
                "`/warn` `/warnings`\n"
                "`/clear` `/slowmode`\n"
                "`/lock` `/unlock`"
            ),
            inline=False,
        )
        embed.add_field(
            name="Tickets",
            value=(
                "Use the ticket panel button to open a ticket.\n"
                "Inside a ticket: Claim / Close / Delete controls are available to staff."
            ),
            inline=False,
        )
        embed.set_footer(text="Stone FFA")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ping.error
    @serverinfo.error
    @userinfo.error
    @avatar.error
    @botinfo.error
    @help_command.error
    async def utility_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {error.retry_after:.1f}s.",
                ephemeral=True,
            )
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred while running this command.",
                    ephemeral=True,
                )
            raise error


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Utility(bot))
