from dl_plus import ytdl
from dl_plus.extractor import Extractor, ExtractorError, ExtractorPlugin


urljoin = ytdl.import_from('utils', 'urljoin')


__version__ = '0.2.0.dev0'


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
    DLP_REL_URL = r'(?P<username>[^/?#]+)/?(?:[?#]|$)'

    _M3U8_URL_TEMPLATE = (
        'https://hls.goodgame.ru/manifest/{stream_key}_master.m3u8')

    def _real_extract(self, url):
        username = self._match_valid_url(url).group('username')
        stream = self._fetch(
            f'https://goodgame.ru/api/4/streams/2/username/{username}',
            item_id=username, description='stream',
        )
        if not stream['online']:
            raise ExtractorError(f'{username} is offline', expected=True)
        m3u8_url = self._M3U8_URL_TEMPLATE.format(
            stream_key=stream['streamKey'])
        formats = self._extract_m3u8_formats(
            m3u8_url, video_id=username, fatal=True)
        return {
            'id': username,
            'title': stream['title'],
            'creator': username,
            'thumbnail': stream.get('preview'),
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
