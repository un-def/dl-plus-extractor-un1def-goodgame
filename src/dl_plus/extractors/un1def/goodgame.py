from dl_plus import ytdl
from dl_plus.extractor import Extractor, ExtractorError, ExtractorPlugin


urljoin = ytdl.import_from('utils', 'urljoin')


__version__ = '0.1.1'


plugin = ExtractorPlugin(__name__)


class GoodGameBaseExtractor(Extractor):

    DLP_BASE_URL = r'https?://(?:www\.)?goodgame\.ru/'

    _API_BASE_URL = 'https://goodgame.ru/api/'

    def _fetch(self, endpoint, *, description, item_id, **query_args):
        """
        Fetch the resource using GoodGame API.

        The `endpoint` argument is either an absolute URL or an URL relative
        to the `_API_BASE_URL`.

        The following keyword arguments are required by this method:
            * `item_id` -- item identifier (for logging purposes).
            * `description` -- human-readable resource description (for logging
            purposes).

        Any additional keyword arguments are used to build URI query component.
        """
        if not endpoint.startswith('http'):
            endpoint = urljoin(self._API_BASE_URL, endpoint)
        return self._download_json(
            endpoint,
            item_id,
            query=query_args,
            note=f'Downloading {description} metadata',
            errnote=f'Unable to download {description} metadata',
        )

    def _fetch_player_info(self, src):
        return self._fetch(
            'player', src=src, fmt='json',
            item_id=src, description='player info',
        )


@plugin.register('stream')
class GoodGameStreamExtractor(GoodGameBaseExtractor):

    DLP_REL_URL = (
        r'(?:channel/(?P<channel_key>[^/#?]+)/?|player/?\?(?P<src>[^&#?]+))')

    _M3U8_URL_TEMPLATES = (
        'https://hls.goodgame.ru/manifest/{src}_master.m3u8',
        'https://hlss.goodgame.ru/hls/{src}.m3u8',
    )

    def _fetch_stream_info(self, channel_key):
        streams_info = self._fetch(
            'getchannelstatus', id=channel_key, fmt='json',
            item_id=channel_key, description='stream info',
        )
        if isinstance(streams_info, list):
            # API returns an empty array with 200 if the stream is not found.
            raise ExtractorError(f'{channel_key} is not found', expected=True)
        if not isinstance(streams_info, dict) or len(streams_info) != 1:
            raise ExtractorError(f'Unexpected response: {streams_info!r}')
        return next(iter(streams_info.values()))

    def _real_extract(self, url):
        channel_key, src = self.dlp_match(url).group('channel_key', 'src')
        if not src:
            stream_info = self._fetch_stream_info(channel_key)
            try:
                embed = stream_info['embed']
            except KeyError:
                raise ExtractorError('Stream embed HTML is not found')
            src = self._search_regex(
                r'src="[^"?]+\?([^"&#?]+)"', embed, name='src')
        player_info = self._fetch_player_info(src)
        if not channel_key:
            try:
                channel_key = player_info['channel_key']
            except KeyError:
                raise ExtractorError('channel_key is not found', expected=True)
            stream_info = self._fetch_stream_info(channel_key)
        try:
            stream_status = stream_info['status']
        except KeyError:
            raise ExtractorError('Stream status is not found')
        if stream_status == 'Dead':
            raise ExtractorError(f'{channel_key} is offline', expected=True)
        if stream_status != 'Live':
            raise ExtractorError(f'Unexpected stream status: {stream_status}')
        for m3u8_url_template in self._M3U8_URL_TEMPLATES:
            m3u8_url = m3u8_url_template.format(src=src)
            formats = self._extract_m3u8_formats(
                m3u8_url, video_id=channel_key, ext='mp4', fatal=False)
            if formats:
                break
        else:
            raise ExtractorError('failed to fetch/parse m3u8')
        self._sort_formats(formats)
        return {
            'id': channel_key,
            'title': stream_info['title'],
            'description': stream_info.get('description'),
            'creator': player_info.get('streamer_name'),
            'uploader': player_info.get('streamer_name'),
            'uploader_id': player_info.get('streamer_id'),
            'thumbnail': stream_info.get('img'),
            'is_live': True,
            'formats': formats,
        }


@plugin.register('vod')
class GoodGameVODExtractor(GoodGameBaseExtractor):

    DLP_REL_URL = r'vods/(?P<src>[^/]+)/(?P<timestamp>[0-9TZ:+-]+)'

    _STORAGE_BASE_URL = 'https://storage2.goodgame.ru/'
    _THUMBNAIL_KEYS = ('jpgSmall', 'jpgFull', 'png')

    def _real_extract(self, url):
        src, timestamp = self.dlp_match(url).group('src', 'timestamp')
        vods_info = self._fetch(
            self._STORAGE_BASE_URL + 'api/json/channel/video', streamId=src,
            item_id=src, description='vods info',
        )
        for vod_info in vods_info['vods']:
            if vod_info['moddate'] == timestamp:
                break
        else:
            raise ExtractorError('vod info not found')
        player_info = self._fetch_player_info(src)
        previewpath = vod_info.get('previewpath', {})
        thumbnails = []
        for preference, key in enumerate(self._THUMBNAIL_KEYS):
            url = previewpath.get(key)
            if not url:
                continue
            if not url.startswith('http'):
                url = urljoin(self._STORAGE_BASE_URL, url)
            thumbnails.append({'url': url, 'preference': preference})
        channel_key = player_info.get('channel_key')
        return {
            'id': f'{channel_key or src} - {timestamp}',
            'title': timestamp,
            'display_id': channel_key,
            'creator': player_info.get('streamer_name'),
            'uploader': player_info.get('streamer_name'),
            'uploader_id': player_info.get('streamer_id'),
            'thumbnails': thumbnails,
            'is_live': False,
            'url': urljoin(self._STORAGE_BASE_URL, vod_info['mp4path']),
        }


@plugin.register('clip')
class GoodGameClipExtractor(GoodGameBaseExtractor):

    DLP_REL_URL = r'clip/(?P<id>\d+)'

    def _real_extract(self, url):
        clip_id = self._match_id(url)
        clip_info = self._fetch(
            'https://goodgame.ru/ajax/clip/' + clip_id,
            item_id=clip_id, description='clip info',
        )
        return {
            'id': clip_id,
            'title': clip_info.get('title', clip_id),
            'creator': clip_info.get('streamer'),
            'uploader': clip_info.get('author'),
            'thumbnail': clip_info.get('thumbnail'),
            'view_count': clip_info.get('views'),
            'timestamp': clip_info.get('created'),
            'is_live': False,
            'url': clip_info['src'],
        }
