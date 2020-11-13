from dl_plus import ytdl
from dl_plus.extractor import Extractor, ExtractorError, ExtractorPlugin


urljoin = ytdl.import_from('utils', 'urljoin')


__version__ = '0.1.0.dev0'


plugin = ExtractorPlugin(__name__)


class GoodGameBaseExtractor(Extractor):

    DLP_BASE_URL = r'https?://(?:www\.)?goodgame\.ru/'

    _API_BASE_URL = None

    def _fetch(self, endpoint, *, description, item_id, **query_args):
        """
        Fetch the resource using GoodGame API.

        The `endpoint` argument is the part of the resource path relative
        to the `_API_BASE_URL`.

        The following keyword arguments are required by this method:
            * `item_id` -- item identifier (for logging purposes).
            * `description` -- human-readable resource description (for logging
            purposes).

        Any additional keyword arguments are used to build URI query component.
        """
        return self._download_json(
            urljoin(self._API_BASE_URL, endpoint),
            item_id,
            query=query_args,
            note=f'Downloading {description} metadata',
            errnote=f'Unable to download {description} metadata',
        )


@plugin.register('stream')
class GoodGameStreamExtractor(GoodGameBaseExtractor):

    DLP_REL_URL = (
        r'(?:channel/(?P<channel_key>[^/#?]+)/?|player/?\?(?P<src>[^&#?]+))')

    _API_BASE_URL = 'https://goodgame.ru/api/'
    _HLS_URL_TEMPLATE = 'https://hls.goodgame.ru/manifest/{src}_master.m3u8'

    def _real_extract(self, url):
        channel_key, src = self.dlp_match(url).group('channel_key', 'src')
        if not channel_key:
            player_info = self._fetch(
                'player', src=src, fmt='json',
                item_id=src, description='player info',
            )
            try:
                channel_key = player_info['channel_key']
            except KeyError:
                raise ExtractorError('channel_key is not found', expected=True)
        streams_info = self._fetch(
            'getchannelstatus', id=channel_key, fmt='json',
            item_id=channel_key, description='stream info',
        )
        if isinstance(streams_info, list):
            # API returns an empty array with 200 if the stream is not found.
            raise ExtractorError(f'{channel_key} is not found', expected=True)
        if not isinstance(streams_info, dict) or len(streams_info) != 1:
            raise ExtractorError(f'Unexpected response: {streams_info!r}')
        stream_info = next(iter(streams_info.values()))
        try:
            stream_status = stream_info['status']
        except KeyError:
            raise ExtractorError('Stream status is not found')
        if stream_status == 'Dead':
            raise ExtractorError(f'{channel_key} is offline', expected=True)
        if stream_status != 'Live':
            raise ExtractorError(f'Unexpected stream status: {stream_status}')
        if not src:
            try:
                embed = stream_info['embed']
            except KeyError:
                raise ExtractorError('Stream embed HTML is not found')
            src = self._search_regex(
                r'src="[^"?]+\?([^"&#?]+)"', embed, name='src')
        formats = self._extract_m3u8_formats(
            self._HLS_URL_TEMPLATE.format(src=src), channel_key, 'mp4')
        self._sort_formats(formats)
        return {
            'id': str(channel_key),
            'title': stream_info['title'],
            'is_live': True,
            'formats': formats,
        }


@plugin.register('vod')
class GoodGameVODExtractor(GoodGameBaseExtractor):

    DLP_REL_URL = r'vods/(?P<src>[^/]+)/(?P<timestamp>[0-9TZ:+-]+)'

    _STORAGE_BASE_URL = 'https://storage2.goodgame.ru/'
    _API_BASE_URL = _STORAGE_BASE_URL + 'api/json/'

    def _real_extract(self, url):
        src, timestamp = self.dlp_match(url).group('src', 'timestamp')
        vods_info = self._fetch(
            'channel/video', streamId=src,
            item_id=src, description='vods info',
        )
        for vod_info in vods_info['vods']:
            if vod_info['moddate'] == timestamp:
                break
        else:
            raise ExtractorError('vod info not found')
        return {
            'id': f'{src}/{timestamp}',
            'title': timestamp,
            'url': urljoin(self._STORAGE_BASE_URL, vod_info['mp4path']),
        }


@plugin.register('clip')
class GoodGameClipExtractor(GoodGameBaseExtractor):

    DLP_REL_URL = r'clip/(?P<id>\d+)'

    _API_BASE_URL = 'https://goodgame.ru/ajax/'

    def _real_extract(self, url):
        clip_id = self._match_id(url)
        clip_info = self._fetch(
            f'clip/{clip_id}',
            item_id=clip_id, description='clip info',
        )
        return {
            'id': clip_id,
            'title': clip_info.get('title', clip_id),
            'url': clip_info['src'],
        }
