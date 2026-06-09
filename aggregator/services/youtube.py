import os
import requests
from django.utils import timezone

from aggregator.models import ContentItem, RawItem, Source
from .utils import clean_text, parse_datetime, safe_int, sha256_text

YOUTUBE_API = 'https://www.googleapis.com/youtube/v3'


def _get(url, params):
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def get_uploads_playlist_id(channel_id: str, api_key: str) -> str:
    data = _get(f'{YOUTUBE_API}/channels', {
        'part': 'contentDetails',
        'id': channel_id,
        'key': api_key,
    })
    items = data.get('items', [])
    if not items:
        return ''
    return items[0].get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads', '')


def crawl_youtube_source(source: Source, max_results: int = 20):
    api_key = os.getenv('YOUTUBE_API_KEY', '')
    if not api_key:
        return {'created': 0, 'skipped': 0, 'error': 'missing YOUTUBE_API_KEY'}
    if not source.youtube_channel_id:
        return {'created': 0, 'skipped': 0, 'error': 'missing youtube_channel_id'}

    uploads_playlist_id = get_uploads_playlist_id(source.youtube_channel_id, api_key)
    if not uploads_playlist_id:
        return {'created': 0, 'skipped': 0, 'error': 'could not find uploads playlist'}

    playlist = _get(f'{YOUTUBE_API}/playlistItems', {
        'part': 'snippet,contentDetails',
        'playlistId': uploads_playlist_id,
        'maxResults': min(max_results, 50),
        'key': api_key,
    })

    video_ids = [i.get('contentDetails', {}).get('videoId') for i in playlist.get('items', [])]
    video_ids = [v for v in video_ids if v]
    if not video_ids:
        return {'created': 0, 'skipped': 0, 'error': 'no videos found'}

    videos = _get(f'{YOUTUBE_API}/videos', {
        'part': 'snippet,statistics,contentDetails',
        'id': ','.join(video_ids),
        'key': api_key,
    })

    created = 0
    skipped = 0
    for video in videos.get('items', []):
        video_id = video.get('id', '')
        snippet = video.get('snippet', {})
        stats = video.get('statistics', {})
        title = clean_text(snippet.get('title', ''))
        description = clean_text(snippet.get('description', ''))
        published = parse_datetime(snippet.get('publishedAt'))
        url = f'https://www.youtube.com/watch?v={video_id}'
        content_hash = sha256_text(source.name + video_id + title)

        raw, raw_created = RawItem.objects.get_or_create(
            source=source,
            external_id=video_id,
            defaults={
                'url': url,
                'title': title,
                'description': description[:4000],
                'raw_text': description,
                'raw_json': video,
                'published_at': published,
                'fetched_at': timezone.now(),
                'content_hash': content_hash,
                'status': 'normalized',
            }
        )

        if not raw_created:
            skipped += 1
            continue

        metrics = {
            'view_count': safe_int(stats.get('viewCount')),
            'like_count': safe_int(stats.get('likeCount')),
            'comment_count': safe_int(stats.get('commentCount')),
        }

        ContentItem.objects.create(
            raw_item=raw,
            source=source,
            content_type=ContentItem.ContentType.YOUTUBE_VIDEO,
            title_ta=title,
            body_ta=description,
            url=url,
            author=snippet.get('channelTitle', ''),
            published_at=published,
            metrics=metrics,
        )
        created += 1

    return {'created': created, 'skipped': skipped}
