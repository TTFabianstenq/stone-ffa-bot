"""
Ticket system for Stone FFA Bot.
Button panel, private channels, claim/close/delete, transcripts.
"""

from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import settings

logger = logging.getLogger("stoneffa.tickets")


def _is_staff(member: discord.Member) -> bool:
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


class TicketControlView(discord.ui.View):
    """Persistent controls inside a ticket channel."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Claim",
        style=discord.ButtonStyle.primary,
        custom_id="ticket:claim",
        emoji="\U0001f44b",
    )
    async def claim_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("Invalid context.", ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message("Only staff can claim tickets.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return

        db = self.bot.db  # type: ignore[attr-defined]
        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            await interaction.response.send_message("This is not a registered ticket.", ephemeral=True)
            return
        if ticket["status"] == "closed":
            await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
            return
        if ticket["claimed_by"]:
            await interaction.response.send_message(
                f"This ticket is already claimed by <@{ticket['claimed_by']}>.", ephemeral=True
            )
            return

        success = await db.claim_ticket(channel.id, interaction.user.id)
        if not success:
            await interaction.response.send_message("Could not claim the ticket.", ephemeral=True)
            return

        await interaction.response.send_message(
            f"Ticket claimed by {interaction.user.mention}."
        )
        await self._log_ticket_action(
            interaction.guild,
            action="Ticket Claimed",
            user=interaction.user,
            channel=channel,
            owner_id=ticket["owner_id"],
        )

    @discord.ui.button(
        label="Close",
        style=discord.ButtonStyle.secondary,
        custom_id="ticket:close",
        emoji="\U0001f512",
    )
    async def close_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("Invalid context.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return

        db = self.bot.db  # type: ignore[attr-defined]
        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            await interaction.response.send_message("This is not a registered ticket.", ephemeral=True)
            return
        if ticket["status"] == "closed":
            await interaction.response.send_message("This ticket is already closed.", ephemeral=True)
            return

        is_owner = ticket["owner_id"] == interaction.user.id
        if not is_owner and not _is_staff(interaction.user):
            await interaction.response.send_message(
                "Only the ticket owner or staff can close this ticket.", ephemeral=True
            )
            return

        await db.close_ticket(channel.id, interaction.user.id)

        overwrites = channel.overwrites
        owner = interaction.guild.get_member(ticket["owner_id"])
        if owner:
            ow = overwrites.get(owner) or discord.PermissionOverwrite()
            ow.send_messages = False
            overwrites[owner] = ow
            try:
                await channel.edit(overwrites=overwrites, reason="Ticket closed")
            except discord.HTTPException:
                pass

        await interaction.response.send_message(
            f"Ticket closed by {interaction.user.mention}. Staff may delete it when ready."
        )
        await self._log_ticket_action(
            interaction.guild,
            action="Ticket Closed",
            user=interaction.user,
            channel=channel,
            owner_id=ticket["owner_id"],
        )

    @discord.ui.button(
        label="Delete",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:delete",
        emoji="\U0001f5d1",
    )
    async def delete_button(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("Invalid context.", ephemeral=True)
            return
        if not _is_staff(interaction.user):
            await interaction.response.send_message("Only staff can delete tickets.", ephemeral=True)
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message("Invalid channel.", ephemeral=True)
            return

        db = self.bot.db  # type: ignore[attr-defined]
        ticket = await db.get_ticket_by_channel(channel.id)
        if not ticket:
            await interaction.response.send_message("This is not a registered ticket.", ephemeral=True)
            return

        await interaction.response.send_message("Generating transcript and deleting channel...")

        transcript_file = await self._generate_transcript(channel)
        transcript_channel_id = settings.transcript_channel_id
        if transcript_channel_id and transcript_file:
            tch = interaction.guild.get_channel(transcript_channel_id)
            if isinstance(tch, discord.TextChannel):
                try:
                    embed = discord.Embed(
                        title="Ticket Transcript",
                        description=(
                            f"Ticket: {channel.name}\n"
                            f"Owner: <@{ticket['owner_id']}>\n"
                            f"Closed/Deleted by: {interaction.user.mention}"
                        ),
                        color=discord.Color.dark_grey(),
                        timestamp=datetime.now(timezone.utc),
                    )
                    await tch.send(embed=embed, file=transcript_file)
                except discord.HTTPException:
                    logger.warning("Failed to send transcript to channel %s", transcript_channel_id)

        await self._log_ticket_action(
            interaction.guild,
            action="Ticket Deleted",
            user=interaction.user,
            channel=channel,
            owner_id=ticket["owner_id"],
        )

        await db.delete_ticket_record(channel.id)

        try:
            await channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except discord.HTTPException as e:
            logger.error("Failed to delete ticket channel %s: %s", channel.id, e)

    async def _generate_transcript(
        self, channel: discord.TextChannel
    ) -> Optional[discord.File]:
        lines = [
            f"Ticket Transcript: #{channel.name}",
            f"Channel ID: {channel.id}",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            "=" * 60,
            "",
        ]
        try:
            async for message in channel.history(limit=500, oldest_first=True):
                ts = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                author = f"{message.author} ({message.author.id})"
                content = message.content or "[no content]"
                if message.attachments:
                    content += " " + " ".join(a.url for a in message.attachments)
                lines.append(f"[{ts}] {author}: {content}")
        except discord.HTTPException:
            lines.append("[Failed to fetch full history]")

        text = "\n".join(lines)
        buffer = io.BytesIO(text.encode("utf-8"))
        filename = f"transcript-{channel.name}-{channel.id}.txt"
        return discord.File(fp=buffer, filename=filename)

    async def _log_ticket_action(
        self,
        guild: discord.Guild,
        *,
        action: str,
        user: discord.Member,
        channel: discord.TextChannel,
        owner_id: int,
    ) -> None:
        log_id = settings.log_channel_id
        if not log_id:
            return
        log_ch = guild.get_channel(log_id)
        if not isinstance(log_ch, discord.TextChannel):
            return
        embed = discord.Embed(
            title=action,
            color=discord.Color.teal(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="Channel", value=f"{channel.name} (`{channel.id}`)", inline=False)
        embed.add_field(name="Owner", value=f"<@{owner_id}>", inline=True)
        embed.add_field(name="Staff", value=f"{user} (`{user.id}`)", inline=True)
        try:
            await log_ch.send(embed=embed)
        except discord.HTTPException:
            pass


class TicketCreateView(discord.ui.View):
    """Panel button to create a new ticket."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Create Ticket",
        style=discord.ButtonStyle.success,
        custom_id="ticket:create",
        emoji="\U0001f3ab",
    )
    async def create_ticket(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return

        guild = interaction.guild
        user = interaction.user
        db = self.bot.db  # type: ignore[attr-defined]

        open_tickets = await db.get_open_tickets_for_user(guild.id, user.id)
        max_tickets = settings.max_tickets_per_user
        if len(open_tickets) >= max_tickets:
            await interaction.response.send_message(
                f"You already have {len(open_tickets)} open ticket(s). "
                f"Please close existing ones before opening a new ticket.",
                ephemeral=True,
            )
            return

        category_id = settings.ticket_category_id
        category = guild.get_channel(category_id) if category_id else None
        if category_id and not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                "Ticket category is not configured correctly. Please contact an administrator.",
                ephemeral=True,
            )
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                attach_files=True,
                read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_channels=True,
                manage_messages=True,
            ),
        }
        if settings.staff_role_id:
            role = guild.get_role(settings.staff_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )
        if settings.admin_role_id:
            role = guild.get_role(settings.admin_role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                )

        await interaction.response.defer(ephemeral=True)

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{user.name}"[:100],
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                reason=f"Ticket opened by {user}",
                topic=f"Ticket owner: {user.id}",
            )
        except discord.Forbidden:
            await interaction.followup.send(
                "I do not have permission to create ticket channels.", ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.followup.send(f"Failed to create ticket: {e}", ephemeral=True)
            return

        await db.create_ticket(guild.id, channel.id, user.id)

        embed = discord.Embed(
            title="Support Ticket",
            description=(
                f"Hello {user.mention}!\n\n"
                "Please describe your issue. A staff member will assist you shortly.\n\n"
                "Use the buttons below to claim, close, or delete this ticket."
            ),
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text=f"Ticket owner: {user}")

        view = TicketControlView(self.bot)
        await channel.send(content=user.mention, embed=embed, view=view)

        await interaction.followup.send(
            f"Your ticket has been created: {channel.mention}", ephemeral=True
        )

        log_id = settings.log_channel_id
        if log_id:
            log_ch = guild.get_channel(log_id)
            if isinstance(log_ch, discord.TextChannel):
                log_embed = discord.Embed(
                    title="Ticket Created",
                    color=discord.Color.green(),
                    timestamp=datetime.now(timezone.utc),
                )
                log_embed.add_field(name="Channel", value=channel.mention, inline=True)
                log_embed.add_field(name="Owner", value=f"{user} (`{user.id}`)", inline=True)
                try:
                    await log_ch.send(embed=log_embed)
                except discord.HTTPException:
                    pass


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(TicketCreateView(self.bot))
        self.bot.add_view(TicketControlView(self.bot))

    @app_commands.command(
        name="ticketpanel",
        description="Post the ticket creation panel (staff only).",
    )
    @app_commands.checks.cooldown(1, 10.0)
    async def ticketpanel(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.user, discord.Member) or interaction.guild is None:
            await interaction.response.send_message("Server only.", ephemeral=True)
            return
        if not _is_staff(interaction.user) and not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "Only staff can post the ticket panel.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Support Tickets \u2014 Stone FFA",
            description=(
                "Need help? Click the button below to open a private support ticket.\n\n"
                "Please provide as much detail as possible so staff can assist you quickly.\n"
                f"You may have up to **{settings.max_tickets_per_user}** open ticket(s) at a time."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Stone FFA Support")

        view = TicketCreateView(self.bot)
        await interaction.response.send_message(embed=embed, view=view)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Tickets(bot))
