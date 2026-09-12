"""
Moderation slash commands for Stone FFA Bot.
Includes hierarchy protection, permission checks, and logging.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import settings

logger = logging.getLogger("stoneffa.moderation")


def _is_staff(member: discord.Member) -> bool:
    """Check if member has the configured staff or admin role, or administrator permission."""
    if member.guild_permissions.administrator:
        return True
    staff_id = settings.staff_role_id
    admin_id = settings.admin_role_id
    role_ids = {r.id for r in member.roles}
    if staff_id and staff_id in role_ids:
        return True
    if admin_id and admin_id in role_ids:
        return True
    return False


def _can_moderate(moderator: discord.Member, target: discord.Member) -> tuple[bool, str]:
    """
    Hierarchy and self-moderation checks.
    Returns (allowed, reason_if_not).
    """
    if target.id == moderator.id:
        return False, "You cannot moderate yourself."
    if target.id == moderator.guild.owner_id:
        return False, "You cannot moderate the server owner."
    if target.top_role >= moderator.top_role and not moderator.guild_permissions.administrator:
        return False, "You cannot moderate a member with an equal or higher role."
    if target.guild_permissions.administrator and not moderator.guild_permissions.administrator:
        return False, "You cannot moderate an administrator."
    bot_member = moderator.guild.me
    if bot_member and target.top_role >= bot_member.top_role:
        return False, "I cannot moderate a member with an equal or higher role than mine."
    return True, ""


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def _get_log_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        channel_id = settings.log_channel_id
        if not channel_id:
            return None
        channel = guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel):
            return channel
        return None

    async def _send_mod_log(
        self,
        guild: discord.Guild,
        *,
        action: str,
        moderator: discord.Member,
        target: discord.abc.User,
        reason: Optional[str] = None,
        extra: Optional[str] = None,
        color: discord.Color = discord.Color.red(),
    ) -> None:
        channel = await self._get_log_channel(guild)
        if channel is None:
            return
        embed = discord.Embed(
            title=f"Moderation: {action}",
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Target", value=f"{target} (`{target.id}`)", inline=False)
        embed.add_field(name="Moderator", value=f"{moderator} (`{moderator.id}`)", inline=False)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        if extra:
            embed.add_field(name="Details", value=extra, inline=False)
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            logger.warning("Failed to send mod log to channel %s", channel.id)

    @app_commands.command(name="ban", description="Ban a member from the server.")
    @app_commands.describe(
        user="The member to ban",
        reason="Reason for the ban",
        delete_message_days="Delete messages from the last N days (0-7)",
    )
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def ban(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
        delete_message_days: app_commands.Range[int, 0, 7] = 0,
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not _is_staff(interaction.user) and not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
            return

        allowed, msg = _can_moderate(interaction.user, user)
        if not allowed:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        delete_seconds = delete_message_days * 86400
        try:
            await user.ban(
                reason=f"{reason} | By: {interaction.user}",
                delete_message_seconds=delete_seconds,
            )
        except TypeError:
            try:
                await user.ban(
                    reason=f"{reason} | By: {interaction.user}",
                    delete_message_days=delete_message_days,
                )
            except discord.Forbidden:
                await interaction.response.send_message("I do not have permission to ban that member.", ephemeral=True)
                return
            except discord.HTTPException as e:
                await interaction.response.send_message(f"Failed to ban: {e}", ephemeral=True)
                return
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to ban that member.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to ban: {e}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"**{user}** has been banned.\nReason: {reason}", ephemeral=False
        )
        await self._send_mod_log(
            interaction.guild,
            action="Ban",
            moderator=interaction.user,
            target=user,
            reason=reason,
            extra=f"Messages deleted: last {delete_message_days} day(s)",
            color=discord.Color.dark_red(),
        )

    @app_commands.command(name="unban", description="Unban a user by ID.")
    @app_commands.describe(user_id="The Discord user ID to unban", reason="Reason for the unban")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def unban(
        self,
        interaction: discord.Interaction,
        user_id: str,
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        try:
            uid = int(user_id.strip())
        except ValueError:
            await interaction.response.send_message("Invalid user ID.", ephemeral=True)
            return

        try:
            user = await self.bot.fetch_user(uid)
        except discord.NotFound:
            await interaction.response.send_message("User not found.", ephemeral=True)
            return
        except discord.HTTPException:
            await interaction.response.send_message("Failed to fetch user.", ephemeral=True)
            return

        try:
            await interaction.guild.unban(user, reason=f"{reason} | By: {interaction.user}")
        except discord.NotFound:
            await interaction.response.send_message("That user is not banned.", ephemeral=True)
            return
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to unban.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to unban: {e}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"**{user}** (`{user.id}`) has been unbanned.\nReason: {reason}"
        )
        await self._send_mod_log(
            interaction.guild,
            action="Unban",
            moderator=interaction.user,
            target=user,
            reason=reason,
            color=discord.Color.green(),
        )

    @app_commands.command(name="kick", description="Kick a member from the server.")
    @app_commands.describe(user="The member to kick", reason="Reason for the kick")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def kick(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        allowed, msg = _can_moderate(interaction.user, user)
        if not allowed:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        try:
            await user.kick(reason=f"{reason} | By: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to kick that member.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to kick: {e}", ephemeral=True)
            return

        await interaction.response.send_message(f"**{user}** has been kicked.\nReason: {reason}")
        await self._send_mod_log(
            interaction.guild,
            action="Kick",
            moderator=interaction.user,
            target=user,
            reason=reason,
            color=discord.Color.orange(),
        )

    @app_commands.command(name="timeout", description="Timeout (mute) a member.")
    @app_commands.describe(
        user="The member to timeout",
        duration="Duration in minutes (1-40320 / 28 days)",
        reason="Reason for the timeout",
    )
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def timeout(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        duration: app_commands.Range[int, 1, 40320],
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        allowed, msg = _can_moderate(interaction.user, user)
        if not allowed:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        until = datetime.now(timezone.utc) + timedelta(minutes=duration)
        try:
            await user.timeout(until, reason=f"{reason} | By: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to timeout that member.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to timeout: {e}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"**{user}** has been timed out for **{duration}** minute(s).\nReason: {reason}"
        )
        await self._send_mod_log(
            interaction.guild,
            action="Timeout",
            moderator=interaction.user,
            target=user,
            reason=reason,
            extra=f"Duration: {duration} minute(s)\nUntil: {discord.utils.format_dt(until, style='F')}",
            color=discord.Color.gold(),
        )

    @app_commands.command(name="untimeout", description="Remove timeout from a member.")
    @app_commands.describe(user="The member to remove timeout from", reason="Reason")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def untimeout(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if user.timed_out_until is None:
            await interaction.response.send_message("That member is not timed out.", ephemeral=True)
            return

        try:
            await user.timeout(None, reason=f"{reason} | By: {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to remove that timeout.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to remove timeout: {e}", ephemeral=True)
            return

        await interaction.response.send_message(f"Timeout removed from **{user}**.\nReason: {reason}")
        await self._send_mod_log(
            interaction.guild,
            action="Untimeout",
            moderator=interaction.user,
            target=user,
            reason=reason,
            color=discord.Color.green(),
        )

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.describe(user="The member to warn", reason="Reason for the warning")
    @app_commands.checks.cooldown(1, 3.0)
    async def warn(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if not _is_staff(interaction.user) and not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message("You do not have permission to warn members.", ephemeral=True)
            return

        allowed, msg = _can_moderate(interaction.user, user)
        if not allowed:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        db = self.bot.db  # type: ignore[attr-defined]
        warning_id = await db.add_warning(
            interaction.guild.id, user.id, interaction.user.id, reason
        )

        warnings = await db.get_warnings(interaction.guild.id, user.id)
        count = len(warnings)

        await interaction.response.send_message(
            f"**{user}** has been warned (#{warning_id}).\n"
            f"Reason: {reason}\n"
            f"Total warnings: **{count}**"
        )
        await self._send_mod_log(
            interaction.guild,
            action="Warn",
            moderator=interaction.user,
            target=user,
            reason=reason,
            extra=f"Warning ID: {warning_id} | Total: {count}",
            color=discord.Color.yellow(),
        )

        try:
            dm = discord.Embed(
                title=f"You were warned in {interaction.guild.name}",
                description=reason,
                color=discord.Color.yellow(),
                timestamp=datetime.now(timezone.utc),
            )
            dm.add_field(name="Moderator", value=str(interaction.user), inline=False)
            await user.send(embed=dm)
        except discord.HTTPException:
            pass

    @app_commands.command(name="warnings", description="View warnings for a member.")
    @app_commands.describe(user="The member whose warnings to view")
    @app_commands.checks.cooldown(1, 5.0)
    async def warnings(
        self,
        interaction: discord.Interaction,
        user: discord.Member,
    ) -> None:
        if interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
            return

        if isinstance(interaction.user, discord.Member):
            if user.id != interaction.user.id and not _is_staff(interaction.user):
                await interaction.response.send_message(
                    "You can only view your own warnings unless you are staff.", ephemeral=True
                )
                return

        db = self.bot.db  # type: ignore[attr-defined]
        records = await db.get_warnings(interaction.guild.id, user.id)

        if not records:
            await interaction.response.send_message(
                f"**{user}** has no warnings.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Warnings for {user}",
            color=discord.Color.orange(),
            timestamp=datetime.now(timezone.utc),
        )
        for i, w in enumerate(records[:15], start=1):
            created = w["created_at"]
            mod_id = w["moderator_id"]
            embed.add_field(
                name=f"#{w['id']} — {created[:19]} UTC",
                value=f"Moderator: <@{mod_id}>\nReason: {w['reason']}",
                inline=False,
            )
        if len(records) > 15:
            embed.set_footer(text=f"Showing 15 of {len(records)} warnings")
        else:
            embed.set_footer(text=f"Total: {len(records)}")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="clear", description="Delete a number of messages in this channel.")
    @app_commands.describe(amount="Number of messages to delete (1-100)", reason="Reason")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True)
    @app_commands.checks.cooldown(1, 5.0)
    async def clear(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a text channel.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            deleted = await interaction.channel.purge(
                limit=amount,
                reason=f"{reason} | By: {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.followup.send("I do not have permission to delete messages here.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to delete messages: {e}", ephemeral=True)
            return

        await interaction.followup.send(f"Deleted **{len(deleted)}** message(s).", ephemeral=True)
        await self._send_mod_log(
            interaction.guild,
            action="Clear Messages",
            moderator=interaction.user,  # type: ignore
            target=interaction.user,  # type: ignore
            reason=reason,
            extra=f"Channel: {interaction.channel.mention}\nDeleted: {len(deleted)}",
            color=discord.Color.blue(),
        )

    @app_commands.command(name="slowmode", description="Set slowmode in this channel.")
    @app_commands.describe(seconds="Slowmode delay in seconds (0 to disable, max 21600)", reason="Reason")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def slowmode(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a text channel.", ephemeral=True)
            return

        try:
            await interaction.channel.edit(
                slowmode_delay=seconds,
                reason=f"{reason} | By: {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to edit this channel.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to set slowmode: {e}", ephemeral=True)
            return

        if seconds == 0:
            msg = "Slowmode disabled."
        else:
            msg = f"Slowmode set to **{seconds}** second(s)."
        await interaction.response.send_message(msg)
        await self._send_mod_log(
            interaction.guild,
            action="Slowmode",
            moderator=interaction.user,  # type: ignore
            target=interaction.user,  # type: ignore
            reason=reason,
            extra=f"Channel: {interaction.channel.mention}\nDelay: {seconds}s",
            color=discord.Color.blue(),
        )

    @app_commands.command(name="lock", description="Lock this channel (deny @everyone send messages).")
    @app_commands.describe(reason="Reason for locking")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def lock(
        self,
        interaction: discord.Interaction,
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a text channel.", ephemeral=True)
            return

        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        try:
            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"{reason} | By: {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to lock this channel.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to lock: {e}", ephemeral=True)
            return

        await interaction.response.send_message(f"Channel locked.\nReason: {reason}")
        await self._send_mod_log(
            interaction.guild,
            action="Lock Channel",
            moderator=interaction.user,  # type: ignore
            target=interaction.user,  # type: ignore
            reason=reason,
            extra=f"Channel: {interaction.channel.mention}",
            color=discord.Color.dark_grey(),
        )

    @app_commands.command(name="unlock", description="Unlock this channel.")
    @app_commands.describe(reason="Reason for unlocking")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    @app_commands.checks.cooldown(1, 3.0)
    async def unlock(
        self,
        interaction: discord.Interaction,
        reason: str = "No reason provided",
    ) -> None:
        if not isinstance(interaction.channel, discord.TextChannel) or interaction.guild is None:
            await interaction.response.send_message("This command can only be used in a text channel.", ephemeral=True)
            return

        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        try:
            await interaction.channel.set_permissions(
                interaction.guild.default_role,
                overwrite=overwrite,
                reason=f"{reason} | By: {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message("I do not have permission to unlock this channel.", ephemeral=True)
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(f"Failed to unlock: {e}", ephemeral=True)
            return

        await interaction.response.send_message(f"Channel unlocked.\nReason: {reason}")
        await self._send_mod_log(
            interaction.guild,
            action="Unlock Channel",
            moderator=interaction.user,  # type: ignore
            target=interaction.user,  # type: ignore
            reason=reason,
            extra=f"Channel: {interaction.channel.mention}",
            color=discord.Color.green(),
        )

    async def cog_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            await interaction.response.send_message(
                "You are missing required permissions for this command.", ephemeral=True
            )
        elif isinstance(error, app_commands.BotMissingPermissions):
            await interaction.response.send_message(
                f"I am missing required permissions: {', '.join(error.missing_permissions)}",
                ephemeral=True,
            )
        elif isinstance(error, app_commands.CommandOnCooldown):
            await interaction.response.send_message(
                f"This command is on cooldown. Try again in {error.retry_after:.1f}s.",
                ephemeral=True,
            )
        elif isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message(
                "You do not have permission to use this command.", ephemeral=True
            )
        else:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "An unexpected error occurred.", ephemeral=True
                )
            logger.exception("Moderation command error: %s", error)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
