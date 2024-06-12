# This file is where the bot is created and launched
import discord  # Python Discord API (pycord)
from init import TOKEN, GUILD_IDS, GITHUB_LINK, DESCRIPTION  # Configs
from music_handler import MusicHandler  # For handling music features
from log import log  # For debugging

# Specify the permissions for bot
intents = discord.Intents(members=True, message_content=True, voice_states=True, guilds=True)

# Initialize the bot itself
bot = discord.Bot(description=DESCRIPTION, intents=intents)

# Initialize the music features handler
music_handler = MusicHandler(bot)


@bot.event
async def on_ready():
    log.info(f'Logged in as {bot.user}')


@bot.event
async def on_disconnect():
    pass


class MusicPlayerView(discord.ui.View):
    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="⏹️", row=0)
    async def stop_callback(self, button: discord.Button, interaction: discord.Interaction):
        self.disable_all_items()

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, emoji="⏸️", row=0)
    async def pause_callback(self, button: discord.Button, interaction: discord.Interaction):
        pass

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.primary, emoji="▶️", row=0)
    async def resume_callback(self, button: discord.Button, interaction: discord.Interaction):
        pass

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.green, emoji="⏩", row=0)
    async def skip_callback(self, button: discord.Button, interaction: discord.Interaction):
        pass

    @discord.ui.button(label="Volume Up", style=discord.ButtonStyle.green, emoji="🔊", row=1)
    async def volume_up_callback(self, button: discord.Button, interaction: discord.Interaction):
        pass

    @discord.ui.button(label="Volume Down", style=discord.ButtonStyle.green, emoji="🔉", row=1)
    async def volume_down_callback(self, button: discord.Button, interaction: discord.Interaction):
        pass

    @discord.ui.button(label="Mute", style=discord.ButtonStyle.green, emoji="🔇", row=1)
    async def mute_callback(self, button: discord.Button, interaction: discord.Interaction):
        pass


@bot.slash_command(guild_ids=GUILD_IDS, description='Play a song immediately, without queue.')
async def play(ctx: discord.ApplicationContext, link: discord.Option(str)):
    voice: discord.VoiceState = ctx.author.voice
    if voice is None:
        return await ctx.respond('Please join a voice channel so I can play music there!')
    else:
        await ctx.respond('Playing the song...')
        return await music_handler.request_music(ctx=ctx, link=link, queue=False)


@bot.slash_command(guild_ids=GUILD_IDS, description='Add desired song to the queue.')
async def queue(ctx: discord.ApplicationContext, link: discord.Option(str)):
    voice: discord.VoiceState = ctx.author.voice
    if voice is None:
        return await ctx.respond('Please join a voice channel so I can play music there!')
    else:
        await ctx.respond('Queueing the song...')
        await music_handler.request_music(ctx=ctx, link=link, queue=True)


@bot.slash_command(guild_ids=GUILD_IDS, description='Skip current song to the next song in the queue')
async def skip(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond('There is no music to skip!')
    else:
        await ctx.respond('Skipping to the next song...')
        music_handler.request_skip()


@bot.slash_command(guild_ids=GUILD_IDS, description='Pause the music.')
async def pause(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond('There is no music to pause!')
    else:
        await ctx.respond('Pausing the music...')
        music_handler.request_pause()


@bot.slash_command(guild_ids=GUILD_IDS, description='Resume the paused music.')
async def resume(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond('There is no paused music to resume!')
    else:
        await ctx.respond('Resuming the music...')
        music_handler.request_resume()


@bot.slash_command(guild_ids=GUILD_IDS, description='Clear the queue and stop current music.')
async def clear(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond('There is no queue to clear!')
    else:
        await ctx.respond('Clearing the queue...')
        music_handler.request_clear()


@bot.slash_command(guild_ids=GUILD_IDS, description='Set the music volume (in %)')
async def volume(ctx: discord.ApplicationContext, vol: discord.Option(int, description='in percents %')):
    if vol < 0:
        await ctx.respond('Percentage cannot be negative!')
    else:
        await ctx.respond(f'Setting the volume to {vol}%')
        music_handler.request_set_volume(vol)


@bot.slash_command(guild_ids=GUILD_IDS, description='Jump to the song with n-th number (removes all previous songs)')
async def jump(ctx: discord.ApplicationContext, n: discord.Option(int, description='The number of the song')):
    queue_size = music_handler.get_queue_size()
    if queue_size == 0:
        await ctx.respond(f'There are no items in the queue!')
    elif n > queue_size:
        await ctx.respond(f'There are only {queue_size} items in the queue!')
    elif n <= 0:
        await ctx.respond(f'Please enter a valid song number (1 - {queue_size})')
    else:
        await ctx.respond(f'Jumping to song #{n}')
        music_handler.request_jump(n - 1)


@bot.slash_command(guild_ids=GUILD_IDS)
async def status(ctx: discord.ApplicationContext):
    await ctx.respond(music_handler.get_status_msg())


bot.run(TOKEN)
