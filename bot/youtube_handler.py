import pytube  # For downloading videos from YouTube
from pytube.exceptions import RegexMatchError, AgeRestrictedError  # For YouTube error handling
from init import log


class YoutubeObject:
    def __init__(self, query: str):
        self.error: str | None = None
        try:
            # Query for the video at the link, then get the audio only
            log.info(f'Querying youtube link={query}')
            self.youtube: pytube.YouTube = pytube.YouTube(url=query)
            log.info('Query successful')
        # If the 'query' wasn't a valid url, search for it in YouTube and get the first video
        except RegexMatchError:
            search = Search.get_urls(query)
            if len(search) == 0:
                self.error = 'Sorry, I could\'t find the video at the specified url.'
            else:
                self.youtube: pytube.YouTube = pytube.YouTube(url=search[0])
        # Video cannot be queried because of age restriction
        except AgeRestrictedError:
            log.error('Query unsuccessful, age restriction error')
            self.error = 'Sorry, I cannot download the video as it is age restricted.'
        # Other error occurred
        except Exception as e:
            log.error(f'Query unsuccessful, {e}')
            self.error = f'Sorry, an error occurred, {e}'

    def get_stream(self) -> pytube.Stream:
        # Find the stream with only audio
        log.info('Filtering streams with only_audio=True')
        stream = self.youtube.streams.filter(only_audio=True).first()
        log.info('Filter successful')
        return stream


class Search:
    @staticmethod
    def get_urls(query: str) -> list[str]:
        log.info(f'Searching youtube\nquery={query}')
        search = pytube.Search(query)
        return [video.watch_url for video in search.results]

    @staticmethod
    def get_title_urls(query: str) -> list[tuple[str, str]]:
        log.info(f'Searching youtube\nquery={query}')
        search = pytube.Search(query)
        return [(video.title, video.watch_url) for video in search.results]

    # Returns a list of (title, author, views, url)
    @staticmethod
    def get_all_details(query: str) -> list[tuple[str, str, int, str]]:
        log.info(f'Searching youtube\nquery={query}')
        search = pytube.Search(query)
        return [(video.title, video.author, video.views, video.watch_url) for video in search.results]
