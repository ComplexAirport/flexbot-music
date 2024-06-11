import discord  # Python discord API
import pytube  # For downloading videos from YouTube
from discord import ApplicationContext
from pytube.exceptions import RegexMatchError, AgeRestrictedError  # For YouTube error handling
import json  # For reading config file
from asyncio import sleep  # For music playing

# For storing queue Data
from collections import deque
from pathlib import Path

# For debugging purposes
from rich.console import Console

console = Console()  # Note: console.log() is same as print() but with better format (time, date, etc.)

# Load config
with open('./config.json') as config_file:
    config = json.load(config_file)
TOKEN = config['token']
GUILD_IDS = config['guild_ids']
GITHUB_LINK = config['github_link']
DESCRIPTION = config['description']

# Select the permissions for bot and initialize it
intents = discord.Intents(
    members=True,
    message_content=True,
    voice_states=True,
    guilds=True
)
bot = discord.Bot(
    description=DESCRIPTION,
    intents=intents
)


# When bot is successfully launched, notify about it
@bot.event
async def on_ready():
    console.log(f'Logged in as {bot.user}')


@bot.event
async def on_disconnect():
    pass


def request_youtube(query: str) -> tuple[pytube.Stream | None, str | None]:  # the string is a possible error message
    try:
        # Get video at the link, then get the audio only
        yt_obj = pytube.YouTube(query)
        console.log('found the video')
        # Find the stream with only audio
        yt_obj = yt_obj.streams.filter(only_audio=True).first()
        return yt_obj, None
    # Video couldn't be found error (caused py pytube.Youtube())
    except RegexMatchError:
        console.log(f'The video couldn\'t be found.')
        return None, 'Sorry, I could\'t find the video at the specified url.'
    # Video cannot be downloaded because of age restriction
    except AgeRestrictedError:
        console.log(f'The video wasn\'t downloaded because of age restriction')
        return None, 'Sorry, I cannot download the video as it is age restricted.'
    # Other error occurred
    except Exception as e:
        console.log(f'Error occurred: {e}')
        return None, f'Sorry, an error occurred: {e}'


