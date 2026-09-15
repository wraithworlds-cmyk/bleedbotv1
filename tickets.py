import asyncio
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .database import get_settings, update_setting

def now_sql():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

def render(text, guild, user=None, channel=None, staff=None):
    replacements = {
        "{server}": guild.name,
        "{server_id}": str(guild.id),
        "{channel}": channel.mention if channel else "",
        "{channel_name}": channel.name if channel else "",
        "{user}": user.mention if user else "",
        "{username}": user.name if user else "",
        "{user_id}": str(user.id) if user else "",
        "{staff}": staff.mention if staff else "",
        "{staff_name}": staff.name if staff else "",
    }
    for key, value in replacements.items():
        text = text.replace(key, value)
    return text

class TicketView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Open Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="v1_1:ticket:open")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.create_ticket(interaction)

class CloseView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success, emoji="🙋", custom_id="v1_1:ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message("Staff only.", ephemeral=True)
        row = await self.cog.bot.db.execute(
            "SELECT id, user_id, status FROM tickets WHERE channel_id=?", (interaction.channel.id,)
        )
        ticket = await row.fetchone()
        if not ticket or ticket["status"] != "open":
            return await interaction.response.send_message("This ticket is not open.", ephemeral=True)

        await self.cog.bot.db.execute(
            "UPDATE tickets SET claimed_by=?, last_staff_activity_at=?, last_activity_at=? WHERE channel_id=?",
            (interaction.user.id, now_sql(), now_sql(), interaction.channel.id)
        )
        await self.cog.bot.db.commit()
        await interaction.response.send_message(f"🙋 {interaction.user.mention} claimed this ticket.")

        settings = await get_settings(self.cog.bot.db, interaction.guild.id)
        if settings["ticket_reminders_enabled"]:
            try:
                user = await self.cog.bot.fetch_user(ticket["user_id"])
                msg = render(
                    "🎫 Your ticket in {server} has been claimed by {staff}.",
                    interaction.guild, user=user, channel=interaction.channel, staff=interaction.user
                )
                await user.send(msg)
            except discord.Forbidden:
                pass

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="v1_1:ticket:close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)

