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
    default_volume_change: int = 25

    __is_paused: bool = False  # Used for toggling music
    __last_volume: int | None = None  # Used for toggling mute button

    def __init__(self):
        super().__init__(timeout=None)

    @staticmethod  # This function turns plain string into an embed to display in messages
    def get_embed(text: str) -> discord.Embed:
        return discord.Embed(title=text, color=discord.Colour.light_gray())

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.red, emoji="⏹️", row=0)
    async def stop_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to stop'))
        elif not await music_handler.check_valid_interaction(interaction):
            return

        else:
            music_handler.request_clear()
            await interaction.edit(embed=music_handler.get_queue_status())
            await music_handler.update_state()

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.primary, emoji="⏸️", row=0)
    async def pause_resume_callback(self, button: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            return await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to pause'))
        elif not await music_handler.check_valid_interaction(interaction):
            return

        if MusicPlayerView.__is_paused:
            music_handler.request_resume()
            button.label = 'Pause'
            button.emoji = '⏸️'
            MusicPlayerView.__is_paused = False
        else:
            music_handler.request_pause()
            button.label = 'Resume'
            button.emoji = '▶️'
            MusicPlayerView.__is_paused = True

        await interaction.edit(embed=music_handler.get_queue_status(), view=self)
        await music_handler.update_state()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.green, emoji="⏩", row=0)
    async def skip_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not music_handler.is_active():
            await interaction.edit(embed=MusicPlayerView.get_embed('There is no music to skip'))
        elif not await music_handler.check_valid_interaction(interaction):
            return

        else:
            music_handler.request_skip()
            state = MusicHandler.State.EMPTY if music_handler.get_queue_size() == 0 else MusicHandler.State.PLAYING
            await interaction.edit(embed=music_handler.get_queue_status(state))
            await music_handler.update_state()

    # Sets the volume default_volume_change% higher
    @discord.ui.button(label="Volume Up", style=discord.ButtonStyle.green, emoji="🔊", row=1)
    async def volume_up_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not await music_handler.check_valid_interaction(interaction):
            return

        set_vol = music_handler.get_volume() + MusicPlayerView.default_volume_change
        music_handler.request_set_volume(set_vol)
        await interaction.edit(embed=music_handler.get_queue_status())
        await music_handler.update_state()

    # Sets the volume default_volume_change% lower
    @discord.ui.button(label="Volume Down", style=discord.ButtonStyle.green, emoji="🔉", row=1)
    async def volume_down_callback(self, _: discord.Button, interaction: discord.Interaction):
        if not await music_handler.check_valid_interaction(interaction):
            return

        set_vol = max(0, music_handler.get_volume() - MusicPlayerView.default_volume_change)
        music_handler.request_set_volume(set_vol)
        await interaction.edit(embed=music_handler.get_queue_status())
        await music_handler.update_state()

    @discord.ui.button(label="Mute", style=discord.ButtonStyle.green, emoji="🔈", row=1)
    async def mute_unmute_callback(self, button: discord.Button, interaction: discord.Interaction):
        if not await music_handler.check_valid_interaction(interaction):
            return

        if MusicPlayerView.__last_volume is not None:
            vol = MusicPlayerView.__last_volume if MusicPlayerView.__last_volume != 0 \
                else MusicPlayerView.default_volume_change
            music_handler.request_set_volume(vol)
            MusicPlayerView.__last_volume = None
            button.label = 'Mute'
            button.emoji = '🔈'
        else:
            MusicPlayerView.__last_volume = music_handler.get_volume()
            music_handler.request_set_volume(0)
            button.label = 'Unmute'
            button.emoji = '🔇'

        await music_handler.update_state()
        await interaction.edit(embed=music_handler.get_queue_status(), view=self)

    # This function is used to remember last set volume, so that when muting and then unmuting
    # bot will set volume to the last set one
    @staticmethod
    def set_last_volume(vol: int):
        MusicPlayerView.__last_volume = vol


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
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Skipped to the next song'))
        music_handler.request_skip()
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Pause the music.')
async def pause(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no music to pause!'))
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Paused the music'))
        music_handler.request_pause()
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Resume the paused music.')
async def resume(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no paused music to resume!'))
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Resumed the music'))
        music_handler.request_resume()
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Clear the queue and stop current music.')
async def clear(ctx: discord.ApplicationContext):
    if not music_handler.is_active():
        await ctx.respond(embed=MusicPlayerView.get_embed('There is no queue to clear!'))
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed('Cleared the queue'))
        music_handler.request_clear()


@bot.slash_command(guild_ids=GUILD_IDS, description='Set the music volume (in %)')
async def volume(ctx: discord.ApplicationContext, vol: discord.Option(int, description='in percents %')):
    if vol < 0:
        await ctx.respond(embed=MusicPlayerView.get_embed('Percentage cannot be negative!'))
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
    else:
        await ctx.respond(embed=MusicPlayerView.get_embed(f'Set the volume to {vol}%'))
        MusicPlayerView.set_last_volume(vol)
        music_handler.request_set_volume(vol)
        await music_handler.update_state()


@bot.slash_command(guild_ids=GUILD_IDS, description='Jump to the song with n-th number (removes all previous songs)')
async def jump(ctx: discord.ApplicationContext, n: discord.Option(int, description='The number of the song')):
    queue_size = music_handler.get_queue_size()
    if queue_size == 0:
        await ctx.respond(embed=MusicPlayerView.get_embed('There are no items in the queue!'))
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
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
    elif not await music_handler.check_valid_interaction(ctx):
        return
        
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
