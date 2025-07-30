# utils/video_processing.py - Video Processing Utilities
import requests
import re
import logging
from urllib.parse import urlparse, parse_qs
from cloudinary.uploader import upload
from cloudinary.utils import cloudinary_url as build_cloudinary_url
from cloudinary import api
import cv2
import tempfile
import os
from django.conf import settings
from moviepy import VideoFileClip

# Graceful imports for optional dependencies
try:
    MOVIEPY_AVAILABLE = True
except ImportError:
    MOVIEPY_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("MoviePy not available. Some video processing features will be limited.")

logger = logging.getLogger(__name__)

def extract_video_duration(video_url_or_path):
    """
    Extract video duration from URL or file path
    Returns duration in seconds or None if failed
    """
    try:
        # Handle different video sources
        if video_url_or_path.startswith('http'):
            # For URL-based videos, try to download temporarily or use API
            if 'youtube.com' in video_url_or_path or 'youtu.be' in video_url_or_path:
                return extract_youtube_duration(video_url_or_path)
            elif 'vimeo.com' in video_url_or_path:
                return extract_vimeo_duration(video_url_or_path)
            elif 'cloudinary.com' in video_url_or_path:
                return extract_cloudinary_duration(video_url_or_path)
            else:
                # Try to get duration from direct video URL
                return extract_direct_video_duration(video_url_or_path)
        else:
            # Local file path
            return extract_local_video_duration(video_url_or_path)
    
    except Exception as e:
        logger.error(f"Error extracting video duration: {str(e)}")
        return None


