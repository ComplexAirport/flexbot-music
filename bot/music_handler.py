# This file is used to request music playing operations, like requesting music, stopping it, changing volume,
# Interacting with queue, etc.

import discord
from discord.errors import NotFound
from init import log, setup_traceback  # For debugging
from youtube_handler import YoutubeObject, human_readable_number  # For YouTube requests

from asyncio import sleep  # For music playing
import time

# For storing queue Data
from collections import deque
from pathlib import Path
from init import OUTPUT_PATH
from enum import Enum  # For tracking music player state

# This line of code fixes AgeRestrictionError when downloading non age-restricted videos
from pytube.innertube import _default_clients
_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID_CREATOR"]

setup_traceback()


class MusicHandler:
    State = Enum('State', ['EMPTY', 'PAUSED', 'PLAYING'])

    def __init__(self, bot: discord.Bot):
        self.vc: discord.VoiceClient | None = None
        self.bot = bot

        # [ tuple(voice_channel, channel_id (to play in), youtube_stream) ]
        # Storing channel id separately as it may change if user joins different channels
        self.queue: deque[tuple[discord.ApplicationContext, int, YoutubeObject]] = deque()

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
        self.__start_time: float = time.time()  # Used for tracking video progress
        self.__pause_time: float | None = None  # Used for pausing progress when pausing audio

        # Other useful variables
        self.__volume: int = 1  # Keep volume for all songs
        self.now_playing: YoutubeObject | None = None  # Name of the song currently playing

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
            self.now_playing = yt
            stream = yt.get_stream()
            log.info(f'Downloading the video...\n\t'
                     f'from={yt.youtube.watch_url}\n\t'
                     f'to={stream.default_filename}')

            video_path = Path(stream.download(output_path=OUTPUT_PATH))

            # If the voice client does not exist or isn't connected to the channel, connect
            if self.vc is None or not self.vc.is_connected():
                log.info(f'Connecting to \'{channel_name}\'...')
                self.vc = await self.bot.get_channel(channel_id).connect()
            # If the bot is in some channel but not the right one, move to it
            else:
                log.info(f'Moving to \'{channel_name}\'...')
                await self.vc.move_to(self.bot.get_channel(channel_id))
                await sleep(1)  # Wait for 1 second to ensure the voice client is connected

            # Create the source from local file
            log.info(f'Creating audio source from {video_path.resolve()} ...')
            source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(str(video_path.resolve())),
                                                  volume=self.__volume)

            # Update the status of all music players, set state to playing
            await self.update_state(MusicHandler.State.PLAYING)

            # Play the audio from source in the voice channel
            log.info(f'Playing the audio in the channel \'{channel_name}\'...')
            self.vc.play(source, after=lambda err: log.error(err) if err else None)
            self.__start_time = time.time()

            # Loop which waits til the audio is over
            while self.vc.is_playing() or self.vc.is_paused():
                if self.__request_skip:
                    log.debug('Terminating current loop...')
                    self.__request_skip = False
                    break
                await self.update_state()
                await sleep(1)

            log.info('The playing loop has finished.')
            self.vc.stop()
            log.info(f'Removing the temporary file {video_path.resolve()} ...')
            try:
                await sleep(1)  # Wait a bit before removing not to cause PermissionError
                video_path.unlink()
            except PermissionError:
                log.warn(f'Temporary file not removed due to PermissionError')

        self.now_playing = None
        self.__is_active = False
        self.__start_time = time.time()
        self.__pause_time = None

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

        youtube = YoutubeObject(link)

        if youtube.error:
            return await ctx.respond(youtube.error)

        # If music is requested in queue mode
        if add_to_queue:
            self.queue.append((ctx, ctx.author.voice.channel.id, youtube))
            log.info('Added request to the end of the queue')
            log.info(f'Queue size={len(self.queue)}')
            if not self.__is_active:
                log.debug('Calling self.__music_task()')
                await self.__music_task()
            else:
                await self.update_state()

        else:
            self.queue.appendleft((ctx, ctx.author.voice.channel.id, youtube))
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
            self.now_playing = self.queue[0][2]
        else:
            self.now_playing = None
        self.__request_skip = True
        time.sleep(1)

    def request_pause(self):
        log.debug('Pause requested')
        self.vc.pause()
        self.__pause_time = time.time()

    def request_resume(self):
        log.debug('Resume requested')
        if self.vc.is_paused():
            self.vc.resume()
            self.__start_time += time.time() - self.__pause_time
            self.__pause_time = None

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
            try:
                await ctx.edit(embed=self.get_queue_status(state=state))
            except NotFound:  # For example, the message was deleted
                log.warn(f'Possible Music Player message/channel removal')
                log.warn(f'Removing {ctx.channel.name} from music player list')
                self.music_player_contexts.remove(ctx)

    # Information functions
    def is_active(self) -> bool:
        return self.__is_active

    def get_volume(self) -> int:
        return int(self.__volume * 100)

    # Get discord.Embed with currently playing music, queue and other information
    # argument state
    def get_queue_status(self, state: State | None = None) -> discord.Embed:
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

        vol = f'{self.get_volume()}% volume' if self.__volume != 0 else 'muted'

        if self.__pause_time:
            spent_time = int(self.__pause_time - self.__start_time)
        else:
            spent_time = int(time.time() - self.__start_time)

        if not self.now_playing:
            progress = ''
        elif spent_time > self.now_playing.youtube.length:
            progress = MusicHandler.readable_time_progress(self.now_playing.youtube.length,
                                                           self.now_playing.youtube.length) + ', '
        else:
            progress = MusicHandler.readable_time_progress(spent_time, self.now_playing.youtube.length) + ', '

        embed = discord.Embed(
            title=f'{status}, {progress}{vol}',
            color=discord.Colour.light_gray()
        )

        if self.now_playing:
            embed.set_thumbnail(url=self.now_playing.youtube.thumbnail_url)
            name, value = MusicHandler.format_main_song(self.now_playing)
            embed.add_field(name=name, value=value, inline=False)

        for idx, m in enumerate(self.queue):
            name, value = MusicHandler.format_queued_song(m[2], self.bot.get_channel(m[1]).name, idx + 1)
            embed.add_field(name=name, value=value, inline=True)

        return embed

    def get_queue_size(self) -> int:
        return len(self.queue)

    def get_voice_channel(self) -> discord.VoiceChannel | None:
        if not self.vc:
            return None
        else:
            return self.vc.channel

    # Generate informative string for the main song (with views, author)
    @staticmethod
    def format_main_song(song: YoutubeObject) -> tuple[str, str]:
        return (
            f'{song.youtube.title}',
            f'**{song.youtube.author}**, **{human_readable_number(song.youtube.views)} Views**'
        )

    # Generate informative string for the song in queue
    @staticmethod
    def format_queued_song(song: YoutubeObject, channel: str, song_number: int | None) -> tuple[str, str]:
        return (
            f'{song_number}) {song.youtube.title}',
            f'**{song.youtube.author}** in _{channel}_'
        )

    # Generate readable string for the current song progress (for example 2:42/4:41)
    @staticmethod
    def readable_time_progress(progress: int, length: int):
        gm = time.gmtime(length)
        fm = '%M:%S' if gm.tm_hour == 0 else '%H:%M:%S'
        progress = time.strftime(fm, time.gmtime(progress))
        total_length = time.strftime(fm, gm)
        return f'{progress}/{total_length}'

    # Checks if a user has right to manipulate music with slash commands or music player buttons
    async def check_valid_interaction(self, ctx: discord.Interaction | discord.ApplicationContext) -> bool:
        author = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        if not author.voice or author.voice.channel != self.vc:
            await ctx.respond(content=(
                f'{ctx.user.mention}, join the voice channel '
                f'{self.get_voice_channel().mention} to use music player'))
            return False
        else:
            return True