class Tickets(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reminder_worker.start()

    async def cog_unload(self):
        self.reminder_worker.cancel()

    async def create_ticket(self, interaction):
        guild = interaction.guild
        settings = await get_settings(self.bot.db, guild.id)
        category = guild.get_channel(settings["ticket_category_id"]) if settings["ticket_category_id"] else None

        existing = await self.bot.db.execute(
            "SELECT channel_id FROM tickets WHERE guild_id=? AND user_id=? AND status='open'",
            (guild.id, interaction.user.id)
        )
        if await existing.fetchone():
            return await interaction.response.send_message("You already have an open ticket.", ephemeral=True)

        me = guild.me
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_channels=True, manage_messages=True
            ),
        }

        # Give members with Manage Channels access to tickets.
        for role in guild.roles:
            if role.permissions.manage_channels and role != guild.default_role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )

        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}".lower()[:90],
            category=category if isinstance(category, discord.CategoryChannel) else None,
            overwrites=overwrites,
            reason="Ticket created",
        )
        stamp = now_sql()
        await self.bot.db.execute(
            """INSERT INTO tickets
               (guild_id,channel_id,user_id,created_at,last_activity_at,last_user_activity_at)
               VALUES (?,?,?,?,?,?)""",
            (guild.id, channel.id, interaction.user.id, stamp, stamp, stamp)
        )
        await self.bot.db.commit()

        embed = discord.Embed(
            title="🎫 Support Ticket",
            description=f"{interaction.user.mention}, describe your issue here.\n\nStaff will be with you shortly."
        )
        await channel.send(embed=embed, view=CloseView(self))
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        try:
            msg = render(
                "🎫 Your ticket has been opened in {server}: {channel}\n\nPlease keep an eye on the ticket for staff replies.",
                guild, user=interaction.user, channel=channel
            )
            await interaction.user.send(msg)
        except discord.Forbidden:
            pass

    async def close_ticket(self, interaction):
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return
        cur = await self.bot.db.execute(
            "SELECT user_id FROM tickets WHERE channel_id=? AND status='open'",
            (channel.id,)
        )
        ticket = await cur.fetchone()
        if not ticket:
            return await interaction.response.send_message("This isn't an open ticket.", ephemeral=True)
        if interaction.user.id != ticket["user_id"] and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "Only the ticket owner or staff can close this ticket.", ephemeral=True
            )

        await self.bot.db.execute(
            "UPDATE tickets SET status='closed', last_activity_at=? WHERE channel_id=?",
            (now_sql(), channel.id)
        )
        await self.bot.db.commit()

        try:
            user = self.bot.get_user(ticket["user_id"]) or await self.bot.fetch_user(ticket["user_id"])
            settings = await get_settings(self.bot.db, interaction.guild.id)
            msg = render(
                "🔒 Your ticket in {server} has been closed.",
                interaction.guild, user=user, channel=channel
            )
            await user.send(msg)
        except discord.Forbidden:
            pass

        await interaction.response.send_message("🔒 Ticket closed. Deleting channel in 5 seconds.")
        await asyncio.sleep(5)
        await channel.delete(reason="Ticket closed")

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        cur = await self.bot.db.execute(
            "SELECT user_id, status FROM tickets WHERE channel_id=?", (message.channel.id,)
        )
        ticket = await cur.fetchone()
        if not ticket or ticket["status"] != "open":
            return

        stamp = now_sql()
        if message.author.id == ticket["user_id"]:
            await self.bot.db.execute(
                "UPDATE tickets SET last_activity_at=?, last_user_activity_at=? WHERE channel_id=?",
                (stamp, stamp, message.channel.id)
            )
        elif message.author.guild_permissions.manage_channels:
            await self.bot.db.execute(
                "UPDATE tickets SET last_activity_at=?, last_staff_activity_at=? WHERE channel_id=?",
                (stamp, stamp, message.channel.id)
            )
        await self.bot.db.commit()

    @tasks.loop(minutes=1)
    async def reminder_worker(self):
        if not self.bot.db:
            return
        cur = await self.bot.db.execute("""
            SELECT t.*, g.ticket_reminder_minutes, g.ticket_reminder_message,
                   g.ticket_reminders_enabled
            FROM tickets t
            JOIN guild_settings g ON g.guild_id=t.guild_id
            WHERE t.status='open' AND g.ticket_reminders_enabled=1
        """)
        rows = await cur.fetchall()
        current = datetime.now(timezone.utc)

        for row in rows:
            channel = self.bot.get_channel(row["channel_id"])
            if not channel:
                continue

            # Reminders are only sent when the USER is waiting for staff:
            # user activity must be newer than staff activity, and no reminder
            # has been sent within the configured interval.
            try:
                user_last = datetime.fromisoformat(row["last_user_activity_at"] + "+00:00")
                staff_last = (
                    datetime.fromisoformat(row["last_staff_activity_at"] + "+00:00")
                    if row["last_staff_activity_at"] else None
                )
                reminder_last = (
                    datetime.fromisoformat(row["last_reminder_at"] + "+00:00")
                    if row["last_reminder_at"] else None
                )
            except ValueError:
                continue

            waiting = staff_last is None or user_last > staff_last
            due_from_activity = (current - user_last).total_seconds() >= row["ticket_reminder_minutes"] * 60
            due_from_previous = reminder_last is None or (
                current - reminder_last
            ).total_seconds() >= row["ticket_reminder_minutes"] * 60

            if not (waiting and due_from_activity and due_from_previous):
                continue

            try:
                user = self.bot.get_user(row["user_id"]) or await self.bot.fetch_user(row["user_id"])
                message = render(
                    row["ticket_reminder_message"],
                    channel.guild, user=user, channel=channel
                )
                await user.send(message)
                await self.bot.db.execute(
                    "UPDATE tickets SET last_reminder_at=? WHERE channel_id=?",
                    (now_sql(), channel.id)
                )
                await self.bot.db.commit()
            except discord.Forbidden:
                # DMs closed; don't hammer them every minute. Mark reminder time.
                await self.bot.db.execute(
                    "UPDATE tickets SET last_reminder_at=? WHERE channel_id=?",
                    (now_sql(), channel.id)
                )
                await self.bot.db.commit()
            except discord.HTTPException:
                pass

    @reminder_worker.before_loop
    async def before_reminder_worker(self):
        await self.bot.wait_until_ready()

    tickets = app_commands.Group(name="tickets", description="Ticket system.")

    @tickets.command(name="setup", description="Create a ticket panel in this channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_panel(self, interaction):
        settings = await get_settings(self.bot.db, interaction.guild.id)
        category = interaction.guild.get_channel(settings["ticket_category_id"]) if settings["ticket_category_id"] else None
        if not isinstance(category, discord.CategoryChannel):
            category = await interaction.guild.create_category("Tickets")
            await update_setting(self.bot.db, interaction.guild.id, "ticket_category_id", category.id)

        embed = discord.Embed(
            title="🎫 Need help?",
            description="Click **Open Ticket** below to create a private support ticket."
        )
        await interaction.channel.send(embed=embed, view=TicketView(self))
        await interaction.response.send_message("✅ Ticket panel created.", ephemeral=True)

    @tickets.command(name="category", description="Set the ticket category.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def category(self, interaction, category: discord.CategoryChannel):
        await update_setting(self.bot.db, interaction.guild.id, "ticket_category_id", category.id)
        await interaction.response.send_message(f"✅ Ticket category set to {category.mention}.")

    @tickets.command(name="reminders", description="Enable/disable ticket DM reminders.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reminders(
        self, interaction, enabled: bool,
        minutes: app_commands.Range[int, 5, 10080] = 120
    ):
        await update_setting(self.bot.db, interaction.guild.id, "ticket_reminders_enabled", int(enabled))
        await update_setting(self.bot.db, interaction.guild.id, "ticket_reminder_minutes", minutes)
        await interaction.response.send_message(
            f"✅ Ticket reminders {'enabled' if enabled else 'disabled'}; interval: **{minutes} minutes**."
        )

    @tickets.command(name="reminder-message", description="Customize the ticket reminder DM.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reminder_message(self, interaction, text: str):
        if len(text) > 1900:
            return await interaction.response.send_message("Keep the message under 1900 characters.", ephemeral=True)
        await update_setting(self.bot.db, interaction.guild.id, "ticket_reminder_message", text)
        await interaction.response.send_message("✅ Ticket reminder message updated.")

    @tickets.command(name="reminder-preview", description="Preview the ticket reminder DM.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reminder_preview(self, interaction):
        settings = await get_settings(self.bot.db, interaction.guild.id)
        text = render(
            settings["ticket_reminder_message"],
            interaction.guild,
            user=interaction.user,
            channel=interaction.channel
        )
        await interaction.response.send_message(text, ephemeral=True)

async def setup(bot):
    cog = Tickets(bot)
    await bot.add_cog(cog)
    bot.tree.add_command(cog.tickets)
    bot.add_view(TicketView(cog))
    bot.add_view(CloseView(cog))
