"""
This file is where the bot is created and launched
NOTE: For script to work ffmpeg should be installed and added to system PATH
PyNaCl library should also be installed
"""

import discord  # Python Discord API (pycord)
from init import TOKEN, GUILD_IDS, HELP_MESSAGE, DESCRIPTION, log, setup_traceback  # Configs
from music_handler import MusicHandler  # For handling music features

setup_traceback()

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
    default_volume_change: int = 20

    @staticmethod  # This function turns plain string into an embed to display in messages
    def get_embed(text: str) -> discord.Embed:
        return discord.Embed(title=text, color=discord.Colour.light_gray())

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="⏹️", row=0)
    async def stop_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to stop'))
        else:
            music_handler.request_clear()
            await interaction.edit(embed=music_handler.get_queue_status())
            await music_handler.update_state()

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, emoji="⏸️", row=0)
    async def pause_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to pause'))
        else:
            music_handler.request_pause()
            await interaction.edit(embed=music_handler.get_queue_status())
            await music_handler.update_state()

    @discord.ui.button(label="Resume", style=discord.ButtonStyle.primary, emoji="▶️", row=0)
    async def resume_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to resume'))
        else:
            music_handler.request_resume()
            await interaction.edit(embed=music_handler.get_queue_status())
            await music_handler.update_state()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.green, emoji="⏩", row=0)
    async def skip_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to skip'))
        else:
            music_handler.request_skip()
            state = MusicHandler.State.EMPTY if music_handler.get_queue_size() == 0 else MusicHandler.State.PLAYING
            await interaction.edit(embed=music_handler.get_queue_status(state))
            await music_handler.update_state()

    # Sets the volume default_volume_change% higher
    @discord.ui.button(label="Volume Up", style=discord.ButtonStyle.green, emoji="🔊", row=1)
    async def volume_up_callback(self, _: discord.Button, interaction: discord.Interaction):
        set_vol = music_handler.get_volume() + MusicPlayerView.default_volume_change
        music_handler.request_set_volume(set_vol)
        await interaction.edit(embed=music_handler.get_queue_status())
        await music_handler.update_state()

    # Sets the volume default_volume_change% lower
    @discord.ui.button(label="Volume Down", style=discord.ButtonStyle.green, emoji="🔉", row=1)
    async def volume_down_callback(self, _: discord.Button, interaction: discord.Interaction):
        set_vol = max(0, music_handler.get_volume() - MusicPlayerView.default_volume_change)
        music_handler.request_set_volume(set_vol)
        await interaction.edit(embed=music_handler.get_queue_status())
        await music_handler.update_state()

    # Sets the volume to 0%
    @discord.ui.button(label="Mute", style=discord.ButtonStyle.green, emoji="🔇", row=1)
    async def mute_callback(self, _: discord.Button, interaction: discord.Interaction):
        music_handler.request_set_volume(0)
        await interaction.edit(embed=music_handler.get_queue_status())
        await music_handler.update_state()

    @discord.ui.button(label="Show status", style=discord.ButtonStyle.secondary, emoji="❔", row=1)
    async def show_status_callback(self, _: discord.Button, interaction: discord.Interaction):
        ctx = await bot.get_application_context(interaction=interaction)
        music_handler.music_player_contexts.append(ctx)
        await interaction.edit(embed=music_handler.get_queue_status())


@bot.slash_command(guild_ids=GUILD_IDS, description='Play a song immediately, without queue.')
async def play(ctx: discord.ApplicationContext, link: discord.Option(str, description='YouTube video link')):
    # If author of the message isn't in any voice channel
    if ctx.author.voice is None:
        return await ctx.respond(
            embed=MusicPlayerView.get_embed('Please join a voice channel so I can play music there!'))

    # Get the music player
    music_player: discord.ApplicationContext = music_handler.get_music_player_from_context(ctx)

    # If this context's channel didn't have music a player
    if music_player == ctx:
        await ctx.respond(view=MusicPlayerView())
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Your music will start playing shortly'))

    # Request the music
    return await music_handler.request_music(ctx=ctx, link=link, add_to_queue=False)


