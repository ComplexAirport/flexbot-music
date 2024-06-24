# This file is used to request music playing operations, like requesting music, stopping it, changing volume,
# Interacting with queue, etc.

import discord  # py-cord - Python Discord Library
from discord.errors import NotFound  # Message not found error (for example)
from init import log, setup_traceback  # For debugging purposes
from youtube_handler import YoutubeObject  # For YouTube requests

from asyncio import sleep
import time  # For time tracking features

from collections import deque  # For storing music
from pathlib import Path
from init import OUTPUT_PATH  # Where the music is downloaded
from enum import Enum  # For tracking music player state

# Fixes pytube AgeRestrictionError bug when downloading non age-restricted videos
from pytube.innertube import _default_clients

_default_clients["ANDROID_MUSIC"] = _default_clients["ANDROID_CREATOR"]

# Setup beautiful traceback provided by rich library
setup_traceback()


class MusicHandler:
    # Possible states of the music player
    State = Enum('State', ['EMPTY', 'PAUSED', 'PLAYING', 'PROCESSING', 'DOWNLOADING'])

    def __init__(self, bot: discord.Bot):
        self.vc: discord.VoiceClient | None = None
        self.bot = bot

        # [ tuple(voice_channel, channel_id (to play in), youtube_stream) ]
        # Storing channel id separately as it may change if user joins different channels
        self.queue: deque[tuple[discord.ApplicationContext, int, YoutubeObject]] = deque()

        """
        List that keeps contexts of all music players.
        The purpose of this list is to let the bot update all the music player embeds
        in all channels when the song state (for example, volume) changes. 
        It's also used not to let bot send music player to the same channel twice (if not requested with /controls)
        see the slash commands /play and /queue for usage mentioned above
        """
        self.music_player_contexts: list[discord.ApplicationContext] = []

        self.__is_active: bool = False  # Used check whether __music_task is running
        self.__request_skip: bool = False  # Skips current song (see __music_task) if set to True

        self.__start_time: float = time.time()  # Used to track video progress
        self.__pause_time: float | None = None  # Used to pause progress when pausing audio

        self.__volume: int = 1  # Keep current volume
        self.now_playing: YoutubeObject | None = None  # Store currently playing song

    # Loops and plays every song from the queue
    async def __music_task(self):
        self.__is_active = True

        while len(self.queue) > 0:
            # Pop first element in the queue and get it's data
            channel, channel_id, yt = self.queue.popleft()
            channel_name = self.bot.get_channel(channel_id).name

            log.info(f'Target channel {channel_name}\n\t'
                     f'id={channel_id}')

            self.now_playing = yt

            # Get the video stream
            stream = yt.get_stream()

            # Update current player state to DOWNLOADING
            await self.update_state(MusicHandler.State.DOWNLOADING)

            log.info(f'Downloading the video...\n\t'
                     f'from={yt.youtube.watch_url}\n\t'
                     f'to={stream.default_filename}')

            # Download the audio
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

            # Update current player state to PLAYING
            await self.update_state(MusicHandler.State.PLAYING)

            log.info(f'Playing the audio in the channel \'{channel_name}\'...')

            # Play the audio from source in the voice channel
            self.vc.play(source, after=lambda err: log.error(err) if err else None)

            # Store playing start time
            self.__start_time = time.time()

            # Loop which waits until the audio is over
            while self.vc.is_playing() or self.vc.is_paused():
                # If a skip is requested, break immediately
                if self.__request_skip:
                    log.debug('Terminating current loop...')
                    self.__request_skip = False
                    break

                # Update current state (usually only the time updates)
                await self.update_state()
                await sleep(1)

            log.info('The playing loop has finished.')

            # Stop playing
            self.vc.stop()

            log.info(f'Removing the temporary file {video_path.resolve()} ...')

            # Remove the locally saved audio file
            try:
                await sleep(1)  # Wait a bit before removing not to cause PermissionError
                video_path.unlink()
            except PermissionError:
                log.warn(f'Temporary file not removed due to PermissionError')

        self.now_playing = None
        self.__is_active = False
        self.__start_time = time.time()
        self.__pause_time = None

        # Update the status of all music players, set state to EMPTY (the queue is empty)
        await self.update_state(MusicHandler.State.EMPTY)

        # If voice client is still in a channel, disconnect
        if self.vc:
            log.info(f'Disconnecting from \'{self.vc.channel.name}\'...')

            await self.vc.disconnect()

    # Request play of a music
    async def request_music(self, ctx: discord.ApplicationContext, query: str, add_to_queue: bool):
        log.debug('Music Handler request\n\t'
                  f'queue={add_to_queue}\n\t'
                  f'query={query}')

        # Get the YouTube object
        youtube = YoutubeObject(query)

        if youtube.error:
            return await ctx.respond(youtube.error)

        log.info(f'Music request add_to_queue={add_to_queue}\nQueue size={len(self.queue)}')

        # If /queue is used, song will be added to the end of the queue
        if add_to_queue:
            self.queue.append((ctx, ctx.author.voice.channel.id, youtube))

        # if /play is used, song will be added to the beginning of the queue (and skip will be requested)
        else:
            self.queue.appendleft((ctx, ctx.author.voice.channel.id, youtube))

        # If __music_task is not active, call it
        if not self.__is_active:
            log.debug('Calling self.__music_task()')
            await self.__music_task()

        # If a song is playing, and no queueing is requested
        # skip it so that the next song playing will be requested one
        elif not add_to_queue:
            self.request_skip()

    def request_skip(self):
        log.debug('Skip requested')

        # With self.__request_skip=True, playing loop in self.__music_task will terminate
        self.__request_skip = True
        time.sleep(1)

    def request_pause(self):
        log.debug('Pause requested')
        self.vc.pause()

        # Store the time of pause (for proper audio progress display)
        self.__pause_time = time.time()

    def request_resume(self):
        log.debug('Resume requested')
        if self.vc.is_paused():
            self.vc.resume()

            # Add the duration of pause to starting time for proper audio progress display
            self.__start_time += time.time() - self.__pause_time

            self.__pause_time = None

    def request_clear(self):
        log.debug('Clear requested')

        # Clear the queue
        self.queue.clear()

        # Skip current song
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

        # Slice the deque (slicing with [:] is not possible)
        for _ in range(idx):
            self.queue.popleft()
        self.request_skip()

    """
    If there is a music player in the channel of ctx already, this function will return the context of that music player
    If not, it will be added to the list of music player contexts and be returned
    """
    def get_music_player_from_context(self, ctx: discord.ApplicationContext) -> discord.ApplicationContext:
        # Get context of player in this channel (or None)
        player_ctx = next((c for c in self.music_player_contexts if c.channel == ctx.channel), None)

        # If there isn't a music player in this context, add this context to music players
        # The music player will be sent from slash commands
        if player_ctx is None:
            self.music_player_contexts.append(ctx)
            return ctx

        # Else return the music player of this context
        else:
            return player_ctx

    # Update the state of the music player
    async def update_state(self, state: State | None = None):
        for ctx in self.music_player_contexts:
            try:
                await ctx.edit(embed=self.get_queue_status(state=state))

            except NotFound:  # For example, the message was deleted
                log.warn(f'Possible Music Player message/channel removal')

                self.music_player_contexts.remove(ctx)

    # Information functions
    def is_active(self) -> bool:
        return self.__is_active

    def get_volume(self) -> int:
        return int(self.__volume * 100)

    def get_queue_size(self) -> int:
        return len(self.queue)

    def get_voice_channel(self) -> discord.VoiceChannel | None:
        if not self.vc:
            return None
        else:
            return self.vc.channel

    # Get discord.Embed with currently playing music, queue and other information
    def get_queue_status(self, state: State | None = None) -> discord.Embed:
        if state is not None:
            match state:
                case MusicHandler.State.EMPTY:
                    status = 'Empty'
                case MusicHandler.State.PLAYING:
                    status = 'Playing'
                case MusicHandler.State.PAUSED:
                    status = 'Paused'
                case MusicHandler.State.PROCESSING:
                    status = 'Processing'
                case MusicHandler.State.DOWNLOADING:
                    status = 'Downloading'

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
            if idx == 6:
                embed.add_field(name='...', value='', inline=True)
                break
            name, value = MusicHandler.format_queued_song(m[2], self.bot.get_channel(m[1]).name, idx + 1)
            embed.add_field(name=name, value=value, inline=True)

        return embed

    # Generate informative string for the main song (with views, author)
    @staticmethod
    def format_main_song(song: YoutubeObject) -> tuple[str, str]:
        return (
            f'{song.youtube.title}',
            f'**{song.youtube.author}**, **{MusicHandler.readable_view_count(song.youtube.views)} Views**'
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

    # Convert number (for example view count) to a human-readable format
    @staticmethod
    def readable_view_count(views: int) -> str:
        views = float('{:.3g}'.format(views))
        magnitude = 0
        while abs(views) >= 1000:
            magnitude += 1
            views /= 1000.0
        return '{}{}'.format('{:f}'.format(views).rstrip('0').rstrip('.'), ['', 'K', 'M', 'B', 'T'][magnitude])

    # Checks if a user has right to manipulate music with slash commands or music player buttons
    async def check_valid_interaction(self, ctx: discord.Interaction | discord.ApplicationContext) -> bool:
        author = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
        if not author.voice or author.voice.channel != self.vc.channel:
            await ctx.respond(content=(
                f'{ctx.user.mention}, join the voice channel '
                f'{self.get_voice_channel().mention} to use music player'))
            return False
        else:
            return True
