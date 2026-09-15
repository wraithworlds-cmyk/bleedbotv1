import discord
from discord import app_commands
from discord.ext import commands
from .database import ensure_guild

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def hierarchy_ok(self, interaction, member):
        me = interaction.guild.me
        if member == interaction.user:
            await interaction.response.send_message("You cannot moderate yourself.", ephemeral=True)
            return False
        if member == interaction.guild.owner:
            await interaction.response.send_message("You cannot moderate the server owner.", ephemeral=True)
            return False
        if member.top_role >= me.top_role:
            await interaction.response.send_message("My role must be above that member's highest role.", ephemeral=True)
            return False
        if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            await interaction.response.send_message("That member's highest role is above or equal to yours.", ephemeral=True)
            return False
        return True

    @app_commands.command(name="ban", description="Ban a member.")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.describe(member="Member to ban", reason="Reason")
    async def ban(self, interaction, member: discord.Member, reason: str = "No reason provided"):
        if not await self.hierarchy_ok(interaction, member): return
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}. **Reason:** {reason}")

    @app_commands.command(name="unban", description="Unban a user by ID.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction, user_id: str):
        try:
            user = await self.bot.fetch_user(int(user_id))
            await interaction.guild.unban(user)
            await interaction.response.send_message(f"✅ Unbanned **{user}**.")
        except (ValueError, discord.NotFound):
            await interaction.response.send_message("I couldn't find that banned user.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction, member: discord.Member, reason: str = "No reason provided"):
        if not await self.hierarchy_ok(interaction, member): return
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member.mention}. **Reason:** {reason}")

    @app_commands.command(name="timeout", description="Timeout a member.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
        if not await self.hierarchy_ok(interaction, member): return
        await member.timeout(discord.utils.utcnow() + __import__("datetime").timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(f"⏳ Timed out {member.mention} for **{minutes} minutes**.")

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction, member: discord.Member, reason: str = "No reason provided"):
        await ensure_guild(self.bot.db, interaction.guild.id)
        await self.bot.db.execute(
            "INSERT INTO warnings (guild_id,user_id,moderator_id,reason) VALUES (?,?,?,?)",
            (interaction.guild.id, member.id, interaction.user.id, reason)
        )
        await self.bot.db.commit()
        await interaction.response.send_message(f"⚠️ Warned {member.mention}. **Reason:** {reason}")

    @app_commands.command(name="warnings", description="View a member's warnings.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(self, interaction, member: discord.Member):
        cur = await self.bot.db.execute(
            "SELECT reason, moderator_id, created_at FROM warnings WHERE guild_id=? AND user_id=? ORDER BY id DESC",
            (interaction.guild.id, member.id)
        )
        rows = await cur.fetchall()
        if not rows:
            return await interaction.response.send_message(f"{member.mention} has no warnings.")
        lines = [f"**{i}.** {r['reason']} — <@{r['moderator_id']}> ({r['created_at']})" for i, r in enumerate(rows, 1)]
        embed = discord.Embed(title=f"Warnings — {member}", description="\n".join(lines))
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="purge", description="Delete recent messages.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction, amount: app_commands.Range[int, 1, 100]):
        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages.", ephemeral=True)

    @app_commands.command(name="slowmode", description="Set channel slowmode.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction, seconds: app_commands.Range[int, 0, 21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(f"🐌 Slowmode set to **{seconds}s**.")

    @app_commands.command(name="lock", description="Lock the current channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔒 Channel locked.")

    @app_commands.command(name="unlock", description="Unlock the current channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction):
        overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        await interaction.response.send_message("🔓 Channel unlocked.")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
