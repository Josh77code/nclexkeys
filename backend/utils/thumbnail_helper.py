# courses/thumbnail_helper.py
from django.utils import timezone
from cloudinary.uploader import upload, destroy
from cloudinary.utils import cloudinary_url
import logging
import re

logger = logging.getLogger(__name__)


# Helper function for generating video thumbnail URLs
def generate_video_thumbnail_from_upload(video_public_id, course_id):
    """Generate thumbnail from uploaded video using Cloudinary's video thumbnail feature"""
    try:
        current_date = timezone.now()
        thumbnail_folder_path = f"courses/thumbnails/generated/{current_date.year}/{current_date.month:02d}"
        
        # Generate thumbnail using Cloudinary's video thumbnail transformation
        thumbnail_url, _ = cloudinary_url(
            video_public_id,
            resource_type="video",
            format="jpg",
            transformation=[
                {'start_offset': "10%"},  # Take frame at 10% of video duration
                {'width': 1280, 'height': 720, 'crop': 'fill'},
                {'quality': 'auto:good'}
            ]
        )
        
        # Now upload this generated thumbnail as an image to organized folder
        upload_result = upload(
            thumbnail_url,
            resource_type="image",
            folder=thumbnail_folder_path,
            public_id=f"course_{course_id}_thumb_{current_date.strftime('%Y%m%d_%H%M%S')}",
            transformation=[
                {'width': 1280, 'height': 720, 'crop': 'fill'},
                {'quality': 'auto:good'},
                {'format': 'jpg'}
            ],
            tags=[
                'course_thumbnail',
                'auto_generated',
                f'course_id_{course_id}',
                f'year_{current_date.year}',
                f'source_video_{video_public_id}'
            ]
        )
        
        logger.info(f"Thumbnail generated from video: {video_public_id} -> {upload_result['public_id']}")
        return upload_result['secure_url']
        
    except Exception as e:
        logger.error(f"Failed to generate thumbnail from video: {str(e)}")
        return None


def generate_video_url_thumbnail(video_url):
    """Generate thumbnail URL for external video URLs (YouTube, Vimeo, etc.)"""
    try:
        current_date = timezone.now()

        # ---------- YOUTUBE ----------
        if 'youtube.com' in video_url or 'youtu.be' in video_url:
            # Match any YouTube format: watch, shorts, embed, youtu.be
            youtube_regex = r'(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([a-zA-Z0-9_-]{6,})'
            match = re.search(youtube_regex, video_url)
            if match:
                video_id = match.group(1)
                youtube_thumbnail_url = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"

                try:
                    thumbnail_folder_path = f"courses/thumbnails/external/{current_date.year}/{current_date.month:02d}"
                    upload_result = upload(
                        youtube_thumbnail_url,
                        resource_type="image",
                        folder=thumbnail_folder_path,
                        public_id=f"youtube_thumb_{video_id}_{current_date.strftime('%Y%m%d_%H%M%S')}",
                        transformation=[
                            {'width': 1280, 'height': 720, 'crop': 'fill'},
                            {'quality': 'auto:good'},
                            {'format': 'jpg'}
                        ],
                        tags=[
                            'course_thumbnail',
                            'youtube_generated',
                            f'video_id_{video_id}',
                            f'year_{current_date.year}'
                        ]
                    )
                    return upload_result['secure_url']
                except Exception as upload_error:
                    logger.error(f"Failed to upload YouTube thumbnail to Cloudinary: {str(upload_error)}")
                    return youtube_thumbnail_url

        # ---------- VIMEO ----------
        elif 'vimeo.com' in video_url:
            vimeo_regex = r'vimeo\.com/(?:video/)?(\d+)'
            match = re.search(vimeo_regex, video_url)
            if match:
                video_id = match.group(1)

                try:
                    import requests
                    vimeo_api_url = f"https://vimeo.com/api/v2/video/{video_id}.json"
                    response = requests.get(vimeo_api_url, timeout=10)

                    if response.status_code == 200:
                        video_data = response.json()[0]
                        vimeo_thumbnail_url = video_data.get('thumbnail_large') or video_data.get('thumbnail_medium')

                        if vimeo_thumbnail_url:
                            thumbnail_folder_path = f"courses/thumbnails/external/{current_date.year}/{current_date.month:02d}"
                            upload_result = upload(
                                vimeo_thumbnail_url,
                                resource_type="image",
                                folder=thumbnail_folder_path,
                                public_id=f"vimeo_thumb_{video_id}_{current_date.strftime('%Y%m%d_%H%M%S')}",
                                transformation=[
                                    {'width': 1280, 'height': 720, 'crop': 'fill'},
                                    {'quality': 'auto:good'},
                                    {'format': 'jpg'}
                                ],
                                tags=[
                                    'course_thumbnail',
                                    'vimeo_generated',
                                    f'video_id_{video_id}',
                                    f'year_{current_date.year}'
                                ]
                            )
                            return upload_result['secure_url']

                except Exception as vimeo_error:
                    logger.error(f"Failed to get Vimeo thumbnail: {str(vimeo_error)}")
                    return f"https://vumbnail.com/{video_id}.jpg"

    except Exception as general_error:
        logger.error(f"Error in generate_video_url_thumbnail: {str(general_error)}")

    return None



def cleanup_old_thumbnail(old_thumbnail):
    """Helper function to clean up old thumbnails"""
    try:
        if not old_thumbnail:
            return
            
        old_public_id = None
        
        # Get public_id from CloudinaryField
        if hasattr(old_thumbnail, 'public_id'):
            old_public_id = old_thumbnail.public_id
        elif hasattr(old_thumbnail, 'url') and old_thumbnail.url:
            # Extract public_id from URL
            url_parts = old_thumbnail.url.split('/')
            if len(url_parts) > 2:
                # Find the part after 'upload' and before file extension
                try:
                    upload_index = url_parts.index('upload')
                    if upload_index + 1 < len(url_parts):
                        # Join the path parts after upload, removing version if present
                        path_parts = url_parts[upload_index + 1:]
                        if path_parts[0].startswith('v'):  # Version number
                            path_parts = path_parts[1:]
                        
                        # Remove file extension from last part
                        last_part = path_parts[-1]
                        last_part = re.sub(r'\.[^.]+$', '', last_part)
                        path_parts[-1] = last_part
                        
                        old_public_id = '/'.join(path_parts)
                except (ValueError, IndexError):
                    pass
        
        if old_public_id:
            destroy(old_public_id, resource_type="image")
            logger.info(f"Old thumbnail cleaned up: {old_public_id}")
            
    except Exception as cleanup_error:
        logger.error(f"Failed to cleanup old thumbnail: {str(cleanup_error)}")