def extract_youtube_duration(youtube_url):
    """Extract duration from YouTube video using YouTube API or yt-dlp"""
    try:
        # Extract video ID
        video_id = None
        if 'youtube.com' in youtube_url:
            parsed_url = urlparse(youtube_url)
            video_id = parse_qs(parsed_url.query).get('v', [None])[0]
        elif 'youtu.be' in youtube_url:
            video_id = youtube_url.split('/')[-1].split('?')[0]
        
        if not video_id:
            return None
        
        # Try YouTube Data API if available
        youtube_api_key = getattr(settings, 'YOUTUBE_API_KEY', None)
        if youtube_api_key:
            api_url = f"https://www.googleapis.com/youtube/v3/videos"
            params = {
                'id': video_id,
                'part': 'contentDetails',
                'key': youtube_api_key
            }
            
            response = requests.get(api_url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    duration = data['items'][0]['contentDetails']['duration']
                    return parse_youtube_duration(duration)
        
        # Fallback: Try using yt-dlp if available
        try:
            import yt_dlp
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extractaudio': False,
                'format': 'worst'  # We only need metadata
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                return info.get('duration')
        
        except ImportError:
            logger.warning("yt-dlp not available for YouTube duration extraction")
            return None
    
    except Exception as e:
        logger.error(f"Error extracting YouTube duration: {str(e)}")
        return None


def parse_youtube_duration(duration_str):
    """Parse YouTube API duration format (PT4M13S) to seconds"""
    try:
        import re
        
        pattern = r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?'
        match = re.match(pattern, duration_str)
        
        if match:
            hours = int(match.group(1) or 0)
            minutes = int(match.group(2) or 0)
            seconds = int(match.group(3) or 0)
            
            return hours * 3600 + minutes * 60 + seconds
        
        return None
    
    except Exception as e:
        logger.error(f"Error parsing YouTube duration: {str(e)}")
        return None


def extract_vimeo_duration(vimeo_url):
    """Extract duration from Vimeo video using API"""
    try:
        # Extract video ID from URL
        video_id = None
        patterns = [
            r'vimeo\.com/(\d+)',
            r'vimeo\.com/video/(\d+)',
            r'player\.vimeo\.com/video/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, vimeo_url)
            if match:
                video_id = match.group(1)
                break
        
        if not video_id:
            return None
        
        # Use Vimeo oEmbed API (no authentication required)
        oembed_url = f"https://vimeo.com/api/oembed.json?url=https://vimeo.com/{video_id}"
        
        response = requests.get(oembed_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('duration')  # Duration in seconds
        
        return None
    
    except Exception as e:
        logger.error(f"Error extracting Vimeo duration: {str(e)}")
        return None


def extract_cloudinary_duration(cloudinary_url):
    """Extract duration from Cloudinary video using direct analysis"""
    try:
        logger.info(f"Analyzing Cloudinary video directly: {cloudinary_url}")
        
        # Try with moviepy first if available
        if MOVIEPY_AVAILABLE:
            try:
                import tempfile
                import requests
                
                # Download first 10MB for analysis
                response = requests.get(cloudinary_url, stream=True, timeout=30)
                response.raise_for_status()
                
                with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                    temp_path = temp_file.name
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if downloaded >= 10 * 1024 * 1024:  # 10MB limit
                            break
                        temp_file.write(chunk)
                        downloaded += len(chunk)
                    
                    temp_file.flush()
                
                # Analyze with moviepy
                try:
                    with VideoFileClip(temp_path) as video:
                        duration = video.duration
                        logger.info(f"MoviePy extracted duration: {duration} seconds")
                        
                        # Return immediately - don't worry about cleanup on Windows
                        if duration:
                            return int(duration)
                            
                except Exception as video_error:
                    logger.warning(f"VideoFileClip analysis failed: {str(video_error)}")
                
                # Try to cleanup, but don't fail if it doesn't work
                try:
                    os.unlink(temp_path)
                except:
                    pass  # Ignore cleanup failures on Windows
                        
            except Exception as moviepy_error:
                logger.warning(f"MoviePy setup failed: {str(moviepy_error)}")
        
        # If MoviePy didn't work, try CV2 (same pattern)
        try:
            import cv2
            import tempfile
            import requests
            
            response = requests.get(cloudinary_url, stream=True, timeout=30)
            response.raise_for_status()
            
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_path = temp_file.name
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if downloaded >= 5 * 1024 * 1024:  # 5MB limit
                        break
                    temp_file.write(chunk)
                    downloaded += len(chunk)
                
                temp_file.flush()
            
            cap = cv2.VideoCapture(temp_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            
            # Try cleanup but ignore errors
            try:
                os.unlink(temp_path)
            except:
                pass
            
            if fps > 0 and frame_count > 0:
                duration = int(frame_count / fps)
                logger.info(f"CV2 extracted duration: {duration} seconds")
                return duration
                
        except Exception as cv2_error:
            logger.warning(f"CV2 analysis failed: {str(cv2_error)}")
        
        return None
        
    except Exception as e:
        logger.error(f"Cloudinary duration extraction failed: {str(e)}")
        return None


def extract_direct_video_duration(video_url):
    """Extract duration from direct video URL by downloading headers"""
    try:
        # Try to get content info without downloading full video
        response = requests.head(video_url, timeout=10, allow_redirects=True)
        
        if response.status_code == 200:
            # Check if server supports range requests
            if 'Accept-Ranges' in response.headers and 'bytes' in response.headers['Accept-Ranges']:
                # Download first few MB to analyze with ffmpeg/moviepy
                with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_file:
                    # Download first 5MB
                    headers = {'Range': 'bytes=0-5242880'}  # 5MB
                    partial_response = requests.get(video_url, headers=headers, timeout=30)
                    
                    if partial_response.status_code == 206:  # Partial content
                        temp_file.write(partial_response.content)
                        temp_file.flush()
                        
                        try:
                            # Try with moviepy first if available
                            if MOVIEPY_AVAILABLE:
                                with VideoFileClip(temp_file.name) as video:
                                    duration = video.duration
                                
                                os.unlink(temp_file.name)
                                return int(duration) if duration else None
                        
                        except Exception:
                            pass
                        
                        # Fallback to cv2
                        try:
                            cap = cv2.VideoCapture(temp_file.name)
                            fps = cap.get(cv2.CAP_PROP_FPS)
                            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                            cap.release()
                            
                            os.unlink(temp_file.name)
                            
                            if fps > 0 and frame_count > 0:
                                return int(frame_count / fps)
                        
                        except Exception:
                            pass
                        
                        os.unlink(temp_file.name)
        
        return None
    
    except Exception as e:
        logger.error(f"Error extracting direct video duration: {str(e)}")
        return None


def extract_local_video_duration(file_path):
    """Extract duration from local video file"""
    try:
        # Try with moviepy first if available
        if MOVIEPY_AVAILABLE:
            try:
                with VideoFileClip(file_path) as video:
                    return int(video.duration) if video.duration else None
            except Exception:
                pass
        
        # Fallback to cv2
        try:
            cap = cv2.VideoCapture(file_path)
            fps = cap.get(cv2.CAP_PROP_FPS)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            
            if fps > 0 and frame_count > 0:
                return int(frame_count / fps)
        
        except Exception:
            pass
        
        return None
    
    except Exception as e:
        logger.error(f"Error extracting local video duration: {str(e)}")
        return None


def generate_video_thumbnail(video_url_or_path, lesson_id=None):
    """
    Generate thumbnail for video
    Returns Cloudinary URL of the generated thumbnail
    """
    try:
        # Handle different video sources
        if 'youtube.com' in video_url_or_path or 'youtu.be' in video_url_or_path:
            return generate_youtube_thumbnail(video_url_or_path, lesson_id)
        elif 'vimeo.com' in video_url_or_path:
            return generate_vimeo_thumbnail(video_url_or_path, lesson_id)
        elif 'cloudinary.com' in video_url_or_path:
            return generate_cloudinary_thumbnail(video_url_or_path, lesson_id)
        else:
            return generate_direct_video_thumbnail(video_url_or_path, lesson_id)
    
    except Exception as e:
        logger.error(f"Error generating video thumbnail: {str(e)}")
        return None


def generate_youtube_thumbnail(youtube_url, lesson_id=None):
    """Generate thumbnail for YouTube video"""
    try:
        # Extract video ID
        video_id = None
        if 'youtube.com' in youtube_url:
            parsed_url = urlparse(youtube_url)
            video_id = parse_qs(parsed_url.query).get('v', [None])[0]
        elif 'youtu.be' in youtube_url:
            video_id = youtube_url.split('/')[-1].split('?')[0]
        
        if not video_id:
            return None
        
        # Try different thumbnail qualities (highest first)
        thumbnail_urls = [
            f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
            f"https://img.youtube.com/vi/{video_id}/default.jpg"
        ]
        
        for thumb_url in thumbnail_urls:
            try:
                response = requests.head(thumb_url, timeout=5)
                if response.status_code == 200:
                    # Upload to Cloudinary
                    folder_path = f"courses/lessons/thumbnails/{lesson_id}" if lesson_id else "courses/lessons/thumbnails"
                    
                    upload_result = upload(
                        thumb_url,
                        folder=folder_path,
                        public_id=f"youtube_thumb_{video_id}_{lesson_id}" if lesson_id else f"youtube_thumb_{video_id}",
                        overwrite=True,
                        tags=['lesson_thumbnail', 'youtube_thumbnail']
                    )
                    
                    return upload_result['secure_url']
            
            except Exception:
                continue
        
        return None
    
    except Exception as e:
        logger.error(f"Error generating YouTube thumbnail: {str(e)}")
        return None


def generate_vimeo_thumbnail(vimeo_url, lesson_id=None):
    """Generate thumbnail for Vimeo video"""
    try:
        # Extract video ID
        video_id = None
        patterns = [
            r'vimeo\.com/(\d+)',
            r'vimeo\.com/video/(\d+)',
            r'player\.vimeo\.com/video/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, vimeo_url)
            if match:
                video_id = match.group(1)
                break
        
        if not video_id:
            return None
        
        # Use Vimeo oEmbed API to get thumbnail
        oembed_url = f"https://vimeo.com/api/oembed.json?url=https://vimeo.com/{video_id}"
        
        response = requests.get(oembed_url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            thumbnail_url = data.get('thumbnail_url')
            
            if thumbnail_url:
                # Upload to Cloudinary
                folder_path = f"courses/lessons/thumbnails/{lesson_id}" if lesson_id else "courses/lessons/thumbnails"
                
                upload_result = upload(
                    thumbnail_url,
                    folder=folder_path,
                    public_id=f"vimeo_thumb_{video_id}_{lesson_id}" if lesson_id else f"vimeo_thumb_{video_id}",
                    overwrite=True,
                    tags=['lesson_thumbnail', 'vimeo_thumbnail']
                )
                
                return upload_result['secure_url']
        
        return None
    
    except Exception as e:
        logger.error(f"Error generating Vimeo thumbnail: {str(e)}")
        return None


def generate_cloudinary_thumbnail(cloudinary_url, lesson_id=None):
    """Generate thumbnail for Cloudinary video"""
    try:
        # Extract public_id from Cloudinary URL
        url_parts = cloudinary_url.split('/')
        
        public_id = None
        for i, part in enumerate(url_parts):
            if part == 'upload' and i + 2 < len(url_parts):
                next_part = url_parts[i + 1]
                if re.match(r'^v\d+', next_part):
                    public_id = '/'.join(url_parts[i + 2:])
                else:
                    public_id = '/'.join(url_parts[i + 1:])
                break
        
        if public_id:
            # Remove file extension
            public_id = public_id.rsplit('.', 1)[0]
            
            # Generate thumbnail URL using Cloudinary transformations
            thumbnail_url, _ = build_cloudinary_url(
                public_id,
                resource_type="video",
                format="jpg",
                transformation=[
                    {'width': 1280, 'height': 720, 'crop': 'fill'},
                    {'quality': 'auto:good'},
                    {'start_offset': '10%'}  # Take frame at 10% of video
                ]
            )
            
            # Upload as separate thumbnail
            folder_path = f"courses/lessons/thumbnails/{lesson_id}" if lesson_id else "courses/lessons/thumbnails"
            
            upload_result = upload(
                thumbnail_url,
                folder=folder_path,
                public_id=f"cloudinary_thumb_{lesson_id}" if lesson_id else f"cloudinary_thumb_{public_id.replace('/', '_')}",
                overwrite=True,
                tags=['lesson_thumbnail', 'cloudinary_thumbnail']
            )
            
            return upload_result['secure_url']
        
        return None
    
    except Exception as e:
        logger.error(f"Error generating Cloudinary thumbnail: {str(e)}")
        return None
    

def generate_cloudinary_thumbnail_from_public_id(public_id, lesson_id=None):
    """Generate thumbnail for Cloudinary video using public_id directly"""
    try:
        logger.info(f"Generating thumbnail for public_id: {public_id}")
        
        # Generate thumbnail URL using Cloudinary transformations
        thumbnail_url, _ = build_cloudinary_url(
            public_id,
            resource_type="video",
            format="jpg",
            transformation=[
                {'width': 1280, 'height': 720, 'crop': 'fill'},
                {'quality': 'auto:good'},
                {'start_offset': '10%'}  # Take frame at 10% of video
            ]
        )
        
        logger.info(f"Generated thumbnail URL: {thumbnail_url}")
        
        # Upload as separate thumbnail
        folder_path = f"courses/lessons/thumbnails/{lesson_id}" if lesson_id else "courses/lessons/thumbnails"
        
        upload_result = upload(
            thumbnail_url,
            folder=folder_path,
            public_id=f"cloudinary_thumb_{lesson_id}" if lesson_id else f"cloudinary_thumb_{public_id.replace('/', '_')}",
            overwrite=True,
            tags=['lesson_thumbnail', 'cloudinary_thumbnail']
        )
        
        logger.info(f"Uploaded thumbnail: {upload_result['secure_url']}")
        return upload_result['secure_url']
    
    except Exception as e:
        logger.error(f"Error generating Cloudinary thumbnail from public_id '{public_id}': {str(e)}")
        return None


def generate_direct_video_thumbnail(video_url, lesson_id=None):
    """Generate thumbnail for direct video URL"""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_video:
            # Download first 10MB of video
            headers = {'Range': 'bytes=0-10485760'}  # 10MB
            response = requests.get(video_url, headers=headers, timeout=30)
            
            if response.status_code in [200, 206]:
                temp_video.write(response.content)
                temp_video.flush()
                
                # Generate thumbnail at 10% of video
                if MOVIEPY_AVAILABLE:
                    try:
                        with VideoFileClip(temp_video.name) as video:
                            duration = video.duration
                            if duration and duration > 1:
                                # Take frame at 10% of video duration
                                frame_time = min(duration * 0.1, duration - 1)
                                
                                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_thumb:
                                    # Extract frame
                                    frame = video.get_frame(frame_time)
                                    
                                    # Save frame as image
                                    try:
                                        import matplotlib.pyplot as plt
                                        plt.imsave(temp_thumb.name, frame)
                                    except ImportError:
                                        # Fallback to PIL if matplotlib not available
                                        from PIL import Image
                                        img = Image.fromarray((frame * 255).astype('uint8'))
                                        img.save(temp_thumb.name)
                                    
                                    # Upload to Cloudinary
                                    folder_path = f"courses/lessons/thumbnails/{lesson_id}" if lesson_id else "courses/lessons/thumbnails"
                                    
                                    upload_result = upload(
                                        temp_thumb.name,
                                        folder=folder_path,
                                        public_id=f"direct_thumb_{lesson_id}" if lesson_id else "direct_thumb",
                                        overwrite=True,
                                        tags=['lesson_thumbnail', 'direct_thumbnail']
                                    )
                                    
                                    # Cleanup
                                    os.unlink(temp_thumb.name)
                                    os.unlink(temp_video.name)
                                    
                                    return upload_result['secure_url']
                    except Exception as e:
                        logger.error(f"Error processing video frame with MoviePy: {str(e)}")
                
                # Fallback to cv2
                try:
                    cap = cv2.VideoCapture(temp_video.name)
                    
                    # Get video properties
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    
                    if fps > 0 and frame_count > 0:
                        # Jump to 10% of video
                        target_frame = int(frame_count * 0.1)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                        
                        ret, frame = cap.read()
                        if ret:
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_thumb:
                                cv2.imwrite(temp_thumb.name, frame)
                                
                                # Upload to Cloudinary
                                folder_path = f"courses/lessons/thumbnails/{lesson_id}" if lesson_id else "courses/lessons/thumbnails"
                                
                                upload_result = upload(
                                    temp_thumb.name,
                                    folder=folder_path,
                                    public_id=f"direct_thumb_{lesson_id}" if lesson_id else "direct_thumb",
                                    overwrite=True,
                                    tags=['lesson_thumbnail', 'direct_thumbnail']
                                )
                                
                                # Cleanup
                                os.unlink(temp_thumb.name)
                                cap.release()
                                os.unlink(temp_video.name)
                                
                                return upload_result['secure_url']
                    
                    cap.release()
                
                except Exception as cv_error:
                    logger.error(f"CV2 fallback failed: {str(cv_error)}")
                
                # Cleanup on failure
                os.unlink(temp_video.name)
        
        return None
    
    except Exception as e:
        logger.error(f"Error generating direct video thumbnail: {str(e)}")
        return None


def format_duration(seconds):
    """Format duration from seconds to readable format"""
    if not seconds:
        return "0:00"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def validate_video_url(url):
    """Validate if URL is a supported video platform"""
    supported_domains = [
        'youtube.com', 'youtu.be', 'vimeo.com', 'cloudinary.com',
        'wistia.com', 'brightcove.com', 'jwplayer.com'
    ]
    
    try:
        parsed_url = urlparse(url)
        domain = parsed_url.netloc.lower()
        
        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]
        
        return any(supported in domain for supported in supported_domains)
    
    except Exception:
        return False


def get_video_platform(url):
    """Detect video platform from URL"""
    url_lower = url.lower()
    
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return 'youtube'
    elif 'vimeo.com' in url_lower:
        return 'vimeo'
    elif 'cloudinary.com' in url_lower:
        return 'cloudinary'
    elif 'wistia.com' in url_lower:
        return 'wistia'
    elif 'brightcove.com' in url_lower:
        return 'brightcove'
    elif 'jwplayer.com' in url_lower:
        return 'jwplayer'
    else:
        return 'direct'


def generate_video_embed_code(video_url, width=800, height=450):
    """Generate HTML embed code for video"""
    platform = get_video_platform(video_url)
    
    try:
        if platform == 'youtube':
            video_id = None
            if 'youtube.com' in video_url:
                parsed_url = urlparse(video_url)
                video_id = parse_qs(parsed_url.query).get('v', [None])[0]
            elif 'youtu.be' in video_url:
                video_id = video_url.split('/')[-1].split('?')[0]
            
            if video_id:
                return f'''
                <iframe width="{width}" height="{height}" 
                        src="https://www.youtube.com/embed/{video_id}" 
                        frameborder="0" allowfullscreen>
                </iframe>
                '''
        
        elif platform == 'vimeo':
            video_id = None
            patterns = [
                r'vimeo\.com/(\d+)',
                r'vimeo\.com/video/(\d+)',
                r'player\.vimeo\.com/video/(\d+)'
            ]
            
            for pattern in patterns:
                match = re.search(pattern, video_url)
                if match:
                    video_id = match.group(1)
                    break
            
            if video_id:
                return f'''
                <iframe src="https://player.vimeo.com/video/{video_id}" 
                        width="{width}" height="{height}" 
                        frameborder="0" allowfullscreen>
                </iframe>
                '''
        
        else:
            # Direct video URL
            return f'''
            <video width="{width}" height="{height}" controls>
                <source src="{video_url}" type="video/mp4">
                Your browser does not support the video tag.
            </video>
            '''
    
    except Exception as e:
        logger.error(f"Error generating embed code: {str(e)}")
        return f'<p>Unable to embed video: {video_url}</p>'


def cleanup_old_video_files(public_ids):
    """Clean up old video files from Cloudinary"""
    try:
        if not public_ids:
            return
        
        # Delete videos
        for public_id in public_ids:
            try:
                api.delete_resources([public_id], resource_type="video")
                logger.info(f"Deleted video: {public_id}")
            except Exception as e:
                logger.error(f"Failed to delete video {public_id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error cleaning up video files: {str(e)}")


def cleanup_old_thumbnails(public_ids):
    """Clean up old thumbnail files from Cloudinary"""
    try:
        if not public_ids:
            return
        
        # Delete images
        for public_id in public_ids:
            try:
                api.delete_resources([public_id], resource_type="image")
                logger.info(f"Deleted thumbnail: {public_id}")
            except Exception as e:
                logger.error(f"Failed to delete thumbnail {public_id}: {str(e)}")
    
    except Exception as e:
        logger.error(f"Error cleaning up thumbnails: {str(e)}")


def batch_process_video_metadata(lesson_ids):
    """Batch process video metadata for multiple lessons"""
    from courses.models import CourseLesson
    
    try:
        lessons = CourseLesson.objects.filter(
            id__in=lesson_ids,
            lesson_type='video',
            duration_seconds__isnull=True
        )
        
        results = []
        
        for lesson in lessons:
            try:
                video_url = lesson.get_video_url()
                if video_url:
                    # Extract duration
                    duration = extract_video_duration(video_url)
                    if duration:
                        lesson.duration_seconds = duration
                        lesson.save(update_fields=['duration_seconds'])
                    
                    # Generate thumbnail if missing
                    if not lesson.thumbnail:
                        thumbnail_url = generate_video_thumbnail(video_url, str(lesson.id))
                        if thumbnail_url:
                            lesson.thumbnail = thumbnail_url
                            lesson.save(update_fields=['thumbnail'])
                    
                    results.append({
                        'lesson_id': str(lesson.id),
                        'lesson_title': lesson.title,
                        'duration_extracted': duration is not None,
                        'duration_seconds': duration,
                        'thumbnail_generated': thumbnail_url is not None if 'thumbnail_url' in locals() else False
                    })
                    
                    logger.info(f"Processed video metadata for lesson: {lesson.title}")
            
            except Exception as e:
                logger.error(f"Error processing lesson {lesson.id}: {str(e)}")
                results.append({
                    'lesson_id': str(lesson.id),
                    'lesson_title': lesson.title,
                    'error': str(e)
                })
        
        return results
    
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        return []