@bot.slash_command(guild_ids=GUILD_IDS, description='Add a song to the queue.')
async def queue(ctx: discord.ApplicationContext, link: discord.Option(str, description='YouTube video link')):
    # If author of the message isn't in any voice channel
    if ctx.author.voice is None:
        return await ctx.respond(
            embed=MusicPlayerView.get_embed('Please join a voice channel so I can play music there!'))

    # Get the music player
    music_player: discord.ApplicationContext = music_handler.get_music_player_from_context(ctx)

    # If this context's channel didn't have music a player
    if music_player == ctx:
        await ctx.respond(view=MusicPlayerView())
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Added your music to the queue'))

    # Request the music
    return await music_handler.request_music(ctx=ctx, link=link, add_to_queue=True)


@bot.slash_command(guild_ids=GUILD_IDS, description='Skip current song to the next song in the queue')
async def skip(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no music to skip!'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Skipped to the next song'))
        music_handler.request_skip()
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Pause the music.')
async def pause(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no music to pause!'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Paused the music'))
        music_handler.request_pause()
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Resume the paused music.')
async def resume(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no paused music to resume!'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Resumed the music'))
        music_handler.request_resume()
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Clear the queue and stop current music.')
async def clear(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no queue to clear!'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Cleared the queue'))
        music_handler.request_clear()


@bot.slash_command(guild_ids=GUILD_IDS, description='Set the music volume (in %)')
async def volume(ctx: discord.ApplicationContext, vol: discord.Option(int, description='in percents %')):
    if vol < 0:
        await ctx.respond(embed=MusicPlayerView.get_embed('Percentage cannot be negative!'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'Set the volume to {vol}%'))
        music_handler.request_set_volume(vol)
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Jump to the song with n-th number (removes all previous songs)')
async def jump(ctx: discord.ApplicationContext, n: discord.Option(int, description='The number of the song')):
    queue_size = music_handler.get_queue_size()
    if queue_size == 0:
        await ctx.respond(embed=MusicPlayerView.get_embed('There are no items in the queue!'))
    elif n > queue_size:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'There are only {queue_size} items in the queue!'))
    elif n <= 0:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'Please enter a valid song number (1 - {queue_size})'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'Jumped to song #{n}'))
        music_handler.request_jump(n - 1)
    await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Remove the song at n-th number')
async def remove(ctx: discord.ApplicationContext, n: discord.Option(int, description='The number of the song')):
    queue_size = music_handler.get_queue_size()
    if queue_size == 0:
        await ctx.respond(embed=MusicPlayerView.get_embed('There are no items in the queue!'))
    elif n > queue_size:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'There are only {queue_size} items in the queue!'))
    elif n <= 0:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'Please enter a valid song number (1 - {queue_size})'))
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'Removed the song #{n}'))
        music_handler.request_remove(n - 1)
    await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Display music controls')
async def controls(ctx: discord.ApplicationContext):
    music_handler.music_player_contexts.append(ctx)
    await ctx.respond(view=MusicPlayerView(), embed=music_handler.get_queue_status())


@bot.slash_command(guild_ids=GUILD_IDS)
async def status(ctx: discord.ApplicationContext):
    music_handler.music_player_contexts.append(ctx)
    await ctx.respond(embed=music_handler.get_queue_status())


@bot.slash_command(guild_ids=GUILD_IDS, description='Display the help message')
async def help(ctx: discord.ApplicationContext):
    await ctx.respond(HELP_MESSAGE)

bot.run(TOKEN)

'''
TODO
1) Turn Show status button into a toggle button
2) Make the Mute button toggle and remember last volume
3) Make the pause and resum buttons the same (toggle)
'''