class MusicHandler:
    def __init__(self, voice_client: discord.VoiceClient = None):
        self.vc: discord.VoiceClient = voice_client
        # [ tuple(voice_channel, channel_id (to play in), youtube_stream) ]
        # Storing channel id separately as it may change
        self.queue: deque[tuple[discord.ApplicationContext, int, pytube.Stream | None]] = deque()

        # Flags required for the __music_task
        self.__is_active: bool = False  # Used in methods to check whether __music_task is running
        self.__request_skip: bool = False  # Used to skip playing current song in the __music_task if set to True

        # Other useful variables
        self.__volume: int = 1  # Keep volume for all songs
        self.__currently_playing: str | None = None  # Name of the song currently playing

    # Creates a recursive music playing task
    async def __music_task(self):
        while len(self.queue) > 0:
            self.__is_active = True

            # Get the first element in the queue
            channel, channel_id, yt = self.queue.popleft()
            channel_name = bot.get_channel(channel_id).name

            # Download the video
            console.log(f'downloading "{yt.default_filename}"...')
            video_path = Path(yt.download())
            self.__currently_playing = video_path.stem

            # # If the voice client does not exist or isn't conected to the channel, connect
            if self.vc is None or not self.vc.is_connected():
                self.vc = await bot.get_channel(channel_id).connect()
            # If the bot is in some channel but not the right one, disconnect then join it
            else:
                await self.vc.move_to(bot.get_channel(channel_id))

            # Convert the downloaded mp4 to mp3, then play it in the 'music' voice channel
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(str(video_path.resolve())),
                                                  volume=self.__volume)
            console.log(f'playing "{video_path.name}" in the channel {channel_name}, id={channel_id}')
            self.vc.play(source, after=lambda err: console.log(err) if err else None)

            await channel.send(self.get_status_msg())

            # When the audio is over, disconnect from the voice channel
            while self.vc.is_playing() or self.vc.is_paused():
                if self.__request_skip:
                    self.__request_skip = False
                    break
                await sleep(1)

            console.log(f'the music has ended, disconnecting from \'{channel_name}\', id={channel_id}')
            await self.vc.disconnect()

            console.log('removing the audio file')
            video_path.unlink()

        if self.__is_active:
            await channel.send('*No song left in the queue:thumbsup:.*')
        self.__is_active = False

    async def request_music(self, ctx: discord.ApplicationContext, link: str, queue: bool):
        await ctx.respond('...')

        yt_stream, error = request_youtube(link)

        if error:
            return await ctx.respond(error)

        # If music is requested in queue mode
        if queue:
            self.queue.append((ctx, ctx.author.voice.channel.id, yt_stream))
            console.log('add video to the queue.')
            if not self.__is_active:
                await self.__music_task()
        else:
            self.queue.appendleft((ctx, ctx.author.voice.channel.id, yt_stream))
            console.log('add video to the top of the queue.')
            if self.__is_active:
                self.request_skip()
            else:
                await self.__music_task()

    def request_skip(self):
        self.__request_skip = True

    def request_pause(self):
        self.vc.pause()

    def request_resume(self):
        self.vc.resume()

    def request_clear(self):
        self.queue.clear()
        self.request_skip()

    def request_set_volume(self, vol: int):
        if self.vc:
            self.vc.source.volume = vol / 100
        self.__volume = vol / 100

    def request_remove(self, idx: int):
        del self.queue[idx]

    def request_jump(self, idx: int):
        # Slice the deque (ordinary slicing with [:] is not possible)
        for _ in range(idx):
            self.queue.popleft()
        self.request_skip()

    # Information functions
    def is_active(self) -> bool:
        return self.__is_active

    def get_volume(self) -> int:
        return self.__volume * 100

    def currently_playing(self) -> str:
        return self.__currently_playing

    def get_status_msg(self) -> str:
        if not self.__is_active:
            return '*Nothing to show here*'

        full_status = '*Now playing:*\n' \
                      f'**{self.__currently_playing}** in \'{self.vc.channel.name}\''

        if len(self.queue) > 0:
            full_status += '\n*Queue:*\n'
            for idx, m in enumerate(self.queue):
                full_status += f'#*{idx + 1})* **{Path(m[2].default_filename).stem}** ' \
                               f'in \'{bot.get_channel(m[1])}\'\n'
        return full_status

    def get_queue_size(self) -> int:
        return len(self.queue)


music_bot = MusicHandler()

'''
@bot.slash_command(guild_ids=GUILD_IDS)
async def music(ctx):  #, arg: str = 'help', *args):
    # If no argument was given, display the help message
    if arg == 'help':
        await ctx.send(f'*Need help? Visit our [github page]({GITHUB_PAGE_LINK})!*')

    # Main music playing features
    # 'play' plays the music immediately, while 'queue' places it in the queue
    elif arg in ('play', 'queue'):
        console.log(f'{arg} requested')

        # If the author of the message hasn't joined any voice channel, do not play music
        if ctx.author.voice is None:
            await ctx.reply('Please join a voice channel so I can play the music there!')
        # If no argument was given
        elif len(args) == 0:
            await ctx.reply('Please specify a YouTube link so I can play the audio from there!')
        else:
            link: str = args[0]  # Link to the YouTube video
            console.log(f'link = {link}')
            if arg == 'queue':
                await ctx.reply('Added your song to the queue')
            return await music_bot.request_music(ctx=ctx, link=link, queue=(arg == 'queue'))

    # Skip current music and play the next one in the queue
    elif arg == 'skip':
        console.log('music skip requested')

        if not music_bot.is_active():
            await ctx.reply('There is no music to skip!')
        else:
            music_bot.request_skip()
            await ctx.reply('Skipped to the next song.')

    # Pause the music
    elif arg in ('pause', 'stop'):
        console.log('music pause requested')

        if not music_bot.is_active():
            await ctx.reply('There is no music to pause!')
        else:
            music_bot.request_pause()
            await ctx.reply('Paused the music.')

    # Resume the paused music
    elif arg == 'resume':
        console.log('music resume requested')

        if not music_bot.is_active():
            await ctx.reply('There is no music to resume!')
        else:
            music_bot.request_resume()
            await ctx.reply('Resumed the music.')

    # Adjust the music volume
    # note: volume is specified in percents of the original audio
    elif arg == 'volume':
        console.log('music volume change requested')

        if len(args) == 0:  # If volume wasn't specified
            await ctx.reply(f'Current volume is set to {music_bot.get_volume()}%')
        else:
            volume: str = args[0]
            if not volume.isdigit():  # If entered volume is not a percentage
                await ctx.reply(f'Enter a valid non-negative percentage please')
            else:
                console.log(f'Setting the music volume to {volume}%')
                music_bot.request_set_volume(int(volume))
                await ctx.reply(f'Set the volume to {volume}%')

    # See the queue
    elif arg == 'status':
        console.log('music status display requested')
        await ctx.reply(music_bot.get_status_msg())

    # Clear the queue
    elif arg == 'clear':
        console.log('music clear requested')

        if music_bot.is_active():
            music_bot.request_clear()
            console.log('cleared the queue')

    # Remove the song at the number from queue
    elif arg == 'remove':
        console.log('music queue remove requested')

        queue_size = music_bot.get_queue_size()

        if queue_size == 0:
            return await ctx.reply('The queue is already empty.')
        if len(args) == 0:
            return await ctx.reply('Please specify the number of song (from queue) to remove.')
        n = args[0]
        if not n.isdigit():
            return await ctx.reply('Please provide a valid positive integer.')
        n = int(n)

        if n > queue_size:
            return await ctx.reply(f'Queue only has {queue_size} items.')
        elif n == 0:
            return await ctx.reply('Queue numbering starts from 1.')
        else:
            music_bot.request_remove(n - 1)
            await ctx.reply(f'Removed the song #{n} from the queue.')

    # Jump to song from the queue
    elif arg == 'jump':
        console.log('music queue jump requested')

        queue_size = music_bot.get_queue_size()

        if queue_size == 0:
            return await ctx.reply('The queue is empty.')
        if len(args) == 0:
            return await ctx.reply('Please specify the number of song (from queue) to jump to.')
        n = args[0]
        if not n.isdigit():
            return await ctx.reply('Please provide a valid positive integer.')
        n = int(n)

        if n > queue_size:
            return await ctx.reply(f'Queue only has {queue_size} items.')
        elif n == 0:
            return await ctx.reply('Queue numbering starts from 1.')
        else:
            music_bot.request_jump(n - 1)
            return await ctx.reply(f'Jumped to song #{n}')

    else:
        await ctx.reply('*I don\'t have that feature*')
'''


@bot.slash_command(guild_ids=GUILD_IDS, description='Play a song immediately')
async def play(ctx: discord.ApplicationContext, link: discord.Option(str)):
    voice: discord.VoiceState = ctx.author.voice
    if voice is None:
        return await ctx.respond('Please join a voice channel so I can play music there!', ephemeral=True)
    else:
        return await music_bot.request_music(ctx=ctx, link=link, queue=False)


@bot.slash_command(guild_ids=GUILD_IDS, description='Add desired song to the queue.')
async def queue(ctx: discord.ApplicationContext, link: discord.Option(str)):
    voice: discord.VoiceState = ctx.author.voice
    if voice is None:
        return await ctx.respond('Please join a voice channel so I can play music there!')
    else:
        await music_bot.request_music(ctx=ctx, link=link, queue=True)


@bot.slash_command(guild_ids=GUILD_IDS)
async def skip(ctx: discord.ApplicationContext):
    if not music_bot.is_active():
        await ctx.respond('There is no music to skip!')
    else:
        music_bot.request_skip()
        await ctx.respond('Skipped to the next song.')


@bot.slash_command(guild_ids=GUILD_IDS)
async def pause(ctx: discord.ApplicationContext):
    pass


@bot.slash_command(guild_ids=GUILD_IDS)
async def resume(ctx: discord.ApplicationContext):
    pass


@bot.slash_command(guild_ids=GUILD_IDS)
async def clear(ctx: discord.ApplicationContext):
    pass


@bot.slash_command(guild_ids=GUILD_IDS, description='Set the music volume')
async def volume(ctx: discord.ApplicationContext):
    pass


@bot.slash_command(guild_ids=GUILD_IDS)
async def jump(ctx: discord.ApplicationContext):
    pass


@bot.slash_command(guild_ids=GUILD_IDS)
async def status(ctx: discord.ApplicationContext):
    await ctx.respond(music_bot.get_status_msg())


bot.run(TOKEN)
