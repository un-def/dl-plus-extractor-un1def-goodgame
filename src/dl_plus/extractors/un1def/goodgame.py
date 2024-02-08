from dl_plus import ytdl
from dl_plus.extractor import Extractor, ExtractorError, ExtractorPlugin


traverse_obj, urljoin = ytdl.import_from('utils', ['traverse_obj', 'urljoin'])


__version__ = '0.2.0'


plugin = ExtractorPlugin(__name__)


class GoodGameBaseExtractor(Extractor):
    DLP_BASE_URL = r'https?://(?:www\.)?goodgame\.ru/'

    _API_V4_BASE_URL = 'https://goodgame.ru/api/4/'

    def _fetch(self, endpoint, *, description, item_id, **query_args):
        """
        Fetch the resource using GoodGame API.

        The `endpoint` argument is either an absolute URL or an URL relative
        to the `_API_V4_BASE_URL`.

        The following keyword arguments are required by this method:
            * `item_id` -- item identifier (for logging purposes).
            * `description` -- human-readable resource description (for logging
            purposes).

        Any additional keyword arguments are used to build URI query component.
        """
        if not endpoint.startswith('http'):
            endpoint = urljoin(self._API_V4_BASE_URL, endpoint)
        return self._download_json(
            endpoint,
            item_id,
            query=query_args,
            note=f'Downloading {description} data',
            errnote=f'Unable to download {description} data',
        )

    def _fetch_stream_by_stream_key(self, stream_key):
        # stream_id and stream_key are not always the same, see:
        # id = 5, key = "6" (Miker)
        # id = 1644, key = "pomi" (Pomi)
        # there is no API v4 method to fetch stream by key, we use
        # legacy (v1) API to extract id first
        player = self._fetch(
            'https://goodgame.ru/api/player', src=stream_key,
            item_id=stream_key, description='player',
        )
        stream_id = player['channel_id']
        return self._fetch(
            f'streams/2/id/{stream_id}',
            item_id=stream_id, description='stream',
        )


@plugin.register('stream')
class GoodGameStreamExtractor(GoodGameBaseExtractor):
    DLP_REL_URL = (
        r'(?:(?P<username>[^/?#]+)/?(?:#|$)|player\?(?P<stream_key>[^&#]+))')

    _M3U8_URL_TEMPLATE = (
        'https://hls.goodgame.ru/manifest/{stream_key}_master.m3u8')

    def _real_extract(self, url):
        username, stream_key = self._match_valid_url(url).group(
            'username', 'stream_key')
        if username:
            stream = self._fetch(
                f'streams/2/username/{username}',
                item_id=username, description='stream',
            )
            stream_key = stream['streamKey']
        elif stream_key:
            stream = self._fetch_stream_by_stream_key(stream_key)
            username = traverse_obj(stream, ('streamer', 'username'))
        else:
            assert False, 'should not reach here'
        video_id = username or stream_key
        if not stream.get('online', True):
            raise ExtractorError(f'{username} is offline', expected=True)
        m3u8_url = self._M3U8_URL_TEMPLATE.format(stream_key=stream_key)
        formats = self._extract_m3u8_formats(
            m3u8_url, video_id=video_id, fatal=True)
        return {
            'id': video_id,
            'title': stream['title'],
            'creator': username,
            'thumbnail': stream.get('preview'),
            'is_live': True,
            'formats': formats,
        }


@plugin.register('vod')
class GoodGameVODExtractor(GoodGameBaseExtractor):
    DLP_REL_URL = r'vods/(?P<stream_key>[^/]+)/(?P<timestamp>[0-9TZ:+-]+)'

    _STORAGE_BASE_URL = 'https://storage2.goodgame.ru/'
    _THUMBNAIL_KEYS = ('jpgSmall', 'jpgFull', 'png')

    def _real_extract(self, url):
        stream_key, timestamp = self._match_valid_url(url).group(
            'stream_key', 'timestamp')
        video_id = f'{stream_key}/{timestamp}'
        vods = self._fetch(
            urljoin(self._STORAGE_BASE_URL, 'api/json/channel/video'),
            streamId=stream_key,
            item_id=stream_key, description='vods',
        )
        for vod in vods['vods']:
            if vod['moddate'] == timestamp:
                break
        else:
            raise ExtractorError('vod not found')
        if m3u8_path := vod.get('m3u8path'):
            formats = self._extract_m3u8_formats(
                self._build_absolute_url(m3u8_path),
                video_id=video_id, fatal=False,
            )
        else:
            formats = None
        thumbnails = []
        preview_path = vod.get('previewpath', {})
        for preference, key in enumerate(self._THUMBNAIL_KEYS):
            url = preview_path.get(key)
            if not url:
                continue
            thumbnails.append({
                'url': self._build_absolute_url(url),
                'preference': preference,
            })
        stream = self._fetch_stream_by_stream_key(stream_key)
        info_dict = {
            'id': video_id,
            'title': timestamp,
            'creator': traverse_obj(stream, ('streamer', 'username')),
            'thumbnails': thumbnails,
            'is_live': False,
        }
        if formats:
            info_dict['formats'] = formats
        else:
            info_dict['url'] = self._build_absolute_url(vod['mp4path'])
        return info_dict

    def _build_absolute_url(self, url):
        if not url.startswith('http'):
            return urljoin(self._STORAGE_BASE_URL, url)
        return url


@plugin.register('clip')
class GoodGameClipExtractor(GoodGameBaseExtractor):
    DLP_REL_URL = r'clip/(?P<id>\d+)'

    def _real_extract(self, url):
        clip_id = self._match_id(url)
        clip = self._fetch(
            f'clips/2/{clip_id}',
            item_id=clip_id, description='clip',
        )
        return {
            'id': clip_id,
            'title': clip.get('title', clip_id),
            'creator': traverse_obj(clip, ('stream', 'streamer', 'username')),
            'uploader': traverse_obj(clip, ('author', 'username')),
            'thumbnail': clip.get('thumbnail'),
            'view_count': clip.get('views'),
            'timestamp': clip.get('created'),
            'url': clip['src'],
        }
