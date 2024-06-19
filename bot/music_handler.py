# This file is used to request music playing operations, like requesting music, stopping it, changing volume,
# Interacting with queue, etc.

import discord
from init import log, setup_traceback  # For debugging

import pytube  # For downloading videos from YouTube
from pytube.exceptions import RegexMatchError, AgeRestrictedError  # For YouTube error handling
from asyncio import sleep  # For music playing
import time
from enum import Enum  # For tracking music player state

# For storing queue Data
from collections import deque
from pathlib import Path
from init import OUTPUT_PATH

# This line of code fixes AgeRestrictionError when downloading non age-restricted videos
from pytube.innertube import _default_clients
_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID_CREATOR"]

setup_traceback()


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
    State = Enum('State', ['EMPTY', 'PAUSED', 'PLAYING'])

    def __init__(self, bot: discord.Bot):
        self.vc: discord.VoiceClient | None = None
        self.bot = bot

        # [ tuple(voice_channel, channel_id (to play in), youtube_stream) ]
        # Storing channel id separately as it may change if user joins different channels
        self.queue: deque[tuple[discord.ApplicationContext, int, pytube.Stream | None]] = deque()

        """
        List that keeps contexts of all music players.
        The purpose of this list is to let the bot update all the music player embeds
        in all channels when the song changes. It's also used not to let bot send music player
        to the same channel twice (of not requested with /controls)
        see the slash commands play and queue for above usage
        """
        self.music_player_contexts: list[discord.ApplicationContext] = []

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

            # Update the status of all music players, set state to playing
            await self.update_state(MusicHandler.State.PLAYING)

            # Play the audio from source in the voice channel
            log.info(f'Playing the audio in the channel \'{channel_name}\'...')
            self.vc.play(source, after=lambda err: log.error(err) if err else None)

            # Loop which waits til the audio is over
            while self.vc.is_playing() or self.vc.is_paused():
                if self.__request_skip:
                    log.debug('Terminating current loop...')
                    self.__request_skip = False
                    break
                await sleep(1)

            log.info('The playing loop has finished.')
            self.vc.stop()
            log.info(f'Removing the temporary file {video_path.resolve()} ...')
            try:
                await sleep(1)  # Wait a bit before removing not to cause PermissionError
                video_path.unlink()
            except PermissionError:
                log.warn(f'Temporary file not removed due to PermissionError')

        self.__currently_playing = None
        self.__is_active = False

        # Update the status of all music players, set state to empty (the queue is empty)
        await self.update_state(MusicHandler.State.EMPTY)

        if self.vc:
            # Disconnect from the last voice channel
            log.info(f'Disconnecting from \'{self.vc.channel.name}\'...')
            await self.vc.disconnect()

    async def request_music(self, ctx: discord.ApplicationContext, link: str, add_to_queue: bool):
        log.debug('Music Handler request\n\t'
                  f'queue={add_to_queue}\n\t'
                  f'link={link}')

        yt_stream, error = request_youtube(link)

        if error:
            return await ctx.respond(error)

        # If music is requested in queue mode
        if add_to_queue:
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
        if self.get_queue_size() == 1:
            self.__currently_playing = MusicHandler.__get_song_name(self.queue[0][2])
        else:
            self.__currently_playing = None
        self.__request_skip = True
        time.sleep(1)

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

    def get_music_player_from_context(self, ctx: discord.ApplicationContext) -> discord.ApplicationContext:
        """
        If there is a music player in the channel of ctx already, it will return the context of that music player.
        If not, it will be added to the list of music player contexts and be returned
        """
        player_ctx = next((c for c in self.music_player_contexts if c.channel == ctx.channel), None)
        if player_ctx is None:
            self.music_player_contexts.append(ctx)
            return ctx
        else:
            return player_ctx

    async def update_state(self, state: State | None = None):
        for ctx in self.music_player_contexts:
            await ctx.edit(embed=self.get_queue_status(state=state))

    # Information functions
    def is_active(self) -> bool:
        return self.__is_active

    def get_volume(self) -> int:
        return int(self.__volume * 100)

    def currently_playing(self) -> str:
        return self.__currently_playing

    # Get discord.Embed with currently playing music, queue and other information
    # argument state
    def get_queue_status(self, state: State | None = None) -> discord.Embed:
        """
        :param state: Explicitly set playing status. can be 'empty', 'playing' or 'paused' or None
        """
        if state is not None:
            match state:
                case MusicHandler.State.EMPTY:
                    status = 'Empty'
                case MusicHandler.State.PLAYING:
                    status = 'Playing'
                case MusicHandler.State.PAUSED:
                    status = 'Paused'
        elif self.vc is None or not self.__is_active:
            status = 'Empty'
        elif self.vc.is_playing():
            status = 'Playing'
        elif self.vc.is_paused():
            status = 'Paused'
        else:
            status = 'Processing'

        embed = discord.Embed(
            title=f'{status}, volume - {self.get_volume()}%',
            color=discord.Colour.light_gray()
        )
        if self.__currently_playing:
            embed.add_field(
                name=f'Now playing: **{self.__currently_playing}**',
                value=f'in _{self.vc.channel.name}_',
                inline=False,
            )
        for idx, m in enumerate(self.queue):
            song_number = idx + 1
            song_name = MusicHandler.__get_song_name(m[2])
            song_channel = self.bot.get_channel(m[1])
            embed.add_field(name=f'{song_number}) {song_name}', value=f'in _{song_channel}_', inline=True)

        return embed

    def get_queue_size(self) -> int:
        return len(self.queue)

    @staticmethod
    def __get_song_name(stream: pytube.Stream):
        return Path(stream.default_filename).stem
