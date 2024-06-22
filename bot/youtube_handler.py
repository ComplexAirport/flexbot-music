import pytube  # For downloading videos from YouTube
from pytube.exceptions import RegexMatchError, AgeRestrictedError  # For YouTube error handling
from init import log


class YoutubeObject:
    def __init__(self, url: str):
        self.error: str | None = None
        try:
            # Query for the video at the link, then get the audio only
            log.info(f'Querying youtube link={url}')
            self.youtube: pytube.YouTube = pytube.YouTube(url=url)
            log.info('Query successful')
        # Video couldn't be found error (caused py pytube.Youtube())
        except RegexMatchError:
            log.error('Query unsuccessful, video not found')
            self.error = 'Sorry, I could\'t find the video at the specified url.'
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


# Todo
def search_youtube(query: str, result_count: int = 10):
    search = pytube.Search(query)

    log.debug(f'Searching youtube\nquery={query}')

    while len(search.results) < result_count:
        search.get_next_results()

    results: list[pytube.YouTube] = search.results[:result_count]
    return [(video.title, video.watch_url) for video in results]
