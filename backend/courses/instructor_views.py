# courses/instructor_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum, F
from django.core.paginator import Paginator
from django.conf import settings
from django.db import models
from cloudinary.uploader import upload, destroy
from cloudinary.utils import cloudinary_url
from cloudinary import api
from .models import Course, UserCourseProgress, CourseEnrollment, CourseCategory, CourseReview, CourseAppeal, CourseExam, ExamQuestion, ExamAnswer, UserExamAttempt, UserExamAnswer, ExamCertificate, CourseSection, CourseLesson, UserLessonProgress
from .serializers import (
    CourseSerializer, CourseCreateUpdateSerializer, UserCourseProgressSerializer,
    CourseEnrollmentSerializer, CourseStatsSerializer, CourseCategorySerializer,
    VideoUploadSerializer, CourseExamCreateSerializer, CourseExamSerializer, ExamQuestionSerializer, ExamQuestionCreateSerializer, ExamAnswerSerializer, UserExamAttemptSerializer, ExamStatsSerializer, CourseSectionSerializer, CourseSectionCreateSerializer,
    CourseLessonSerializer, CourseLessonCreateSerializer,
    UserLessonProgressSerializer, UserLessonProgressUpdateSerializer
)
from common.permissions import IsAuthenticated, IsAdmin
from users.models import User
from utils.auth import EmailService
from django.utils.text import slugify
import logging
import json
from datetime import datetime, timedelta
from utils.thumbnail_helper import generate_video_thumbnail_from_upload, generate_video_url_thumbnail, cleanup_old_thumbnail
from utils.admin_email_service import AdminEmailService
from utils.video_processing import extract_video_duration, generate_video_thumbnail, generate_cloudinary_thumbnail_from_public_id


logger = logging.getLogger(__name__)


