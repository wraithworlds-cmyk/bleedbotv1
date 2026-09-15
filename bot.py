import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN is missing. Put it in .env")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=",",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        for extension in (
            "cogs.database",
            "cogs.moderation",
            "cogs.welcome",
            "cogs.tickets",
        ):
            await self.load_extension(extension)

        # Sync slash commands globally. For faster testing, set TEST_GUILD_ID
        # in .env and the bot will sync to that guild instead.
        test_guild = os.getenv("TEST_GUILD_ID")
        if test_guild:
            guild = discord.Object(id=int(test_guild))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            print(f"Synced commands to test guild {test_guild}")
        else:
            await self.tree.sync()
            print("Synced global slash commands")

bot = Bot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")
    print("Version 1 is online.")

if __name__ == "__main__":
    bot.run(TOKEN)
