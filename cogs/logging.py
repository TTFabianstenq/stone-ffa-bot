"""
Event logging cog for Stone FFA Bot.
Logs member joins/leaves, bans, message edits/deletes, etc. to the configured log channel.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from config import settings

logger = logging.getLogger("stoneffa.logging")


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        channel_id = settings.log_channel_id
        if not channel_id:
            return None
        ch = guild.get_channel(channel_id)
        return ch if isinstance(ch, discord.TextChannel) else None

    async def _send(
        self,
        guild: discord.Guild,
        embed: discord.Embed,
    ) -> None:
        channel = self._get_log_channel(guild)
        if channel is None:
            return
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to send log embed to channel %s", channel.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title="Member Joined",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        embed.add_field(
            name="Account Created",
            value=discord.utils.format_dt(member.created_at, style="F"),
            inline=True,
        )
        embed.add_field(
            name="Member Count",
            value=str(member.guild.member_count or "?"),
            inline=True,
        )
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        embed = discord.Embed(
            title="Member Left",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="User", value=f"{member} (`{member.id}`)", inline=False)
        joined = (
            discord.utils.format_dt(member.joined_at, style="F")
            if member.joined_at
            else "Unknown"
        )
        embed.add_field(name="Joined", value=joined, inline=True)
        roles = [r.name for r in member.roles if r != member.guild.default_role]
        if roles:
            embed.add_field(name="Roles", value=", ".join(roles[:15]), inline=False)
        await self._send(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(
            title="Member Banned",
            color=discord.Color.dark_red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        reason = "Unknown"
        moderator = "Unknown"
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target and entry.target.id == user.id:
                    reason = entry.reason or "No reason provided"
                    moderator = str(entry.user) if entry.user else "Unknown"
                    break
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass
        embed.add_field(name="Moderator", value=moderator, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        embed = discord.Embed(
            title="Member Unbanned",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="User", value=f"{user} (`{user.id}`)", inline=False)
        moderator = "Unknown"
        reason = "Unknown"
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target and entry.target.id == user.id:
                    reason = entry.reason or "No reason provided"
                    moderator = str(entry.user) if entry.user else "Unknown"
                    break
        except (discord.Forbidden, discord.HTTPException):
            pass
        embed.add_field(name="Moderator", value=moderator, inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await self._send(guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until is not None:
                embed = discord.Embed(
                    title="Member Timed Out",
                    color=discord.Color.gold(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="User", value=f"{after} (`{after.id}`)", inline=False)
                embed.add_field(
                    name="Until",
                    value=discord.utils.format_dt(after.timed_out_until, style="F"),
                    inline=True,
                )
            else:
                embed = discord.Embed(
                    title="Timeout Removed",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )
                embed.add_field(name="User", value=f"{after} (`{after.id}`)", inline=False)
            await self._send(after.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.guild is None or message.author.bot:
            return
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):
            return

        embed = discord.Embed(
            title="Message Deleted",
            color=discord.Color.red(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Author",
            value=f"{message.author} (`{message.author.id}`)",
            inline=False,
        )
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content or "[empty or embed-only]"
        if len(content) > 1000:
            content = content[:997] + "..."
        embed.add_field(name="Content", value=content, inline=False)
        if message.attachments:
            embed.add_field(
                name="Attachments",
                value="\n".join(a.url for a in message.attachments[:5]),
                inline=False,
            )
        await self._send(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return
        if not isinstance(before.channel, (discord.TextChannel, discord.Thread)):
            return

        embed = discord.Embed(
            title="Message Edited",
            color=discord.Color.blue(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(
            name="Author",
            value=f"{before.author} (`{before.author.id}`)",
            inline=False,
        )
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        if before.jump_url:
            embed.add_field(name="Jump", value=f"[Go to message]({before.jump_url})", inline=True)

        before_c = before.content or "[empty]"
        after_c = after.content or "[empty]"
        if len(before_c) > 500:
            before_c = before_c[:497] + "..."
        if len(after_c) > 500:
            after_c = after_c[:497] + "..."
        embed.add_field(name="Before", value=before_c, inline=False)
        embed.add_field(name="After", value=after_c, inline=False)
        await self._send(before.guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Logging(bot))