# Create your views here.
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def upload_video(request):
    """
    Admin: Upload video file to Cloudinary with organized folders
    POST /api/admin/videos/upload/
    """
    
    serializer = VideoUploadSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid file data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        video_file = serializer.validated_data['video_file']
        
        # Create organized folder structure
        current_date = timezone.now()
        folder_path = f"courses/videos/{current_date.year}/{current_date.month:02d}"
        
        # Upload to Cloudinary with organized structure
        upload_result = upload(
            video_file,
            resource_type="video",
            folder=folder_path,  # ← ORGANIZED BY YEAR/MONTH
            public_id=f"course_video_{current_date.strftime('%Y%m%d_%H%M%S')}_{request.user.id}",
            overwrite=True,
            transformation=[
                {'quality': 'auto:good'},
                {'format': 'mp4'}
            ],
            tags=[
                'course_video',
                f'uploaded_by_{request.user.id}',
                f'year_{current_date.year}',
                f'month_{current_date.month}'
            ]
        )
        
        # Get optimized video URL
        video_url, _ = cloudinary_url(
            upload_result['public_id'],
            resource_type="video",
            format="mp4",
            quality="auto:good"
        )
        
        video_info = {
            'public_id': upload_result['public_id'],
            'url': video_url,
            'secure_url': upload_result['secure_url'],
            'folder': folder_path,
            'duration': upload_result.get('duration'),
            'format': upload_result.get('format'),
            'size': upload_result.get('bytes')
        }
        
        logger.info(f"Video uploaded to {folder_path} by admin {request.user.email}: {upload_result['public_id']}")
        
        return Response({
            'message': 'Video uploaded successfully.',
            'video_info': video_info
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Video upload error: {str(e)}")
        return Response(
            {'detail': f'Video upload failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def create_course(request):
    """
    Admin: Create New Course with Video Upload Support and Auto Thumbnail
    POST /api/admin/courses/
    """

    serializer = CourseCreateUpdateSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            # Set course as inactive by default (requires super admin approval)
            course = serializer.save(is_active=False, moderation_status='pending')
            
            # Handle video upload and thumbnail generation
            video_info = None
            if course.video_source == 'upload' and course.video_file:
                try:
                    video_public_id = getattr(course.video_file, 'public_id', None)
                    # Handle video info safely
                    video_info = {
                        'public_id': video_public_id
                    }
                    
                    # Safely get video URL
                    try:
                        if hasattr(course.video_file, 'url'):
                            video_info['url'] = course.video_file.url
                        else:
                            video_info['url'] = str(course.video_file)
                    except (AttributeError, ValueError):
                        video_info['url'] = None

                    from cloudinary.api import resource

                    if video_public_id:
                        try:
                            cloudinary_resource = resource(video_public_id, resource_type="video")
                            video_info.update({
                                'duration': int(cloudinary_resource.get('duration', 0)),
                                'size': cloudinary_resource.get('bytes', 0),
                                'format': cloudinary_resource.get('format', '').lower(),
                            })
                        except Exception as meta_error:
                            logger.warning(f"Could not fetch Cloudinary video metadata: {str(meta_error)}")

                    
                    # AUTO-GENERATE THUMBNAIL if not provided
                    if not course.thumbnail and video_public_id:
                        try:
                            thumbnail_url = generate_video_thumbnail_from_upload(video_public_id, course.id)
                            
                            if thumbnail_url:
                                course.thumbnail = thumbnail_url
                                course.save(update_fields=['thumbnail'])
                                
                                video_info['thumbnail_generated'] = True
                                video_info['thumbnail_url'] = thumbnail_url
                                
                                logger.info(f"Auto-generated thumbnail for course: {course.title}")
                            else:
                                video_info['thumbnail_generated'] = False
                                logger.warning(f"Failed to generate thumbnail for course: {course.title}")
                            
                        except Exception as thumb_error:
                            logger.error(f"Thumbnail generation failed: {str(thumb_error)}")
                            video_info['thumbnail_generated'] = False
                    
                    # Send success notification
                    AdminEmailService.notify_video_upload_success(course, request.user, video_info)
                    
                except Exception as video_error:
                    logger.error(f"Video processing error: {str(video_error)}")
                    AdminEmailService.notify_video_upload_failure(course.title, request.user, str(video_error))

            # URL-based thumbnail generation for video URLs
            elif course.video_source == 'url' and course.video_url and not course.thumbnail:
                try:
                    thumbnail_url = generate_video_url_thumbnail(course.video_url)
                    if thumbnail_url:
                        course.thumbnail = thumbnail_url
                        course.save(update_fields=['thumbnail'])
                        logger.info(f"Generated thumbnail from URL for course: {course.title}")
                except Exception as e:
                    logger.error(f"URL thumbnail generation failed: {str(e)}")
            
            # Log course creation
            logger.info(f"Course created: {course.title} by admin {request.user.email}")
            
            # Send confirmation to course creator
            AdminEmailService.notify_course_creator_confirmation(course, request.user)
            
            # Send notification to super admins for approval
            AdminEmailService.notify_super_admins_new_course(course, request.user)
            
            # Return full course data
            response_serializer = CourseSerializer(course)
            response_data = response_serializer.data
            
            if video_info:
                response_data['video_info'] = video_info
            
            return Response(response_data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Course creation error: {str(e)}")
        return Response(
            {'detail': 'Course creation failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def list_all_courses(request):
    """
    Admin: List All Courses with Enhanced Filtering
    GET /api/admin/courses/
    """
    try:
        # Get query parameters
        search = request.GET.get('search', '')
        category = request.GET.get('category', '')
        course_type = request.GET.get('course_type', '')
        is_active = request.GET.get('is_active', '')
        is_featured = request.GET.get('is_featured', '')
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        sort_by = request.GET.get('sort_by', '-created_at')
        
        # Build queryset
        queryset = Course.objects.select_related(
            'created_by', 'updated_by'
        ).prefetch_related(
            'user_progress', 'enrollments__user', 'reviews'
        ).annotate(
            enrollment_count=Count('user_progress'),
            review_count=Count('reviews', filter=Q(reviews__is_approved=True)),
            avg_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True))
        )
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search)
            )
        
        if category:
            queryset = queryset.filter(category=category)
        
        if course_type:
            queryset = queryset.filter(course_type=course_type)
        
        if is_active:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        if is_featured:
            queryset = queryset.filter(is_featured=is_featured.lower() == 'true')
        
        # Apply sorting
        valid_sort_fields = ['title', 'created_at', 'updated_at', 'category', 'difficulty_level', 'price', 'course_type']
        if sort_by.lstrip('-') in valid_sort_fields:
            queryset = queryset.order_by(sort_by)
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = CourseSerializer(page_obj.object_list, many=True)
        
        return Response({
            'courses': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_courses': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'filters': {
                'categories': list(Course.objects.values_list('category', flat=True).distinct()),
                'course_types': [choice[0] for choice in Course.COURSE_TYPES],
                'difficulty_levels': [choice[0] for choice in Course._meta.get_field('difficulty_level').choices]
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"List courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def get_course_details(request, course_id):
    """
    Admin: Get Course Details with Analytics
    GET /api/admin/courses/{course_id}/
    """
    try:
        course = Course.objects.select_related('created_by', 'updated_by').prefetch_related(
            'user_progress', 'enrollments', 'reviews'
        ).get(id=course_id)
        
        serializer = CourseSerializer(course)
        
        # Add additional admin-specific data
        data = serializer.data
        
        # Enrollment analytics
        total_enrollments = course.user_progress.count()
        completed_enrollments = course.user_progress.filter(progress_percentage=100).count()
        in_progress_enrollments = course.user_progress.filter(
            progress_percentage__gt=0, progress_percentage__lt=100
        ).count()
        not_started_enrollments = course.user_progress.filter(progress_percentage=0).count()
        
        # Revenue analytics
        total_revenue = course.enrollments.filter(
            payment_status='completed'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Recent activity (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_enrollments = course.user_progress.filter(started_at__gte=thirty_days_ago).count()
        
        # Reviews summary
        reviews = course.reviews.filter(is_approved=True)
        avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
        
        data.update({
            'enrollment_stats': {
                'total_enrollments': total_enrollments,
                'completed_enrollments': completed_enrollments,
                'in_progress_enrollments': in_progress_enrollments,
                'not_started_enrollments': not_started_enrollments,
                'completion_rate': round((completed_enrollments / total_enrollments * 100), 2) if total_enrollments > 0 else 0
            },
            'revenue_stats': {
                'total_revenue': float(total_revenue),
                'average_revenue_per_enrollment': float(total_revenue / total_enrollments) if total_enrollments > 0 else 0
            },
            'recent_activity': {
                'recent_enrollments': recent_enrollments
            },
            'review_stats': {
                'average_rating': round(avg_rating, 1),
                'total_reviews': reviews.count(),
                'rating_distribution': {
                    '5': reviews.filter(rating=5).count(),
                    '4': reviews.filter(rating=4).count(),
                    '3': reviews.filter(rating=3).count(),
                    '2': reviews.filter(rating=2).count(),
                    '1': reviews.filter(rating=1).count(),
                }
            }
        })
        
        return Response(data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get course details error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course details.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def update_course(request, course_id):
    """
    Admin: Update Course with Change Tracking and Cloudinary Cleanup
    PUT/PATCH /api/admin/courses/{course_id}/update/
    """
    try:
        course = Course.objects.get(id=course_id)
        original_data = CourseSerializer(course).data
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    partial = request.method == 'PATCH'
    serializer = CourseCreateUpdateSerializer(
        course, 
        data=request.data, 
        partial=partial,
        context={'request': request}
    )
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            # Store old thumbnail for cleanup
            old_thumbnail = course.thumbnail
            
            # Save the updated course
            updated_course = serializer.save()
            
            # Track changes for notification
            updated_data = CourseSerializer(updated_course).data
            changes = []
            
            for key, new_value in updated_data.items():
                if key in original_data and original_data[key] != new_value:
                    changes.append({
                        'field': key,
                        'old_value': original_data[key],
                        'new_value': new_value
                    })
            
            # Handle video file changes with thumbnail generation
            video_info = None
            if updated_course.video_source == 'upload' and updated_course.video_file:
                try:
                    video_public_id = getattr(updated_course.video_file, 'public_id', None)
                    video_info = {
                        'url': updated_course.video_file.url,
                        'public_id': video_public_id
                    }

                    from cloudinary.api import resource

                    if video_public_id:
                        try:
                            cloudinary_resource = resource(video_public_id, resource_type="video")
                            video_info.update({
                                'duration': int(cloudinary_resource.get('duration', 0)),
                                'size': cloudinary_resource.get('bytes', 0),
                                'format': cloudinary_resource.get('format', '').lower(),
                            })
                        except Exception as meta_error:
                            logger.warning(f"Could not fetch Cloudinary video metadata: {str(meta_error)}")

                    # Check if video was actually changed
                    if 'video_file' in request.FILES:
                        # Generate new thumbnail for new video
                        if video_public_id:
                            # Clean up old thumbnail
                            if old_thumbnail:
                                cleanup_old_thumbnail(old_thumbnail)
                            
                            # Generate new thumbnail
                            thumbnail_url = generate_video_thumbnail_from_upload(video_public_id, updated_course.id)
                            
                            if thumbnail_url:
                                updated_course.thumbnail = thumbnail_url
                                updated_course.save(update_fields=['thumbnail'])
                                
                                video_info['thumbnail_generated'] = True
                                video_info['thumbnail_url'] = thumbnail_url
                                
                                logger.info(f"Auto-generated new thumbnail for updated course: {updated_course.title}")
                            else:
                                video_info['thumbnail_generated'] = False

                        # Send success notification
                        AdminEmailService.notify_video_upload_success(updated_course, request.user, video_info)
                        
                except Exception as video_error:
                    logger.error(f"Video processing error during update: {str(video_error)}")
                    AdminEmailService.notify_video_upload_failure(updated_course.title, request.user, str(video_error))

            # Handle video URL changes with thumbnail generation
            elif updated_course.video_source == 'url' and updated_course.video_url:
                if 'video_url' in request.data and request.data['video_url'] != original_data.get('video_url'):
                    try:
                        # Generate thumbnail for new URL if no manual thumbnail provided
                        if not updated_course.thumbnail or not request.FILES.get('thumbnail'):
                            # Clean up old thumbnail
                            if old_thumbnail:
                                cleanup_old_thumbnail(old_thumbnail)
                            
                            thumbnail_url = generate_video_url_thumbnail(updated_course.video_url)
                            if thumbnail_url:
                                updated_course.thumbnail = thumbnail_url
                                updated_course.save(update_fields=['thumbnail'])
                                logger.info(f"Generated thumbnail from new URL for course: {updated_course.title}")
                    except Exception as url_thumb_error:
                        logger.error(f"URL thumbnail generation failed: {str(url_thumb_error)}")
            
            # Handle manual thumbnail changes
            elif 'thumbnail' in request.FILES and old_thumbnail:
                cleanup_old_thumbnail(old_thumbnail)
            
            # Log course update
            logger.info(f"Course updated: {updated_course.title} by admin {request.user.email}")
            
            # Send notification to instructor (owner)
            if changes:
                AdminEmailService.notify_course_updated(updated_course, request.user, changes)
            
            # Return updated course data
            response_serializer = CourseSerializer(updated_course)
            response_data = response_serializer.data
            
            if video_info:
                response_data['video_info'] = video_info
            
            return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Course update error: {str(e)}")
        return Response(
            {'detail': 'Course update failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAdmin])
def delete_course(request, course_id):
    """
    Admin: Delete Course with Video Cleanup
    DELETE /api/admin/courses/{course_id}/
    """
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        with transaction.atomic():
            course_title = course.title
            video_public_id = None
            
            # Get video public_id for cleanup
            if course.video_source == 'upload' and course.video_file:
                video_public_id = course.video_file.public_id
            
            # Check if course has active enrollments
            active_enrollments = course.user_progress.filter(progress_percentage__gt=0).count()
            paid_enrollments = course.enrollments.filter(payment_status='completed').count()
            
            if active_enrollments > 0 or paid_enrollments > 0:
                # Soft delete by deactivating
                course.is_active = False
                course.updated_by = request.user
                course.save(update_fields=['is_active', 'updated_by'])
                
                logger.info(f"Course deactivated: {course_title} by admin {request.user.email} (had {active_enrollments} active enrollments, {paid_enrollments} paid enrollments)")
                
                return Response({
                    'message': f'Course "{course_title}" has been deactivated instead of deleted due to active enrollments or payments.',
                    'action': 'deactivated',
                    'stats': {
                        'active_enrollments': active_enrollments,
                        'paid_enrollments': paid_enrollments
                    }
                }, status=status.HTTP_200_OK)
            else:
                # Safe to hard delete
                course.delete()
                
                # Clean up video from Cloudinary
                if video_public_id:
                    try:
                        destroy(video_public_id, resource_type="video")
                        logger.info(f"Video deleted from Cloudinary: {video_public_id}")
                    except Exception as video_error:
                        logger.error(f"Failed to delete video from Cloudinary: {str(video_error)}")
                
                # Clean up thumbnail from Cloudinary
                if course.thumbnail:
                    try:
                        # Extract public_id from thumbnail URL
                        thumbnail_public_id = None
                        
                        if hasattr(course.thumbnail, 'public_id'):
                            thumbnail_public_id = course.thumbnail.public_id
                        elif course.thumbnail.url:
                            # Extract from URL if needed
                            import re
                            url_match = re.search(r'/([^/]+)\.(jpg|jpeg|png|gif|webp)$', course.thumbnail.url)
                            if url_match:
                                thumbnail_public_id = f"courses/thumbnails/{url_match.group(1)}"
                        
                        if thumbnail_public_id:
                            destroy(thumbnail_public_id, resource_type="image")
                            logger.info(f"Thumbnail deleted from Cloudinary: {thumbnail_public_id}")
                            
                    except Exception as thumb_error:
                        logger.error(f"Failed to delete thumbnail from Cloudinary: {str(thumb_error)}")
                
                # Clean up any auto-generated thumbnails for this course
                try:
                    # Delete by tag (more reliable for auto-generated thumbnails)
                    api.delete_resources_by_tag(f"course_id_{course.id}")
                    logger.info(f"Auto-generated thumbnails deleted for course: {course.id}")
                except Exception as tag_error:
                    logger.error(f"Failed to delete tagged resources: {str(tag_error)}")
                
                logger.info(f"Course deleted: {course_title} by admin {request.user.email}")
                
                return Response(
                    {
                        'message': f'Course "{course_title}" has been permanently deleted.',
                        'action': 'deleted'
                    },
                    status=status.HTTP_200_OK
                )

    
    except Exception as e:
        logger.error(f"Course deletion error: {str(e)}")
        return Response(
            {'detail': 'Course deletion failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def course_statistics(request):
    """
    Admin: Get Enhanced Course Statistics
    GET /api/admin/courses/statistics/
    """
    try:
        # Basic stats
        total_courses = Course.objects.count()
        active_courses = Course.objects.filter(is_active=True).count()
        free_courses = Course.objects.filter(course_type='free', is_active=True).count()
        paid_courses = Course.objects.filter(course_type__in=['paid', 'premium'], is_active=True).count()
        
        # Enrollment stats
        total_enrollments = UserCourseProgress.objects.count()
        paid_enrollments = CourseEnrollment.objects.filter(payment_status='completed').count()
        completed_courses = UserCourseProgress.objects.filter(progress_percentage=100).count()
        
        # Revenue stats
        total_revenue = CourseEnrollment.objects.filter(
            payment_status='completed'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Average completion rate
        avg_completion = UserCourseProgress.objects.aggregate(
            avg=Avg('progress_percentage')
        )['avg'] or 0
        
        # Courses by category
        courses_by_category = dict(
            Course.objects.filter(is_active=True)
            .values_list('category')
            .annotate(count=Count('id'))
        )
        
        # Recent enrollments (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_enrollments = UserCourseProgress.objects.filter(
            started_at__gte=thirty_days_ago
        ).count()
        
        stats_data = {
            'total_courses': total_courses,
            'active_courses': active_courses,
            'free_courses': free_courses,
            'paid_courses': paid_courses,
            'total_enrollments': total_enrollments,
            'paid_enrollments': paid_enrollments,
            'completed_courses': completed_courses,
            'total_revenue': float(total_revenue),
            'average_completion_rate': round(avg_completion, 2),
            'courses_by_category': courses_by_category,
            'recent_enrollments': recent_enrollments
        }
        
        serializer = CourseStatsSerializer(stats_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Course statistics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course statistics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def course_enrollments(request, course_id):
    """
    Admin: Get Course Enrollments with Payment Info
    GET /api/admin/courses/{course_id}/enrollments/
    """
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        # Get query parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        status_filter = request.GET.get('status', '')  # completed, in_progress, not_started
        payment_filter = request.GET.get('payment_status', '')  # completed, pending, failed
        
        # Build queryset
        queryset = UserCourseProgress.objects.filter(course=course).select_related('user')
        
        # Apply status filter
        if status_filter == 'completed':
            queryset = queryset.filter(progress_percentage=100)
        elif status_filter == 'in_progress':
            queryset = queryset.filter(progress_percentage__gt=0, progress_percentage__lt=100)
        elif status_filter == 'not_started':
            queryset = queryset.filter(progress_percentage=0)
        
        # Apply payment filter if course is paid
        if payment_filter and not course.is_free():
            enrollment_ids = CourseEnrollment.objects.filter(
                course=course,
                payment_status=payment_filter
            ).values_list('user_id', flat=True)
            queryset = queryset.filter(user_id__in=enrollment_ids)
        
        # Order by latest activity
        queryset = queryset.order_by('-last_accessed')
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = UserCourseProgressSerializer(page_obj.object_list, many=True)
        
        # Get enrollment summary
        total_revenue = 0
        if not course.is_free():
            total_revenue = CourseEnrollment.objects.filter(
                course=course,
                payment_status='completed'
            ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        return Response({
            'course': {
                'id': str(course.id),
                'title': course.title,
                'description': course.description,
                'is_free': course.is_free(),
                'price': course.get_effective_price()
            },
            'enrollments': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_enrollments': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'summary': {
                'total': queryset.count(),
                'completed': queryset.filter(progress_percentage=100).count(),
                'in_progress': queryset.filter(progress_percentage__gt=0, progress_percentage__lt=100).count(),
                'not_started': queryset.filter(progress_percentage=0).count(),
                'total_revenue': float(total_revenue)
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Course enrollments error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course enrollments.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['GET'])
@permission_classes([IsAdmin])
def user_course_progress_detail(request, user_id, course_id):
    """
    Admin: Get Specific User's Course Progress with Enhanced Details
    GET /api/admin/users/{user_id}/courses/{course_id}/progress/
    """
    try:
        user = User.objects.get(id=user_id)
        course = Course.objects.get(id=course_id)
        
        try:
            progress = UserCourseProgress.objects.select_related('user', 'course').get(
                user=user, course=course
            )
            
            serializer = UserCourseProgressSerializer(progress)
            data = serializer.data
            
            # Add enrollment information if exists
            try:
                enrollment = CourseEnrollment.objects.get(user=user, course=course)
                enrollment_data = CourseEnrollmentSerializer(enrollment).data
                data['enrollment_info'] = enrollment_data
            except CourseEnrollment.DoesNotExist:
                data['enrollment_info'] = None
            
            # Add progress analytics
            data['analytics'] = {
                'time_spent_minutes': progress.sections_completed and len(progress.sections_completed) * 15 or 0,  # Estimate
                'last_section_completed': progress.sections_completed[-1] if progress.sections_completed else None,
                'completion_streak': 0,  # You can calculate this based on your needs
                'average_session_time': 25  # Estimate - you can track this separately
            }
            
            return Response(data, status=status.HTTP_200_OK)
            
        except UserCourseProgress.DoesNotExist:
            # Check if user has enrollment but no progress yet
            try:
                enrollment = CourseEnrollment.objects.get(user=user, course=course)
                enrollment_data = CourseEnrollmentSerializer(enrollment).data
                
                return Response({
                    'user_id': str(user.id),
                    'user_name': user.full_name,
                    'course_id': str(course.id),
                    'course_title': course.title,
                    'progress_percentage': 0,
                    'started_at': None,
                    'completed_at': None,
                    'enrollment_info': enrollment_data,
                    'message': 'User is enrolled but has not started this course yet.'
                }, status=status.HTTP_200_OK)
                
            except CourseEnrollment.DoesNotExist:
                return Response({
                    'user_id': str(user.id),
                    'user_name': user.full_name,
                    'course_id': str(course.id),
                    'course_title': course.title,
                    'progress_percentage': 0,
                    'started_at': None,
                    'completed_at': None,
                    'enrollment_info': None,
                    'message': 'User is not enrolled in this course.'
                }, status=status.HTTP_200_OK)
    
    except User.DoesNotExist:
        return Response(
            {'detail': 'User not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"User course progress detail error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch user course progress.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdmin])
def bulk_course_actions(request):
    """
    Admin: Enhanced Bulk Actions on Courses
    POST /api/admin/courses/bulk-actions/
    
    Supported actions:
    - activate: Activate selected courses
    - deactivate: Deactivate selected courses
    - delete: Delete courses (with safety checks)
    - feature: Mark courses as featured
    - unfeature: Remove featured status
    - update_category: Update category for selected courses
    - apply_discount: Apply discount to selected courses
    """
    action = request.data.get('action')
    course_ids = request.data.get('course_ids', [])
    
    if not action or not course_ids:
        return Response(
            {'detail': 'Action and course_ids are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    valid_actions = [
        'activate', 'deactivate', 'delete', 'feature', 'unfeature',
        'update_category', 'apply_discount', 'remove_discount'
    ]
    
    if action not in valid_actions:
        return Response(
            {'detail': f'Invalid action. Valid actions: {", ".join(valid_actions)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            courses = Course.objects.filter(id__in=course_ids)
            
            if not courses.exists():
                return Response(
                    {'detail': 'No courses found with provided IDs.'},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            updated_count = 0
            response_data = {'message': '', 'updated_courses': 0}
            
            if action == 'activate':
                updated_count = courses.update(is_active=True, updated_by=request.user)
                response_data['message'] = f'Successfully activated {updated_count} courses.'
                
            elif action == 'deactivate':
                updated_count = courses.update(is_active=False, updated_by=request.user)
                response_data['message'] = f'Successfully deactivated {updated_count} courses.'
                
            elif action == 'feature':
                updated_count = courses.update(is_featured=True, updated_by=request.user)
                response_data['message'] = f'Successfully featured {updated_count} courses.'
                
            elif action == 'unfeature':
                updated_count = courses.update(is_featured=False, updated_by=request.user)
                response_data['message'] = f'Successfully unfeatured {updated_count} courses.'
                
            elif action == 'update_category':
                new_category = request.data.get('category')
                if not new_category:
                    return Response(
                        {'detail': 'Category is required for update_category action.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                updated_count = courses.update(category=new_category, updated_by=request.user)
                response_data['message'] = f'Successfully updated category for {updated_count} courses.'
                
            elif action == 'apply_discount':
                discount_percentage = request.data.get('discount_percentage')
                discount_start_date = request.data.get('discount_start_date')
                discount_end_date = request.data.get('discount_end_date')
                
                if not discount_percentage or discount_percentage <= 0 or discount_percentage > 100:
                    return Response(
                        {'detail': 'Valid discount_percentage (1-100) is required.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                update_data = {
                    'has_discount': True,
                    'discount_percentage': discount_percentage,
                    'updated_by': request.user
                }
                
                if discount_start_date:
                    update_data['discount_start_date'] = discount_start_date
                if discount_end_date:
                    update_data['discount_end_date'] = discount_end_date
                
                updated_count = courses.update(**update_data)
                response_data['message'] = f'Successfully applied {discount_percentage}% discount to {updated_count} courses.'
                
            elif action == 'remove_discount':
                updated_count = courses.update(
                    has_discount=False,
                    discount_percentage=0,
                    discount_start_date=None,
                    discount_end_date=None,
                    updated_by=request.user
                )
                response_data['message'] = f'Successfully removed discount from {updated_count} courses.'
                
            elif action == 'delete':
                # Enhanced deletion with detailed safety checks
                courses_with_enrollments = []
                courses_with_payments = []
                courses_to_delete = []
                courses_deactivated = []
                
                for course in courses:
                    has_progress = course.user_progress.filter(progress_percentage__gt=0).exists()
                    has_payments = course.enrollments.filter(payment_status='completed').exists()
                    
                    if has_progress or has_payments:
                        # Cannot delete - deactivate instead
                        course.is_active = False
                        course.updated_by = request.user
                        course.save(update_fields=['is_active', 'updated_by'])
                        courses_deactivated.append(course.title)
                        
                        if has_progress:
                            courses_with_enrollments.append(course.title)
                        if has_payments:
                            courses_with_payments.append(course.title)
                    else:
                        courses_to_delete.append(course)
                
                # Delete courses that are safe to delete
                deleted_count = 0
                if courses_to_delete:
                    # Clean up associated video files
                    for course in courses_to_delete:
                        if course.video_source == 'upload' and course.video_file:
                            try:
                                destroy(course.video_file.public_id, resource_type="video")
                            except Exception as e:
                                logger.error(f"Failed to delete video for course {course.title}: {str(e)}")
                    
                    Course.objects.filter(id__in=[c.id for c in courses_to_delete]).delete()
                    deleted_count = len(courses_to_delete)
                
                response_data = {
                    'message': 'Bulk deletion completed with safety checks.',
                    'deleted_courses': deleted_count,
                    'deactivated_courses': len(courses_deactivated),
                    'courses_with_enrollments': courses_with_enrollments,
                    'courses_with_payments': courses_with_payments,
                    'deactivated_course_names': courses_deactivated
                }
                
                logger.info(f"Bulk delete: {deleted_count} deleted, {len(courses_deactivated)} deactivated by admin {request.user.email}")
                return Response(response_data, status=status.HTTP_200_OK)
            
            response_data['updated_courses'] = updated_count
            
            # Log bulk action
            logger.info(f"Bulk action '{action}' performed on {updated_count} courses by admin {request.user.email}")
            
            return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Bulk course actions error: {str(e)}")
        return Response(
            {'detail': 'Bulk action failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def course_categories(request):
    """
    Admin: Get Course Categories with Enhanced Data
    GET /api/admin/course-categories/
    """
    try:
        categories = CourseCategory.objects.filter(is_active=True).order_by('order', 'name')
        serializer = CourseCategorySerializer(categories, many=True)
        
        # Add category statistics
        category_stats = {}
        for category in categories:
            courses_count = Course.objects.filter(category=category.slug, is_active=True).count()
            enrolled_count = UserCourseProgress.objects.filter(course__category=category.slug).count()
            
            category_stats[category.slug] = {
                'courses_count': courses_count,
                'enrolled_count': enrolled_count,
                'completion_rate': 0  # You can calculate this if needed
            }
        
        return Response({
            'categories': serializer.data,
            'statistics': category_stats,
            'total_categories': categories.count()
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Course categories error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course categories.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdmin])
def create_category(request):
    """
    Admin: Create Course Category with Auto-slug Generation
    POST /api/admin/course-categories/
    """
    serializer = CourseCategorySerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Auto-generate slug from name
        name = serializer.validated_data['name']

        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        
        # Ensure unique slug
        while CourseCategory.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        serializer.validated_data['slug'] = slug
        
        category = serializer.save()
        logger.info(f"Course category created: {category.name} by admin {request.user.email}")
        
        response_data = CourseCategorySerializer(category).data
        return Response(response_data, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Create category error: {str(e)}")
        return Response(
            {'detail': 'Category creation failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdmin])
def update_category(request, category_id):
    """
    Admin: Update Course Category
    PUT/PATCH /api/admin/course-categories/{category_id}/
    """
    try:
        category = CourseCategory.objects.get(id=category_id)
    except CourseCategory.DoesNotExist:
        return Response(
            {'detail': 'Category not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    partial = request.method == 'PATCH'
    serializer = CourseCategorySerializer(category, data=request.data, partial=partial)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Auto-regenerate slug only if name is being updated
        if 'name' in serializer.validated_data:
            base_slug = slugify(serializer.validated_data['name'])
            slug = base_slug
            counter = 1
            while CourseCategory.objects.filter(slug=slug).exclude(id=category_id).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            serializer.validated_data['slug'] = slug

        updated_category = serializer.save()
        logger.info(f"Course category updated: {updated_category.name} by admin {request.user.email}")
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Update category error: {str(e)}")
        return Response(
            {'detail': 'Category update failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAdmin])
def delete_category(request, category_id):
    """
    Admin: Delete Course Category with Safety Checks
    DELETE /api/admin/course-categories/{category_id}/
    """
    try:
        category = CourseCategory.objects.get(id=category_id)
    except CourseCategory.DoesNotExist:
        return Response(
            {'detail': 'Category not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        # Check if category has associated courses
        courses_count = Course.objects.filter(category=category.slug).count()
        
        if courses_count > 0:
            return Response(
                {
                    'detail': f'Cannot delete category. It has {courses_count} associated courses.',
                    'courses_count': courses_count,
                    'suggestion': 'Please move or delete all courses in this category first.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        category_name = category.name
        category.delete()
        
        logger.info(f"Course category deleted: {category_name} by admin {request.user.email}")
        
        return Response(status=status.HTTP_204_NO_CONTENT)
    
    except Exception as e:
        logger.error(f"Delete category error: {str(e)}")
        return Response(
            {'detail': 'Category deletion failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# COURSE SECTION MANAGEMENT

@api_view(['GET', 'POST'])
@permission_classes([IsAdmin])
def course_sections(request, course_id):
    """
    Admin: List sections or create new section for course
    GET/POST /api/admin/courses/{course_id}/sections/
    """
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # List all sections with lesson counts
        sections = CourseSection.objects.filter(course=course).annotate(
            lessons_count=Count('lessons', filter=Q(lessons__is_active=True)),
            completed_lessons_count=Count('lessons__user_progress', filter=Q(
                lessons__user_progress__is_completed=True,
                lessons__is_active=True
            ))
        ).order_by('order')
        
        serializer = CourseSectionSerializer(sections, many=True)
        
        return Response({
            'course': {
                'id': str(course.id),
                'title': course.title,
                'total_sections': sections.count()
            },
            'sections': serializer.data
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        # Create new section
        serializer = CourseSectionCreateSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                section = serializer.save(course=course, created_by=request.user)
                
                # Update course totals
                course.update_course_totals()
                
                logger.info(f"Section created: {section.title} for course {course.title} by admin {request.user.email}")
                
                return Response(CourseSectionSerializer(section).data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Create section error: {str(e)}")
            return Response(
                {'detail': 'Section creation failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAdmin])
def section_detail(request, course_id, section_id):
    """
    Admin: Get, update, or delete course section
    GET/PUT/DELETE /api/admin/courses/{course_id}/sections/{section_id}/
    """
    try:
        course = Course.objects.get(id=course_id)
        section = CourseSection.objects.get(id=section_id, course=course)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseSection.DoesNotExist:
        return Response({'detail': 'Section not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # Get section with lessons
        section_data = CourseSectionSerializer(section).data
        
        # Add lessons data
        lessons = CourseLesson.objects.filter(section=section).order_by('order')
        section_data['lessons'] = CourseLessonSerializer(lessons, many=True).data
        
        # Add analytics
        total_lessons = lessons.filter(is_active=True).count()
        total_enrollments = UserCourseProgress.objects.filter(course=course).count()
        
        section_data['analytics'] = {
            'total_lessons': total_lessons,
            'total_enrollments': total_enrollments,
            'average_completion_rate': section.get_completion_rate() if hasattr(section, 'get_completion_rate') else 0
        }
        
        return Response(section_data, status=status.HTTP_200_OK)
    
    elif request.method == 'PUT':
        serializer = CourseSectionCreateSerializer(section, data=request.data)
        
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            updated_section = serializer.save()
            logger.info(f"Section updated: {updated_section.title} by admin {request.user.email}")
            
            return Response(CourseSectionSerializer(updated_section).data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Update section error: {str(e)}")
            return Response(
                {'detail': 'Section update failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    elif request.method == 'DELETE':
        try:
            # Check if section has lessons
            lessons_count = section.lessons.count()
            active_progress = UserLessonProgress.objects.filter(lesson__section=section).count()
            
            if lessons_count > 0:
                return Response(
                    {
                        'detail': f'Cannot delete section. It has {lessons_count} lessons.',
                        'lessons_count': lessons_count,
                        'active_progress': active_progress,
                        'suggestion': 'Please delete all lessons first or move them to another section.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            section_title = section.title
            section.delete()
            
            # Update course totals
            course.update_course_totals()
            
            logger.info(f"Section deleted: {section_title} from course {course.title} by admin {request.user.email}")
            
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        except Exception as e:
            logger.error(f"Delete section error: {str(e)}")
            return Response(
                {'detail': 'Section deletion failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        
@api_view(['POST'])
@permission_classes([IsAdmin])
def reorder_sections(request, course_id, section_id=None):
    """
    Admin: Reorder sections within a course
    POST /api/admin/courses/{course_id}/sections/reorder/
    """
    try:
        course = Course.objects.get(id=course_id)
        
        section_orders = request.data.get('section_orders', [])
        if not section_orders:
            return Response(
                {'detail': 'section_orders is required. Format: [{"id": "uuid", "order": 1}, ...]'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            for item in section_orders:
                section_id = item.get('id')
                new_order = item.get('order')
                
                if not section_id or new_order is None:
                    continue
                
                try:
                    section = CourseSection.objects.get(id=section_id, course=course)
                    section.order = new_order
                    section.save(update_fields=['order'])
                except CourseSection.DoesNotExist:
                    continue
            
            logger.info(f"Sections reordered for course {course.title} by admin {request.user.email}")
            
            return Response({
                'message': f'Successfully reordered {len(section_orders)} sections.',
                'course_title': course.title
            }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Reorder sections error: {str(e)}")
        return Response(
            {'detail': 'Failed to reorder sections.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# COURSE LESSON MANAGEMENT

@api_view(['GET', 'POST'])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def section_lessons(request, course_id, section_id):
    """
    Admin: List lessons or create new lesson for section
    GET/POST /api/admin/courses/{course_id}/sections/{section_id}/lessons/
    """
    try:
        course = Course.objects.get(id=course_id)
        section = CourseSection.objects.get(id=section_id, course=course)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseSection.DoesNotExist:
        return Response({'detail': 'Section not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # List all lessons with progress stats
        lessons = CourseLesson.objects.filter(section=section).annotate(
            progress_count=Count('user_progress'),
            completed_count=Count('user_progress', filter=Q(user_progress__is_completed=True)),
            average_watch_percentage=Avg('user_progress__watch_percentage')
        ).order_by('order')
        
        serializer = CourseLessonSerializer(lessons, many=True)
        
        return Response({
            'course': {'id': str(course.id), 'title': course.title},
            'section': {'id': str(section.id), 'title': section.title},
            'lessons': serializer.data
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        # Create new lesson
        serializer = CourseLessonCreateSerializer(data=request.data, context={'section': section})

        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            with transaction.atomic():
                lesson = serializer.save(section=section, created_by=request.user)

                # Handle video processing
                if lesson.lesson_type == 'video':
                    video_url = lesson.get_video_url()
                    logger.info(f"Processing video for lesson {lesson.title}")

                    # Always try to extract duration if not set
                    if not lesson.duration_seconds:
                        logger.info("Duration not set, attempting to extract...")
                        try:
                            # For uploaded videos with public_id
                            if lesson.video_source == 'upload':
                                # Get public_id (handle both string and CloudinaryField)
                                public_id = lesson.video_file
                                if hasattr(lesson.video_file, 'public_id'):
                                    public_id = lesson.video_file.public_id

                                logger.info(f"Using public_id: {public_id}")

                                # Skip Cloudinary API and go directly to video analysis
                                if video_url:
                                    logger.info("Using direct video analysis for uploaded Cloudinary video...")
                                    duration = extract_video_duration(video_url)
                                    if duration:
                                        lesson.duration_seconds = duration
                                        lesson.save(update_fields=['duration_seconds'])
                                        logger.info(f"Set duration from video analysis: {duration} seconds")
                                    else:
                                        logger.warning("Direct video analysis failed")

                            # For URL-based videos
                            elif lesson.video_source in ['url', 'streaming'] and video_url:
                                logger.info("Trying URL-based duration extraction")
                                duration = extract_video_duration(video_url)
                                if duration:
                                    lesson.duration_seconds = duration
                                    lesson.save(update_fields=['duration_seconds'])
                                    logger.info(f"Set duration from URL extraction: {duration} seconds")

                        except Exception as e:
                            logger.error(f"Could not extract video duration: {str(e)}")

                    # Generate thumbnail if not provided
                    if not lesson.thumbnail and video_url:
                        try:
                            if 'cloudinary.com' in video_url and isinstance(lesson.video_file, str):
                                # For Cloudinary videos with public_id, generate thumbnail directly
                                thumbnail_url = generate_cloudinary_thumbnail_from_public_id(lesson.video_file, str(lesson.id))
                            else:
                                # For other video sources or CloudinaryField objects
                                thumbnail_url = generate_video_thumbnail(video_url, str(lesson.id))

                            if thumbnail_url:
                                lesson.thumbnail = thumbnail_url
                                lesson.save(update_fields=['thumbnail'])
                        except Exception as e:
                            logger.warning(f"Could not generate thumbnail: {str(e)}")

                logger.info(f"Lesson created: {lesson.title} in section {section.title} by admin {request.user.email}")

                return Response(CourseLessonSerializer(lesson).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Create lesson error: {str(e)}")
            return Response(
                {'detail': 'Lesson creation failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def lesson_detail(request, course_id, section_id, lesson_id):
    """
    Admin: Get, update, or delete lesson
    GET/PUT/DELETE /api/admin/courses/{course_id}/sections/{section_id}/lessons/{lesson_id}/
    """
    try:
        course = Course.objects.get(id=course_id)
        section = CourseSection.objects.get(id=section_id, course=course)
        lesson = CourseLesson.objects.get(id=lesson_id, section=section)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseSection.DoesNotExist:
        return Response({'detail': 'Section not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseLesson.DoesNotExist:
        return Response({'detail': 'Lesson not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'GET':
        # Get lesson with detailed analytics
        lesson_data = CourseLessonSerializer(lesson).data
        
        # Add progress analytics
        total_views = UserLessonProgress.objects.filter(lesson=lesson).count()
        completed_views = UserLessonProgress.objects.filter(lesson=lesson, is_completed=True).count()
        avg_watch_time = UserLessonProgress.objects.filter(lesson=lesson).aggregate(
            avg=Avg('watch_time_seconds')
        )['avg'] or 0
        avg_completion_rate = UserLessonProgress.objects.filter(lesson=lesson).aggregate(
            avg=Avg('watch_percentage')
        )['avg'] or 0
        
        lesson_data['analytics'] = {
            'total_views': total_views,
            'completed_views': completed_views,
            'completion_rate': round((completed_views / total_views * 100), 2) if total_views > 0 else 0,
            'average_watch_time_seconds': round(avg_watch_time, 2),
            'average_completion_percentage': round(avg_completion_rate, 2)
        }
        
        # Add navigation info
        lesson_data['navigation'] = {
            'next_lesson': lesson.get_next_lesson().id if lesson.get_next_lesson() else None,
            'previous_lesson': lesson.get_previous_lesson().id if lesson.get_previous_lesson() else None
        }
        
        return Response(lesson_data, status=status.HTTP_200_OK)
    
    elif request.method == 'PUT':
        serializer = CourseLessonCreateSerializer(lesson, data=request.data, partial=False, context={'section': section})
        
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                updated_lesson = serializer.save()
                
                # Update video duration if video changed
                if 'video_file' in request.FILES or 'video_url' in request.data:
                    try:
                        video_url = updated_lesson.get_video_url()
                        if video_url:
                            duration = extract_video_duration(video_url)
                            if duration:
                                updated_lesson.duration_seconds = duration
                                updated_lesson.save(update_fields=['duration_seconds'])
                    except Exception as e:
                        logger.warning(f"Could not extract video duration: {str(e)}")
                
                logger.info(f"Lesson updated: {updated_lesson.title} by admin {request.user.email}")
                
                return Response(CourseLessonSerializer(updated_lesson).data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Update lesson error: {str(e)}")
            return Response(
                {'detail': 'Lesson update failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    elif request.method == 'DELETE':
        try:
            # Check if lesson has user progress
            progress_count = UserLessonProgress.objects.filter(lesson=lesson).count()
            completed_progress = UserLessonProgress.objects.filter(lesson=lesson, is_completed=True).count()
            
            if completed_progress > 0:
                return Response(
                    {
                        'detail': f'Cannot delete lesson. {completed_progress} users have completed it.',
                        'total_progress': progress_count,
                        'completed_progress': completed_progress,
                        'suggestion': 'Consider deactivating the lesson instead of deleting it.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            lesson_title = lesson.title
            
            # Clean up video file if uploaded
            if lesson.video_source == 'upload' and lesson.video_file:
                try:
                    destroy(lesson.video_file.public_id, resource_type="video")
                except Exception as e:
                    logger.error(f"Failed to delete video file: {str(e)}")
            
            lesson.delete()
            
            logger.info(f"Lesson deleted: {lesson_title} from section {section.title} by admin {request.user.email}")
            
            return Response(
                {'detail': f'Lesson "{lesson_title}" deleted successfully.'},
                status=status.HTTP_200_OK
            )
        
        except Exception as e:
            logger.error(f"Delete lesson error: {str(e)}")
            return Response(
                {'detail': 'Lesson deletion failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# BULK LESSON OPERATIONS

@api_view(['POST'])
@permission_classes([IsAdmin])
def bulk_lesson_actions(request, course_id, section_id):
    """
    Admin: Bulk actions on lessons
    POST /api/admin/courses/{course_id}/sections/{section_id}/lessons/bulk-actions/
    
    Actions: reorder, activate, deactivate, move_to_section, delete, update_settings
    """
    try:
        course = Course.objects.get(id=course_id)
        section = CourseSection.objects.get(id=section_id, course=course)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseSection.DoesNotExist:
        return Response({'detail': 'Section not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    action = request.data.get('action')
    lesson_ids = request.data.get('lesson_ids', [])
    
    if not action or not lesson_ids:
        return Response(
            {'detail': 'Action and lesson_ids are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    valid_actions = ['reorder', 'activate', 'deactivate', 'move_to_section', 'delete', 'update_settings']
    
    if action not in valid_actions:
        return Response(
            {'detail': f'Invalid action. Valid actions: {", ".join(valid_actions)}'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        lessons = CourseLesson.objects.filter(id__in=lesson_ids, section=section)
        
        if not lessons.exists():
            return Response(
                {'detail': 'No lessons found with provided IDs in this section.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        with transaction.atomic():
            if action == 'reorder':
                # Reorder lessons based on provided order
                new_order = request.data.get('new_order', [])
                if len(new_order) != len(lesson_ids):
                    return Response(
                        {'detail': 'new_order must have same length as lesson_ids.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                for i, lesson_id in enumerate(lesson_ids):
                    try:
                        lesson = lessons.get(id=lesson_id)
                        lesson.order = new_order[i]
                        lesson.save(update_fields=['order'])
                    except CourseLesson.DoesNotExist:
                        continue
                
                updated_count = len(lesson_ids)
                message = f'Successfully reordered {updated_count} lessons.'
            
            elif action == 'activate':
                updated_count = lessons.update(is_active=True)
                message = f'Successfully activated {updated_count} lessons.'
            
            elif action == 'deactivate':
                updated_count = lessons.update(is_active=False)
                message = f'Successfully deactivated {updated_count} lessons.'
            
            elif action == 'move_to_section':
                target_section_id = request.data.get('target_section_id')
                if not target_section_id:
                    return Response(
                        {'detail': 'target_section_id is required for move_to_section action.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                try:
                    target_section = CourseSection.objects.get(id=target_section_id, course=course)
                except CourseSection.DoesNotExist:
                    return Response(
                        {'detail': 'Target section not found.'},
                        status=status.HTTP_404_NOT_FOUND
                    )
                
                # Move lessons and reorder
                for lesson in lessons:
                    # Get next order in target section
                    last_lesson = CourseLesson.objects.filter(section=target_section).order_by('-order').first()
                    new_order = (last_lesson.order + 1) if last_lesson else 1
                    
                    lesson.section = target_section
                    lesson.order = new_order
                    lesson.save()
                
                updated_count = lessons.count()
                message = f'Successfully moved {updated_count} lessons to {target_section.title}.'
            
            elif action == 'update_settings':
                # Update common settings for selected lessons
                settings = request.data.get('settings', {})
                allowed_settings = ['is_preview', 'require_completion', 'auto_play_next', 'minimum_watch_percentage']
                
                update_data = {}
                for key, value in settings.items():
                    if key in allowed_settings:
                        update_data[key] = value
                
                if update_data:
                    updated_count = lessons.update(**update_data)
                    message = f'Successfully updated settings for {updated_count} lessons.'
                else:
                    return Response(
                        {'detail': 'No valid settings provided.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            elif action == 'delete':
                # Check for user progress before deletion
                lessons_with_progress = []
                lessons_to_delete = []
                
                for lesson in lessons:
                    if UserLessonProgress.objects.filter(lesson=lesson, is_completed=True).exists():
                        lessons_with_progress.append(lesson.title)
                    else:
                        lessons_to_delete.append(lesson)
                
                # Delete safe lessons
                deleted_count = 0
                if lessons_to_delete:
                    # Clean up video files
                    for lesson in lessons_to_delete:
                        if lesson.video_source == 'upload' and lesson.video_file:
                            try:
                                destroy(lesson.video_file.public_id, resource_type="video")
                            except Exception as e:
                                logger.error(f"Failed to delete video for lesson {lesson.title}: {str(e)}")
                    
                    CourseLesson.objects.filter(id__in=[l.id for l in lessons_to_delete]).delete()
                    deleted_count = len(lessons_to_delete)
                
                return Response({
                    'message': 'Bulk deletion completed with safety checks.',
                    'deleted_lessons': deleted_count,
                    'lessons_with_progress': len(lessons_with_progress),
                    'lessons_with_progress_names': lessons_with_progress
                }, status=status.HTTP_200_OK)
            
            # Update section and course totals
            section.update_section_totals()
            
            logger.info(f"Bulk lesson action '{action}' performed by admin {request.user.email}")
            
            return Response({
                'message': message,
                'updated_lessons': updated_count if 'updated_count' in locals() else 0
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Bulk lesson actions error: {str(e)}")
        return Response(
            {'detail': 'Bulk action failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# USER LESSON PROGRESS TRACKING

@api_view(['GET'])
@permission_classes([IsAdmin])
def lesson_progress_analytics(request, course_id, section_id, lesson_id):
    """
    Admin: Get detailed lesson progress analytics
    GET /api/admin/courses/{course_id}/sections/{section_id}/lessons/{lesson_id}/analytics/
    """
    try:
        course = Course.objects.get(id=course_id)
        section = CourseSection.objects.get(id=section_id, course=course)
        lesson = CourseLesson.objects.get(id=lesson_id, section=section)
    except Course.DoesNotExist:
        return Response({'detail': 'Course not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseSection.DoesNotExist:
        return Response({'detail': 'Section not found.'}, status=status.HTTP_404_NOT_FOUND)
    except CourseLesson.DoesNotExist:
        return Response({'detail': 'Lesson not found.'}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        # Get all progress records for this lesson
        progress_records = UserLessonProgress.objects.filter(lesson=lesson).select_related('user')
        
        total_enrolled = UserCourseProgress.objects.filter(course=course).count()
        total_views = progress_records.count()
        completed_views = progress_records.filter(is_completed=True).count()
        
        # Calculate engagement metrics
        if total_views > 0:
            avg_watch_percentage = progress_records.aggregate(avg=Avg('watch_percentage'))['avg'] or 0
            avg_watch_time = progress_records.aggregate(avg=Avg('watch_time_seconds'))['avg'] or 0
            completion_rate = (completed_views / total_views) * 100
        else:
            avg_watch_percentage = 0
            avg_watch_time = 0
            completion_rate = 0
        
        # Engagement over time (last 30 days)
        from datetime import timedelta
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_views = progress_records.filter(first_accessed__gte=thirty_days_ago).count()
        
        # Watch percentage distribution
        percentage_ranges = [
            (0, 25), (25, 50), (50, 75), (75, 100)
        ]
        percentage_distribution = {}
        
        for start, end in percentage_ranges:
            count = progress_records.filter(
                watch_percentage__gte=start,
                watch_percentage__lt=end if end < 100 else 101
            ).count()
            percentage_distribution[f"{start}-{end}%"] = count
        
        # Most common drop-off points (for video lessons)
        drop_off_points = []
        if lesson.lesson_type == 'video' and lesson.duration_seconds:
            # Calculate drop-off every 10% of video
            duration = lesson.duration_seconds
            for i in range(1, 11):
                position = int(duration * (i / 10))
                dropped_at_position = progress_records.filter(
                    current_position_seconds__lt=position,
                    is_completed=False
                ).count()
                
                drop_off_points.append({
                    'position_seconds': position,
                    'position_percentage': i * 10,
                    'dropped_count': dropped_at_position
                })
        
        # Top performing students
        top_students = progress_records.filter(is_completed=True).order_by('-watch_percentage', 'watch_time_seconds')[:10]
        top_students_data = []
        
        for progress in top_students:
            top_students_data.append({
                'user_id': str(progress.user.id),
                'user_name': progress.user.full_name,
                'user_email': progress.user.email,
                'watch_percentage': progress.watch_percentage,
                'watch_time_seconds': progress.watch_time_seconds,
                'completed_at': progress.completed_at,
                'rating': progress.rating
            })
        
        analytics_data = {
            'lesson_info': {
                'id': str(lesson.id),
                'title': lesson.title,
                'lesson_type': lesson.lesson_type,
                'duration_seconds': lesson.duration_seconds,
                'section_title': section.title,
                'course_title': course.title
            },
            'overview': {
                'total_enrolled_in_course': total_enrolled,
                'total_lesson_views': total_views,
                'completed_views': completed_views,
                'completion_rate': round(completion_rate, 2),
                'view_rate': round((total_views / total_enrolled * 100), 2) if total_enrolled > 0 else 0
            },
            'engagement': {
                'average_watch_percentage': round(avg_watch_percentage, 2),
                'average_watch_time_seconds': round(avg_watch_time, 2),
                'recent_views_30_days': recent_views,
                'percentage_distribution': percentage_distribution
            },
            'video_analytics': {
                'drop_off_points': drop_off_points
            } if lesson.lesson_type == 'video' else {},
            'top_students': top_students_data
        }
        
        return Response(analytics_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Lesson progress analytics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch lesson analytics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# VIDEO PROCESSING UTILITIES

@api_view(['POST'])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser])
def upload_lesson_video(request):
    """
    Admin: Upload video file for lesson with automatic processing
    POST /api/admin/lessons/upload-video/
    """
    if 'video_file' not in request.FILES:
        return Response(
            {'detail': 'video_file is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        video_file = request.FILES['video_file']
        
        # Validate file
        max_size = 1024 * 1024 * 1024  # 1GB
        if video_file.size > max_size:
            return Response(
                {'detail': 'Video file size cannot exceed 1GB.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create organized folder structure
        current_date = timezone.now()
        folder_path = f"courses/lessons/videos/{current_date.year}/{current_date.month:02d}"
        
        # Upload to Cloudinary
        upload_result = upload(
            video_file,
            resource_type="video",
            folder=folder_path,
            public_id=f"lesson_video_{current_date.strftime('%Y%m%d_%H%M%S')}",
            overwrite=True,
            transformation=[
                {'quality': 'auto:good'},
                {'format': 'mp4'}
            ],
            tags=['lesson_video', f'uploaded_by_{request.user.id}']
        )
        
        # Extract video information
        video_info = {
            'public_id': upload_result['public_id'],
            'url': upload_result['secure_url'],
            'duration_seconds': upload_result.get('duration'),
            'format': upload_result.get('format'),
            'size_bytes': upload_result.get('bytes'),
            'width': upload_result.get('width'),
            'height': upload_result.get('height')
        }
        
        # Generate thumbnail
        try:
            thumbnail_url = generate_video_thumbnail(upload_result['secure_url'])
            if thumbnail_url:
                video_info['thumbnail_url'] = thumbnail_url
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {str(e)}")
        
        logger.info(f"Lesson video uploaded by admin {request.user.email}: {upload_result['public_id']}")
        
        return Response({
            'message': 'Video uploaded successfully.',
            'video_info': video_info
        }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Lesson video upload error: {str(e)}")
        return Response(
            {'detail': f'Video upload failed: {str(e)}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# PAYMENT GATEWAY INTEGRATION VIEWS

@api_view(['POST'])
@permission_classes([IsAdmin])
def process_manual_enrollment(request):
    """
    Admin: Manually Enroll User in Course (for free courses or manual payments)
    POST /api/admin/enrollments/manual/
    """
    user_id = request.data.get('user_id')
    course_id = request.data.get('course_id')
    payment_method = request.data.get('payment_method', 'manual')
    amount_paid = request.data.get('amount_paid', 0)
    notes = request.data.get('notes', '')
    
    if not user_id or not course_id:
        return Response(
            {'detail': 'user_id and course_id are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user = User.objects.get(id=user_id)
        course = Course.objects.get(id=course_id)
        
        # Check if user is already enrolled
        if CourseEnrollment.objects.filter(user=user, course=course).exists():
            return Response(
                {'detail': 'User is already enrolled in this course.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Create enrollment
            enrollment = CourseEnrollment.objects.create(
                user=user,
                course=course,
                payment_status='completed' if amount_paid > 0 or course.is_free() else 'pending',
                payment_method=payment_method,
                amount_paid=amount_paid,
                currency=course.currency
            )
            
            # Create progress record
            UserCourseProgress.objects.create(
                user=user,
                course=course,
                progress_percentage=0
            )
            
            # Send notification email to user
            EmailService.send_enrollment_confirmation(user, course, enrollment)
            
            # Log manual enrollment
            logger.info(f"Manual enrollment created by admin {request.user.email}: {user.email} -> {course.title}")
            
            serializer = CourseEnrollmentSerializer(enrollment)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    except User.DoesNotExist:
        return Response(
            {'detail': 'User not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Manual enrollment error: {str(e)}")
        return Response(
            {'detail': 'Manual enrollment failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def payment_analytics(request):
    """
    Admin: Get Payment Analytics and Revenue Data
    GET /api/admin/payments/analytics/
    """
    try:
        from datetime import datetime, timedelta
        from django.db.models import Sum, Count, Avg
        
        # Date range filters
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Revenue analytics
        total_revenue = CourseEnrollment.objects.filter(
            payment_status='completed'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        recent_revenue = CourseEnrollment.objects.filter(
            payment_status='completed',
            enrolled_at__gte=start_date
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        # Enrollment analytics
        total_enrollments = CourseEnrollment.objects.count()
        paid_enrollments = CourseEnrollment.objects.filter(payment_status='completed').count()
        pending_payments = CourseEnrollment.objects.filter(payment_status='pending').count()
        failed_payments = CourseEnrollment.objects.filter(payment_status='failed').count()
        
        # Average order value
        avg_order_value = CourseEnrollment.objects.filter(
            payment_status='completed',
            amount_paid__gt=0
        ).aggregate(avg=Avg('amount_paid'))['avg'] or 0
        
        # Top performing courses by revenue
        top_courses = Course.objects.annotate(
            revenue=Sum('enrollments__amount_paid', filter=Q(enrollments__payment_status='completed')),
            enrollment_count=Count('enrollments', filter=Q(enrollments__payment_status='completed'))
        ).filter(revenue__gt=0).order_by('-revenue')[:10]
        
        top_courses_data = []
        for course in top_courses:
            top_courses_data.append({
                'id': str(course.id),
                'title': course.title,
                'revenue': float(course.revenue or 0),
                'enrollments': course.enrollment_count,
                'avg_price': float((course.revenue or 0) / max(course.enrollment_count, 1))
            })
        
        # Payment methods breakdown
        payment_methods = CourseEnrollment.objects.filter(
            payment_status='completed'
        ).values('payment_method').annotate(
            count=Count('id'),
            revenue=Sum('amount_paid')
        ).order_by('-revenue')
        
        analytics_data = {
            'revenue': {
                'total_revenue': float(total_revenue),
                'recent_revenue': float(recent_revenue),
                'average_order_value': float(avg_order_value),
                'revenue_growth': 0  # Calculate based on previous period if needed
            },
            'enrollments': {
                'total_enrollments': total_enrollments,
                'paid_enrollments': paid_enrollments,
                'pending_payments': pending_payments,
                'failed_payments': failed_payments,
                'conversion_rate': round((paid_enrollments / max(total_enrollments, 1)) * 100, 2)
            },
            'top_courses': top_courses_data,
            'payment_methods': list(payment_methods),
            'period_days': days
        }
        
        return Response(analytics_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Payment analytics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch payment analytics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

# EXAM MANAGEMENT VIEWS

@api_view(['GET'])
@permission_classes([IsAdmin])
def list_course_exams(request, course_id):
    """
    Admin: List All Exams for a Course
    GET /api/admin/courses/{course_id}/exams/
    """
    try:
        course = Course.objects.get(id=course_id)
        
        # Get query parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        exam_type = request.GET.get('exam_type', '')
        is_published = request.GET.get('is_published', '')
        
        # Build queryset
        queryset = CourseExam.objects.filter(course=course).select_related('created_by')
        
        if exam_type:
            queryset = queryset.filter(exam_type=exam_type)
        
        if is_published:
            queryset = queryset.filter(is_published=is_published.lower() == 'true')
        
        queryset = queryset.order_by('exam_type', 'title')
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = CourseExamSerializer(page_obj.object_list, many=True)
        
        return Response({
            'course': {
                'id': str(course.id),
                'title': course.title
            },
            'exams': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_exams': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"List course exams error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course exams.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAdmin])
def create_course_exam(request, course_id):
    """
    Admin: Create New Exam for Course
    POST /api/admin/courses/{course_id}/exams/
    """
    try:
        course = Course.objects.get(id=course_id)
        
        serializer = CourseExamCreateSerializer(data=request.data, context={'request': request, 'course': course})
        
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            exam = serializer.save()
            
            # Send notification to other admins
            AdminEmailService.notify_exam_created(exam, request.user)
            
            logger.info(f"Exam created: {exam.title} for course {course.title} by admin {request.user.email}")
            
            return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Create exam error: {str(e)}")
        return Response(
            {'detail': 'Exam creation failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def get_exam_details(request, course_id, exam_id):
    """
    Admin: Get Exam Details with Questions and Analytics
    GET /api/admin/courses/{course_id}/exams/{exam_id}/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.select_related('course', 'created_by').prefetch_related(
            'questions__answers', 'attempts'
        ).get(id=exam_id, course=course)
        
        serializer = CourseExamSerializer(exam)
        data = serializer.data
        
        # Add exam analytics
        total_attempts = exam.attempts.count()
        completed_attempts = exam.attempts.filter(status='completed').count()
        passed_attempts = exam.attempts.filter(passed=True).count()
        
        avg_score = exam.attempts.filter(status='completed').aggregate(
            avg=Avg('percentage_score')
        )['avg'] or 0
        
        data.update({
            'analytics': {
                'total_attempts': total_attempts,
                'completed_attempts': completed_attempts,
                'passed_attempts': passed_attempts,
                'pass_rate': round((passed_attempts / completed_attempts * 100), 2) if completed_attempts > 0 else 0,
                'average_score': round(avg_score, 2),
                'total_questions': exam.questions.filter(is_active=True).count()
            }
        })
        
        return Response(data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get exam details error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch exam details.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAdmin])
def update_exam(request, course_id, exam_id):
    """
    Admin: Update Exam
    PUT/PATCH /api/admin/courses/{course_id}/exams/{exam_id}/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    partial = request.method == 'PATCH'
    serializer = CourseExamSerializer(exam, data=request.data, partial=partial, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        updated_exam = serializer.save()
        logger.info(f"Exam updated: {updated_exam.title} by admin {request.user.email}")
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Update exam error: {str(e)}")
        return Response(
            {'detail': 'Exam update failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['DELETE'])
@permission_classes([IsAdmin])
def delete_exam(request, course_id, exam_id):
    """
    Admin: Delete Exam with Safety Checks
    DELETE /api/admin/courses/{course_id}/exams/{exam_id}/delete/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        # Check if exam has attempts
        attempts_count = exam.attempts.count()
        completed_attempts = exam.attempts.filter(status='completed').count()
        
        if completed_attempts > 0:
            return Response(
                {
                    'detail': f'Cannot delete exam. It has {completed_attempts} completed attempts.',
                    'attempts_count': attempts_count,
                    'completed_attempts': completed_attempts,
                    'suggestion': 'Consider deactivating the exam instead of deleting it.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        exam_title = exam.title
        exam.delete()
        
        logger.info(f"Exam deleted: {exam_title} from course {course.title} by admin {request.user.email}")
        
        return Response(
            {
                "success": True,
                "message": f"Exam '{exam_title}' deleted successfully.",
                "course_id": str(course.id),
                "exam_id": str(exam_id)
            },
            status=status.HTTP_200_OK
        )

    
    except Exception as e:
        logger.error(f"Delete exam error: {str(e)}")
        return Response(
            {'detail': 'Exam deletion failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# EXAM QUESTION MANAGEMENT

@api_view(['GET', 'POST'])
@permission_classes([IsAdmin])
def exam_questions(request, course_id, exam_id):
    """
    Admin: List Questions or Create New Question for Exam
    GET/POST /api/admin/courses/{course_id}/exams/{exam_id}/questions/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.method == 'GET':
        # List questions
        questions = ExamQuestion.objects.filter(exam=exam).prefetch_related('answers').order_by('order', 'created_at')
        serializer = ExamQuestionSerializer(questions, many=True)
        
        return Response({
            'exam': {
                'id': str(exam.id),
                'title': exam.title,
                'total_questions': questions.count()
            },
            'questions': serializer.data
        }, status=status.HTTP_200_OK)
    
    elif request.method == 'POST':
        # Create new question
        serializer = ExamQuestionCreateSerializer(data=request.data, context={'exam': exam})
        
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                question = serializer.save()
                
                # Update exam's total questions count
                exam.calculate_total_questions()
                
                logger.info(f"Question created for exam {exam.title} by admin {request.user.email}")
                
                response_serializer = ExamQuestionSerializer(question)
                return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        
        except Exception as e:
            logger.error(f"Create question error: {str(e)}")
            return Response(
                {'detail': 'Question creation failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET', 'PUT', 'DELETE'])
@permission_classes([IsAdmin])
def exam_question_detail(request, course_id, exam_id, question_id):
    """
    Admin: Get, Update, or Delete Exam Question
    GET/PUT/DELETE /api/admin/courses/{course_id}/exams/{exam_id}/questions/{question_id}/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
        question = ExamQuestion.objects.prefetch_related('answers').get(id=question_id, exam=exam)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except ExamQuestion.DoesNotExist:
        return Response(
            {'detail': 'Question not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    if request.method == 'GET':
        serializer = ExamQuestionSerializer(question)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    elif request.method == 'PUT':
        serializer = ExamQuestionCreateSerializer(question, data=request.data, context={'exam': exam})
        
        if not serializer.is_valid():
            return Response(
                {'detail': 'Invalid input data.', 'errors': serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            updated_question = serializer.save()
            logger.info(f"Question updated in exam {exam.title} by admin {request.user.email}")

            # Return updated question using read serializer
            response_serializer = ExamQuestionSerializer(updated_question)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.error(f"Update question error: {str(e)}")
            return Response(
                {'detail': 'Question update failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    elif request.method == 'DELETE':
        try:
            question.delete()
            
            # Update exam's total questions count
            exam.calculate_total_questions()
            
            logger.info(f"Question deleted from exam {exam.title} by admin {request.user.email}")
            
            return Response(status=status.HTTP_204_NO_CONTENT)
        
        except Exception as e:
            logger.error(f"Delete question error: {str(e)}")
            return Response(
                {'detail': 'Question deletion failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@api_view(['GET'])
@permission_classes([IsAdmin])
def exam_attempts(request, course_id, exam_id):
    """
    Admin: Get All Attempts for an Exam
    GET /api/admin/courses/{course_id}/exams/{exam_id}/attempts/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
        
        # Get query parameters
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        status_filter = request.GET.get('status', '')
        passed_filter = request.GET.get('passed', '')
        
        # Build queryset
        queryset = UserExamAttempt.objects.filter(exam=exam).select_related('user').order_by('-started_at')
        
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        if passed_filter:
            queryset = queryset.filter(passed=passed_filter.lower() == 'true')
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = UserExamAttemptSerializer(page_obj.object_list, many=True)
        
        # Calculate summary stats
        total_attempts = queryset.count()
        completed_attempts = queryset.filter(status='completed').count()
        passed_attempts = queryset.filter(passed=True).count()
        avg_score = queryset.filter(status='completed').aggregate(avg=Avg('percentage_score'))['avg'] or 0
        
        return Response({
            'exam': {
                'id': str(exam.id),
                'title': exam.title,
                'course_title': course.title
            },
            'attempts': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_attempts': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'summary': {
                'total_attempts': total_attempts,
                'completed_attempts': completed_attempts,
                'passed_attempts': passed_attempts,
                'pass_rate': round((passed_attempts / completed_attempts * 100), 2) if completed_attempts > 0 else 0,
                'average_score': round(avg_score, 2)
            }
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get exam attempts error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch exam attempts.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def exam_statistics(request):
    """
    Admin: Get Overall Exam Statistics
    GET /api/admin/exams/statistics/
    """
    try:
        # Basic exam stats
        total_exams = CourseExam.objects.count()
        published_exams = CourseExam.objects.filter(is_published=True).count()
        active_exams = CourseExam.objects.filter(is_active=True).count()
        
        # Attempt stats
        total_attempts = UserExamAttempt.objects.count()
        completed_attempts = UserExamAttempt.objects.filter(status='completed').count()
        passed_attempts = UserExamAttempt.objects.filter(passed=True).count()
        
        # Average scores
        avg_score = UserExamAttempt.objects.filter(status='completed').aggregate(
            avg=Avg('percentage_score')
        )['avg'] or 0
        
        # Exams by type
        exams_by_type = dict(
            CourseExam.objects.values_list('exam_type').annotate(count=Count('id'))
        )
        
        # Recent activity (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_attempts = UserExamAttempt.objects.filter(started_at__gte=thirty_days_ago).count()
        
        # Top performing exams
        top_exams = CourseExam.objects.annotate(
            attempt_count=Count('attempts'),
            pass_rate=Avg('attempts__passed', filter=Q(attempts__status='completed'))
        ).filter(attempt_count__gt=0).order_by('-pass_rate')[:10]
        
        top_exams_data = []
        for exam in top_exams:
            top_exams_data.append({
                'id': str(exam.id),
                'title': exam.title,
                'course_title': exam.course.title,
                'attempt_count': exam.attempt_count,
                'pass_rate': round((exam.pass_rate or 0) * 100, 2)
            })
        
        stats_data = {
            'total_exams': total_exams,
            'published_exams': published_exams,
            'active_exams': active_exams,
            'total_attempts': total_attempts,
            'completed_attempts': completed_attempts,
            'passed_attempts': passed_attempts,
            'overall_pass_rate': round((passed_attempts / completed_attempts * 100), 2) if completed_attempts > 0 else 0,
            'average_score': round(avg_score, 2),
            'exams_by_type': exams_by_type,
            'recent_attempts': recent_attempts,
            'top_performing_exams': top_exams_data
        }
        
        serializer = ExamStatsSerializer(stats_data)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Exam statistics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch exam statistics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['GET'])
@permission_classes([IsAdmin])
def exam_question_analytics(request, course_id, exam_id):
    """
    Admin: Get Analytics for All Questions in an Exam
    GET /api/admin/courses/{course_id}/exams/{exam_id}/questions/analytics/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        # Get all questions for this exam
        questions = ExamQuestion.objects.filter(exam=exam, is_active=True).order_by('order')
        
        analytics_data = []
        
        for question in questions:
            # Get all user answers for this question from completed attempts
            user_answers = UserExamAnswer.objects.filter(
                question=question,
                attempt__status='completed'
            ).select_related('attempt')
            
            total_attempts = user_answers.count()
            correct_attempts = user_answers.filter(is_correct=True).count()
            
            # Calculate success rate
            success_rate = round((correct_attempts / total_attempts * 100), 2) if total_attempts > 0 else 0
            
            # Calculate average time spent (if available)
            time_data = user_answers.exclude(time_taken_seconds=0).values_list('time_taken_seconds', flat=True)
            average_time_spent = round(sum(time_data) / len(time_data), 2) if time_data else 0
            
            question_stats = {
                'question_id': question.id,
                'question_text': question.question_text,
                'question_type': question.question_type,
                'total_attempts': total_attempts,
                'correct_attempts': correct_attempts,
                'success_rate': success_rate,
                'difficulty_level': question.difficulty_level,
                'average_time_spent': average_time_spent
            }
            
            analytics_data.append(question_stats)
        
        # Overall exam analytics
        total_exam_attempts = UserExamAttempt.objects.filter(exam=exam, status='completed').count()
        
        # Questions sorted by difficulty (lowest success rate first)
        difficult_questions = sorted(analytics_data, key=lambda x: x['success_rate'])[:5]
        easy_questions = sorted(analytics_data, key=lambda x: x['success_rate'], reverse=True)[:5]
        
        response_data = {
            'exam': {
                'id': str(exam.id),
                'title': exam.title,
                'total_questions': len(analytics_data),
                'total_attempts': total_exam_attempts
            },
            'questions_analytics': analytics_data,
            'summary': {
                'average_success_rate': round(sum(q['success_rate'] for q in analytics_data) / len(analytics_data), 2) if analytics_data else 0,
                'most_difficult_questions': difficult_questions,
                'easiest_questions': easy_questions,
                'questions_needing_review': [q for q in analytics_data if q['success_rate'] < 50]
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Exam question analytics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch question analytics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def question_detail_analytics(request, course_id, exam_id, question_id):
    """
    Admin: Get Detailed Analytics for a Specific Question
    GET /api/admin/courses/{course_id}/exams/{exam_id}/questions/{question_id}/analytics/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
        question = ExamQuestion.objects.get(id=question_id, exam=exam)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except ExamQuestion.DoesNotExist:
        return Response(
            {'detail': 'Question not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        # Get all user answers for this question
        user_answers = UserExamAnswer.objects.filter(
            question=question,
            attempt__status='completed'
        ).select_related('attempt', 'attempt__user')
        
        total_attempts = user_answers.count()
        correct_attempts = user_answers.filter(is_correct=True).count()
        success_rate = round((correct_attempts / total_attempts * 100), 2) if total_attempts > 0 else 0
        
        # Time analytics
        time_data = user_answers.exclude(time_taken_seconds=0).values_list('time_taken_seconds', flat=True)
        average_time_spent = round(sum(time_data) / len(time_data), 2) if time_data else 0
        
        # Answer choice analytics (for multiple choice questions)
        answer_choices_stats = []
        if question.question_type == 'multiple_choice':
            for answer in question.answers.all():
                times_selected = user_answers.filter(selected_answers=answer).count()
                selection_percentage = round((times_selected / total_attempts * 100), 2) if total_attempts > 0 else 0
                
                answer_choices_stats.append({
                    'answer_id': str(answer.id),
                    'answer_text': answer.answer_text,
                    'is_correct': answer.is_correct,
                    'times_selected': times_selected,
                    'selection_percentage': selection_percentage
                })
        
        # Recent attempts (last 10)
        recent_attempts = []
        for user_answer in user_answers.order_by('-answered_at')[:10]:
            recent_attempts.append({
                'user_name': user_answer.attempt.user.full_name,
                'user_email': user_answer.attempt.user.email,
                'is_correct': user_answer.is_correct,
                'time_taken': user_answer.time_taken_seconds,
                'answered_at': user_answer.answered_at,
                'attempt_score': user_answer.attempt.percentage_score
            })
        
        # Performance over time (group by date)
        from django.db.models import Count, Avg
        from django.utils import timezone
        from datetime import datetime, timedelta
        
        # Last 30 days performance
        thirty_days_ago = timezone.now() - timedelta(days=30)
        daily_performance = user_answers.filter(
            answered_at__gte=thirty_days_ago
        ).extra(
            select={'day': 'date(answered_at)'}
        ).values('day').annotate(
            total_attempts=Count('id'),
            correct_attempts=Count('id', filter=models.Q(is_correct=True)),
            avg_time=Avg('time_taken_seconds')
        ).order_by('day')
        
        response_data = {
            'question': {
                'id': str(question.id),
                'question_text': question.question_text,
                'question_type': question.question_type,
                'difficulty_level': question.difficulty_level,
                'points': question.points,
                'tags': question.tags
            },
            'analytics': {
                'total_attempts': total_attempts,
                'correct_attempts': correct_attempts,
                'success_rate': success_rate,
                'average_time_spent': average_time_spent
            },
            'answer_choices_analytics': answer_choices_stats,
            'recent_attempts': recent_attempts,
            'daily_performance': list(daily_performance),
            'recommendations': {
                'needs_review': success_rate < 50,
                'difficulty_assessment': (
                    'Very Hard' if success_rate < 30 else
                    'Hard' if success_rate < 50 else
                    'Medium' if success_rate < 75 else
                    'Easy'
                ),
                'suggested_actions': []
            }
        }
        
        # Add suggestions based on performance
        if success_rate < 30:
            response_data['recommendations']['suggested_actions'].append(
                'Consider revising this question as it may be too difficult or unclear'
            )
        elif success_rate > 90:
            response_data['recommendations']['suggested_actions'].append(
                'This question might be too easy - consider making it more challenging'
            )
        
        if average_time_spent > 120:  # More than 2 minutes
            response_data['recommendations']['suggested_actions'].append(
                'Students are taking longer than expected - consider simplifying the question'
            )
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Question detail analytics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch question analytics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def exam_performance_trends(request, course_id, exam_id):
    """
    Admin: Get Performance Trends for an Exam Over Time
    GET /api/admin/courses/{course_id}/exams/{exam_id}/performance-trends/
    """
    try:
        course = Course.objects.get(id=course_id)
        exam = CourseExam.objects.get(id=exam_id, course=course)
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    try:
        from django.db.models import Count, Avg, Q
        from datetime import datetime, timedelta
        
        # Get date range from query params
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Daily performance trends
        daily_trends = UserExamAttempt.objects.filter(
            exam=exam,
            status='completed',
            completed_at__gte=start_date
        ).extra(
            select={'day': 'date(completed_at)'}
        ).values('day').annotate(
            total_attempts=Count('id'),
            passed_attempts=Count('id', filter=Q(passed=True)),
            average_score=Avg('percentage_score'),
            average_time=Avg('time_taken_minutes')
        ).order_by('day')
        
        # Weekly comparison
        current_week = UserExamAttempt.objects.filter(
            exam=exam,
            status='completed',
            completed_at__gte=timezone.now() - timedelta(days=7)
        ).aggregate(
            attempts=Count('id'),
            pass_rate=Avg('passed', output_field=models.FloatField()),
            avg_score=Avg('percentage_score')
        )
        
        previous_week = UserExamAttempt.objects.filter(
            exam=exam,
            status='completed',
            completed_at__gte=timezone.now() - timedelta(days=14),
            completed_at__lt=timezone.now() - timedelta(days=7)
        ).aggregate(
            attempts=Count('id'),
            pass_rate=Avg('passed', output_field=models.FloatField()),
            avg_score=Avg('percentage_score')
        )
        
        # Calculate trends
        attempts_trend = 0
        pass_rate_trend = 0
        score_trend = 0
        
        if previous_week['attempts'] and previous_week['attempts'] > 0:
            attempts_trend = round(((current_week['attempts'] or 0) - previous_week['attempts']) / previous_week['attempts'] * 100, 2)
        
        if previous_week['pass_rate'] and previous_week['pass_rate'] > 0:
            pass_rate_trend = round(((current_week['pass_rate'] or 0) - previous_week['pass_rate']) / previous_week['pass_rate'] * 100, 2)
        
        if previous_week['avg_score'] and previous_week['avg_score'] > 0:
            score_trend = round(((current_week['avg_score'] or 0) - previous_week['avg_score']) / previous_week['avg_score'] * 100, 2)
        
        response_data = {
            'exam': {
                'id': str(exam.id),
                'title': exam.title
            },
            'period': {
                'days': days,
                'start_date': start_date.date(),
                'end_date': timezone.now().date()
            },
            'daily_trends': list(daily_trends),
            'weekly_comparison': {
                'current_week': current_week,
                'previous_week': previous_week,
                'trends': {
                    'attempts_change': attempts_trend,
                    'pass_rate_change': pass_rate_trend,
                    'score_change': score_trend
                }
            },
            'insights': []
        }
        
        # Add insights based on trends
        if attempts_trend > 20:
            response_data['insights'].append("📈 Exam attempts increased significantly this week")
        elif attempts_trend < -20:
            response_data['insights'].append("📉 Exam attempts decreased significantly this week")
        
        if pass_rate_trend > 10:
            response_data['insights'].append("✅ Pass rate improved this week")
        elif pass_rate_trend < -10:
            response_data['insights'].append("❌ Pass rate declined this week - may need review")
        
        if score_trend > 5:
            response_data['insights'].append("📊 Average scores improved")
        elif score_trend < -5:
            response_data['insights'].append("📊 Average scores declined")
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Exam performance trends error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch performance trends.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    
@api_view(['GET'])
@permission_classes([IsAdmin])
def get_course_structure_only(request, course_id):
    """
    Admin: Get Course Structure Only (Sections + Lessons + Exams)
    GET /api/admin/courses/{course_id}/structure/
    
    Returns only the structural data without statistics
    """
    try:
        course = Course.objects.select_related(
            'category', 'created_by'
        ).prefetch_related(
            'sections__lessons',
            'exams__questions__answers'
        ).get(id=course_id)
        
        # Use existing serializer for basic course info
        course_serializer = CourseSerializer(course)
        course_data = course_serializer.data
        
        # Add sections with lessons
        sections = course.sections.filter(is_active=True).order_by('order')
        sections_data = []
        
        for section in sections:
            section_serializer = CourseSectionSerializer(section)
            section_data = section_serializer.data
            
            # Add lessons to section
            lessons = section.lessons.filter(is_active=True).order_by('order')
            lessons_serializer = CourseLessonSerializer(lessons, many=True)
            section_data['lessons'] = lessons_serializer.data
            
            sections_data.append(section_data)
        
        # Add exams with questions
        exams = course.exams.filter(is_active=True).order_by('exam_type', 'title')
        exams_data = []
        
        for exam in exams:
            exam_serializer = CourseExamSerializer(exam)
            exam_data = exam_serializer.data
            
            # Add questions with answers
            questions = exam.questions.filter(is_active=True).order_by('order')
            questions_serializer = ExamQuestionSerializer(questions, many=True)
            exam_data['questions'] = questions_serializer.data
            
            exams_data.append(exam_data)
        
        return Response({
            'course': course_data,
            'sections': sections_data,
            'exams': exams_data,
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        logger.error(f"Get course structure error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course structure.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['POST'])
@permission_classes([IsAdmin])
def update_course_pricing(request, course_id):
    """
    Admin: Update Course Pricing and Type
    POST /api/admin/courses/{course_id}/pricing/
    """
    try:
        course = Course.objects.get(id=course_id)
        
        course_type = request.data.get('course_type')
        price = request.data.get('price')
        currency = request.data.get('currency', 'NGN')
        has_discount = request.data.get('has_discount', False)
        discount_percentage = request.data.get('discount_percentage', 0)
        discount_start_date = request.data.get('discount_start_date')
        discount_end_date = request.data.get('discount_end_date')

        # Convert discount dates to timezone-aware datetime
        def make_aware_date(date_value, end_of_day=False):
            if isinstance(date_value, str):
                try:
                    # Parse date only (YYYY-MM-DD)
                    date_obj = datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError:
                    # Parse full datetime string
                    date_obj = datetime.fromisoformat(date_value)

                if end_of_day:
                    date_obj = date_obj.replace(hour=23, minute=59, second=59)

                return timezone.make_aware(date_obj)
            return date_value

        discount_start_date = make_aware_date(discount_start_date) if has_discount and discount_start_date else None
        discount_end_date = make_aware_date(discount_end_date, end_of_day=True) if has_discount and discount_end_date else None
        
        # Validation
        if course_type not in ['free', 'paid', 'premium']:
            return Response(
                {'detail': 'Invalid course type. Must be: free, paid, or premium'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if course_type != 'free' and (not price or float(price) <= 0):
            return Response(
                {'detail': 'Price is required for paid/premium courses'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if course_type == 'free':
            price = 0.00
            has_discount = False
            discount_percentage = 0
            discount_start_date = None
            discount_end_date = None
        
        with transaction.atomic():
            # Update course
            course.course_type = course_type
            course.price = price or 0.00
            course.currency = currency
            course.has_discount = has_discount
            course.discount_percentage = discount_percentage if has_discount else 0
            course.discount_start_date = discount_start_date
            course.discount_end_date = discount_end_date
            course.updated_by = request.user
            course.save()
            
            logger.info(f"Course pricing updated: {course.title} -> {course_type} (${price}) by {request.user.email}")
            
            serializer = CourseSerializer(course)
            return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Update course pricing error: {str(e)}")
        return Response(
            {'detail': 'Failed to update course pricing.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAdmin])
def course_revenue_report(request):
    """
    Admin: Get detailed revenue report by course
    GET /api/admin/courses/revenue-report/
    """
    try:
        # Date range filters
        start_date = request.GET.get('start_date')
        end_date = request.GET.get('end_date')
        course_type = request.GET.get('course_type')
        
        # Base queryset
        queryset = CourseEnrollment.objects.filter(payment_status='completed')
        
        if start_date:
            queryset = queryset.filter(enrolled_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(enrolled_at__lte=end_date)
        if course_type:
            queryset = queryset.filter(course__course_type=course_type)
        
        # Revenue by course
        revenue_by_course = queryset.values(
            'course__id',
            'course__title',
            'course__course_type',
            'course__price'
        ).annotate(
            total_revenue=Sum('amount_paid'),
            enrollment_count=Count('id'),
            avg_revenue_per_enrollment=Avg('amount_paid')
        ).order_by('-total_revenue')
        
        # Revenue by course type
        revenue_by_type = queryset.values('course__course_type').annotate(
            total_revenue=Sum('amount_paid'),
            enrollment_count=Count('id')
        ).order_by('-total_revenue')
        
        # Monthly revenue trend
        monthly_revenue = queryset.extra(
            select={'month': "TO_CHAR(enrolled_at, 'YYYY-MM')"}
        ).values('month').annotate(
            revenue=Sum('amount_paid'),
            enrollments=Count('id')
        ).order_by('month')

        
        return Response({
            'revenue_by_course': list(revenue_by_course),
            'revenue_by_type': list(revenue_by_type),
            'monthly_trend': list(monthly_revenue),
            'total_revenue': queryset.aggregate(total=Sum('amount_paid'))['total'] or 0,
            'total_enrollments': queryset.count()
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Revenue report error: {str(e)}")
        return Response(
            {'detail': 'Failed to generate revenue report.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAdmin])
def get_suspended_courses(request):
    """
    Instructor: Get their suspended courses that can be appealed
    GET /api/instructor/courses/suspended/
    """
    try:
        suspended_courses = Course.objects.filter(
            created_by=request.user,
            moderation_status='suspended',
            is_active=False
        ).select_related('moderated_by').prefetch_related('appeals')
        
        courses_data = []
        for course in suspended_courses:
            # Check if there's already a pending appeal
            pending_appeal = course.appeals.filter(status__in=['pending', 'under_review']).first()
            
            courses_data.append({
                'id': str(course.id),
                'title': course.title,
                'course_type': course.course_type,
                'suspended_at': course.moderated_at,
                'suspension_reason': course.moderation_reason,
                'suspended_by': course.moderated_by.full_name if course.moderated_by else 'System',
                'can_appeal': not pending_appeal,  # Can't appeal if already pending
                'pending_appeal': {
                    'id': str(pending_appeal.id),
                    'status': pending_appeal.status,
                    'submitted_at': pending_appeal.created_at,
                    'appeal_reason': pending_appeal.appeal_reason
                } if pending_appeal else None
            })
        
        return Response({
            'suspended_courses': courses_data,
            'total_suspended': len(courses_data),
            'can_appeal_count': sum(1 for c in courses_data if c['can_appeal'])
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Get suspended courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch suspended courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsAdmin])
def submit_course_appeal(request, course_id):
    """
    Instructor: Submit appeal for suspended course
    POST /api/instructor/courses/{course_id}/appeal/
    """
    try:
        course = Course.objects.get(
            id=course_id,
            created_by=request.user,
            moderation_status='suspended'
        )
        
        # Check if there's already a pending appeal
        if CourseAppeal.objects.filter(
            course=course,
            status__in=['pending', 'under_review']
        ).exists():
            return Response(
                {'detail': 'An appeal for this course is already pending review.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        appeal_reason = request.data.get('appeal_reason', '').strip()
        supporting_documents = request.data.get('supporting_documents', [])
        
        if not appeal_reason:
            return Response(
                {'detail': 'Appeal reason is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if len(appeal_reason) < 50:
            return Response(
                {'detail': 'Appeal reason must be at least 50 characters long.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Create the appeal
        appeal = CourseAppeal.objects.create(
            course=course,
            instructor=request.user,
            appeal_reason=appeal_reason,
            supporting_documents=supporting_documents,
            status='pending'
        )
        
        # Log the appeal
        logger.info(f"Course appeal submitted: Course {course.title} by {request.user.email}")
        
        # Send notification to super admins
        try:
            EmailService.send_course_appeal_notification(appeal)
        except Exception as email_error:
            logger.error(f"Failed to send appeal notification: {str(email_error)}")
        
        # Send confirmation to instructor
        try:
            EmailService.send_appeal_confirmation_to_instructor(appeal)
        except Exception as email_error:
            logger.error(f"Failed to send appeal confirmation: {str(email_error)}")
        
        return Response({
            'message': 'Course appeal submitted successfully.',
            'appeal_id': str(appeal.id),
            'course_title': course.title,
            'status': appeal.status,
            'submitted_at': appeal.created_at
        }, status=status.HTTP_201_CREATED)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Suspended course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Submit course appeal error: {str(e)}")
        return Response(
            {'detail': 'Failed to submit course appeal.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsAdmin])
def get_my_appeals(request):
    """
    Instructor: Get their course appeals history
    GET /api/instructor/appeals/
    """
    try:
        appeals = CourseAppeal.objects.filter(
            instructor=request.user
        ).select_related('course', 'reviewed_by').order_by('-created_at')
        
        appeals_data = []
        for appeal in appeals:
            appeals_data.append({
                'id': str(appeal.id),
                'course': {
                    'id': str(appeal.course.id),
                    'title': appeal.course.title,
                    'course_type': appeal.course.course_type
                },
                'appeal_reason': appeal.appeal_reason,
                'status': appeal.status,
                'submitted_at': appeal.created_at,
                'reviewed_by': appeal.reviewed_by.full_name if appeal.reviewed_by else None,
                'review_notes': appeal.review_notes,
                'reviewed_at': appeal.reviewed_at,
                'supporting_documents': appeal.supporting_documents
            })
        
        return Response({
            'appeals': appeals_data,
            'total_appeals': len(appeals_data),
            'pending_appeals': sum(1 for a in appeals_data if a['status'] in ['pending', 'under_review'])
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Get instructor appeals error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch appeals.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )