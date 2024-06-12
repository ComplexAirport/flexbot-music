# This file is used to request music playing operations, like requesting music, stopping it, changing volume,
# Interacting with queue, etc.

import discord
from log import log  # For debugging

import pytube  # For downloading videos from YouTube
from pytube.exceptions import RegexMatchError, AgeRestrictedError  # For YouTube error handling
from asyncio import sleep  # For music playing

# For storing queue Data
from collections import deque
from pathlib import Path
from init import OUTPUT_PATH


def request_youtube(query: str) -> tuple[pytube.Stream | None, str | None]:  # the string is a possible error msg
    try:
        # Query for the video at the link, then get the audio only
        log.info(f'Querying youtube link={query}')
        yt_obj = pytube.YouTube(query)
        log.info('Query successful')

        # Find the stream with only audio
        log.info('Filtering streams with only_audio=True')
        yt_obj = yt_obj.streams.filter(only_audio=True).first()
        log.info('Filter successful')
        return yt_obj, None
    # Video couldn't be found error (caused py pytube.Youtube())
    except RegexMatchError:
        log.error('Query unsuccessful, video not found')
        return None, 'Sorry, I could\'t find the video at the specified url.'
    # Video cannot be downloaded because of age restriction
    except AgeRestrictedError:
        log.error('Query unsuccessful, age restriction error')
        return None, 'Sorry, I cannot download the video as it is age restricted.'
    # Other error occurred
    except Exception as e:
        log.error(f'Query unsuccessful, {e}')
        return None, f'Sorry, an error occurred'


class MusicHandler:
    def __init__(self, bot: discord.Bot):
        self.vc: discord.VoiceClient | None = None
        self.bot = bot

        # [ tuple(voice_channel, channel_id (to play in), youtube_stream) ]
        # Storing channel id separately as it may change if user joins different channels
        self.queue: deque[tuple[discord.ApplicationContext, int, pytube.Stream | None]] = deque()

        # Flags required for the __music_task
        self.__is_active: bool = False  # Used in methods to check whether __music_task is running
        self.__request_skip: bool = False  # Used to skip playing current song in the __music_task if set to True

        # Other useful variables
        self.__volume: int = 1  # Keep volume for all songs
        self.__currently_playing: str | None = None  # Name of the song currently playing

    # Creates a recursive music playing task
    async def __music_task(self):
        self.__is_active = True

        while len(self.queue) > 0:
            # Get the first element in the queue
            channel, channel_id, yt = self.queue.popleft()
            channel_name = self.bot.get_channel(channel_id).name
            log.info(f'Target channel {channel_name}\n\t'
                     f'id={channel_id}')

            # Download the video
            log.info(f'Downloading the video...\n\t'
                     f'from={yt.url}\n\t'
                     f'to={yt.default_filename}')

            video_path = Path(yt.download(output_path=OUTPUT_PATH))
            self.__currently_playing = video_path.stem

            # If the voice client does not exist or isn't connected to the channel, connect
            if self.vc is None or not self.vc.is_connected():
                log.info(f'Connecting to \'{channel_name}\'...')
                self.vc = await self.bot.get_channel(channel_id).connect()
            # If the bot is in some channel but not the right one, disconnect then join it
            else:
                log.info(f'Moving to \'{channel_name}\'...')
                await self.vc.move_to(self.bot.get_channel(channel_id))

            # Create the source from local file
            log.info(f'Creating audio source from {video_path.resolve()} ...')
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(str(video_path.resolve())),
                                                  volume=self.__volume)

            # Play the audio from source in the voice channel
            log.info(f'Playing the audio in the channel \'{channel_name}\'...')
            self.vc.play(source, after=lambda err: log.error(err) if err else None)

            # Show the current status in the chat
            await channel.send(self.get_status_msg())

            # Loop which waits til the audio is over
            while self.vc.is_playing() or self.vc.is_paused():
                if self.__request_skip:
                    log.debug('Terminating current loop...')
                    self.__request_skip = False
                    break
                await sleep(1)

            log.info('The playing loop has finished.')

            self.vc.stop()
            # await self.vc.disconnect()

            log.info(f'Removing the temporary file {video_path.resolve()} ...')

            try:
                video_path.unlink()
            except PermissionError:
                log.warn(f'Temporary file not removed due to PermissionError')
                pass

        self.__is_active = False

        if self.vc:
            # Disconnect from the last voice channel
            log.info(f'Disconnecting from \'{self.vc.channel.name}\'...')
            await self.vc.disconnect()

            # Remove the temporary music storage folder
            # log.info(f'Removing the temporary audio folder \'{OUTPUT_PATH}\'')
            # Path(OUTPUT_PATH).rmdir()

        await channel.send('*No song left in the queue:thumbsup:.*')

    async def request_music(self, ctx: discord.ApplicationContext, link: str, queue: bool):
        log.debug('Music Handler request\n\t'
                  f'queue={queue}\n\t'
                  f'link={link}')

        yt_stream, error = request_youtube(link)

        if error:
            return await ctx.respond(error)

        # If music is requested in queue mode
        if queue:
            self.queue.append((ctx, ctx.author.voice.channel.id, yt_stream))
            log.info('Added request to the end of the queue')
            log.info(f'Queue size={len(self.queue)}')
            if not self.__is_active:
                log.debug('Calling self.__music_task()')
                await self.__music_task()
        else:
            self.queue.appendleft((ctx, ctx.author.voice.channel.id, yt_stream))
            log.info('Add request to beginning of the queue')
            log.info(f'Queue size={len(self.queue)}')
            if self.__is_active:
                self.request_skip()
            else:
                log.debug('Calling self.__music_task()')
                await self.__music_task()

    def request_skip(self):
        log.debug('Skip requested')
        self.__request_skip = True

    def request_pause(self):
        log.debug('Pause requested')
        self.vc.pause()

    def request_resume(self):
        log.debug('Resume requested')
        self.vc.resume()

    def request_clear(self):
        log.debug('Clear requested')
        self.queue.clear()
        self.request_skip()

    def request_set_volume(self, vol: int):
        vol /= 100
        log.debug(f'Volume change requested from={self.__volume} to={vol}')
        if self.vc and self.vc.source:
            self.vc.source.volume = vol
        self.__volume = vol

    def request_remove(self, idx: int):
        log.debug(f'Request removal at queue[{idx}]')
        del self.queue[idx]

    def request_jump(self, idx: int):
        log.debug(f'Jump requested to queue[{idx}]')
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
                               f'in \'{self.bot.get_channel(m[1])}\'\n'
        return full_status

    def get_queue_size(self) -> int:
        return len(self.queue)
