# courses/platform_admin_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from common.permissions import IsSuperAdmin
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum, F
from django.core.paginator import Paginator
from datetime import timedelta
from .models import Course, CourseEnrollment, UserCourseProgress, CourseReview, CourseAppeal
from users.models import User
from utils.auth import EmailService
from .instructor_views import AdminEmailService
from .serializers import CourseReviewSerializer
import logging

logger = logging.getLogger(__name__)


def format_duration(seconds):
    """Helper function to format duration in seconds to readable format"""
    if not seconds:
        return "0:00"
    
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remaining_seconds = seconds % 60
    
    if hours > 0:
        return f"{hours}:{minutes:02d}:{remaining_seconds:02d}"
    return f"{minutes}:{remaining_seconds:02d}"


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def platform_overview(request):
    """
    Super Admin: Get overall platform statistics
    GET /api/super-admin/overview/
    """
    try:
        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        course_creators = User.objects.filter(role='admin', is_active=True).count()
        new_users_30d = User.objects.filter(
            created_at__gte=timezone.now() - timedelta(days=30)
        ).count()
        
        # Course statistics
        total_courses = Course.objects.count()
        active_courses = Course.objects.filter(is_active=True).count()
        pending_courses = Course.objects.filter(is_active=False).count()
        
        # Revenue statistics
        total_revenue = CourseEnrollment.objects.filter(
            payment_status='completed'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        platform_commission_rate = 0.30  # 30% platform fee
        platform_revenue = float(total_revenue) * platform_commission_rate
        instructor_revenue = float(total_revenue) * (1 - platform_commission_rate)
        
        # Monthly revenue trend
        monthly_revenue = CourseEnrollment.objects.filter(
            payment_status='completed',
            enrolled_at__gte=timezone.now() - timedelta(days=365)
        ).extra(
            select={'month': "TO_CHAR(enrolled_at, 'YYYY-MM')"}
        ).values('month').annotate(
            revenue=Sum('amount_paid'),
            enrollments=Count('id')
        ).order_by('month')

        
        # Top performing instructors
        top_instructors = User.objects.filter(
            role='admin',
            is_active=True
        ).annotate(
            total_courses=Count('created_courses'),
            total_enrollments=Count('created_courses__enrollments'),
            total_revenue=Sum(
                'created_courses__enrollments__amount_paid',
                filter=Q(created_courses__enrollments__payment_status='completed')
            )
        ).filter(total_revenue__gt=0).order_by('-total_revenue')[:10]
        
        top_instructors_data = []
        for instructor in top_instructors:
            instructor_share = float(instructor.total_revenue or 0) * (1 - platform_commission_rate)
            platform_share = float(instructor.total_revenue or 0) * platform_commission_rate
            
            top_instructors_data.append({
                'id': str(instructor.id),
                'name': instructor.full_name,
                'email': instructor.email,
                'total_courses': instructor.total_courses,
                'total_enrollments': instructor.total_enrollments,
                'total_revenue': float(instructor.total_revenue or 0),
                'instructor_share': instructor_share,
                'platform_share': platform_share
            })
        
        return Response({
            'users': {
                'total_users': total_users,
                'active_users': active_users,
                'course_creators': course_creators,
                'new_users_30d': new_users_30d
            },
            'courses': {
                'total_courses': total_courses,
                'active_courses': active_courses,
                'pending_courses': pending_courses
            },
            'revenue': {
                'total_revenue': float(total_revenue),
                'platform_revenue': platform_revenue,
                'instructor_revenue': instructor_revenue,
                'commission_rate': platform_commission_rate,
                'monthly_trend': list(monthly_revenue)
            },
            'top_instructors': top_instructors_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Platform overview error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch platform overview.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def manage_instructors(request):
    """
    Super Admin: Manage course instructors
    GET /api/super-admin/instructors/
    """
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        search = request.GET.get('search', '')
        status_filter = request.GET.get('status', '')  # active, inactive, suspended
        
        # Build queryset
        queryset = User.objects.filter(role='admin').annotate(
            total_courses=Count('created_courses'),
            active_courses=Count('created_courses', filter=Q(created_courses__is_active=True)),
            total_revenue=Sum(
                'created_courses__enrollments__amount_paid',
                filter=Q(created_courses__enrollments__payment_status='completed')
            )
        )
        
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search) | Q(email__icontains=search)
            )
        
        if status_filter == 'active':
            queryset = queryset.filter(is_active=True)
        elif status_filter == 'inactive':
            queryset = queryset.filter(is_active=False)
        
        queryset = queryset.order_by('-created_at')
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        instructors_data = []
        for instructor in page_obj.object_list:
            instructors_data.append({
                'id': str(instructor.id),
                'full_name': instructor.full_name,
                'email': instructor.email,
                'is_active': instructor.is_active,
                'created_at': instructor.created_at,
                'last_login': instructor.last_login,
                'total_courses': instructor.total_courses,
                'active_courses': instructor.active_courses,
                'total_revenue': float(instructor.total_revenue or 0),
                'instructor_earnings': float(instructor.total_revenue or 0) * 0.7,  # 70% to instructor
                'platform_earnings': float(instructor.total_revenue or 0) * 0.3   # 30% to platform
            })
        
        return Response({
            'instructors': instructors_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_instructors': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Manage instructors error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch instructors.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def pending_courses(request):
    """
    Super Admin: Get all courses pending approval
    GET /api/super-admin/courses/pending/
    """
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        search = request.GET.get('search', '')
        
        # Get courses pending approval
        queryset = Course.objects.filter(
            moderation_status='pending'
        ).select_related('created_by').order_by('-created_at')
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(created_by__full_name__icontains=search) |
                Q(created_by__email__icontains=search)
            )
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        courses_data = []
        for course in page_obj.object_list:
            courses_data.append({
                'id': str(course.id),
                'title': course.title,
                'description': course.description[:200] + '...' if len(course.description) > 200 else course.description,
                'instructor_name': course.created_by.full_name,
                'instructor_email': course.created_by.email,
                'course_type': course.course_type,
                'price': float(course.price),
                'category': course.category,
                'difficulty_level': course.difficulty_level,
                'duration_minutes': course.duration_minutes,
                'video_url': course.get_video_url(),
                'thumbnail_url': course.thumbnail.url if course.thumbnail else None,
                'created_at': course.created_at,
                'moderation_status': course.moderation_status
            })
        
        return Response({
            'pending_courses': courses_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_courses': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Pending courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch pending courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def all_courses(request):
    """
    Super Admin: Get all courses with filtering
    GET /api/super-admin/courses/
    """
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        search = request.GET.get('search', '')
        status_filter = request.GET.get('status', '')  # pending, approved, rejected, suspended
        course_type = request.GET.get('course_type', '')  # free, paid, premium
        category = request.GET.get('category', '')
        
        # Build queryset
        queryset = Course.objects.select_related('created_by', 'moderated_by').order_by('-created_at')
        
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(created_by__full_name__icontains=search) |
                Q(created_by__email__icontains=search)
            )
        
        if status_filter:
            queryset = queryset.filter(moderation_status=status_filter)
        
        if course_type:
            queryset = queryset.filter(course_type=course_type)
            
        if category:
            queryset = queryset.filter(category=category)
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        courses_data = []
        for course in page_obj.object_list:
            courses_data.append({
                'id': str(course.id),
                'title': course.title,
                'instructor_name': course.created_by.full_name,
                'instructor_email': course.created_by.email,
                'course_type': course.course_type,
                'price': float(course.price),
                'effective_price': course.get_effective_price(),
                'category': course.category,
                'difficulty_level': course.difficulty_level,
                'is_active': course.is_active,
                'is_featured': course.is_featured,
                'moderation_status': course.moderation_status,
                'moderated_by': course.moderated_by.full_name if course.moderated_by else None,
                'moderated_at': course.moderated_at,
                'moderation_reason': course.moderation_reason,
                'total_enrollments': course.enrollments.count(),
                'total_revenue': float(course.get_total_revenue()),
                'completion_rate': course.get_completion_rate(),
                'average_rating': course.get_average_rating(),
                'review_count': course.get_review_count(),
                'created_at': course.created_at
            })
        
        return Response({
            'courses': courses_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_courses': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'summary': {
                'total_courses': Course.objects.count(),
                'pending_courses': Course.objects.filter(moderation_status='pending').count(),
                'approved_courses': Course.objects.filter(moderation_status='approved').count(),
                'rejected_courses': Course.objects.filter(moderation_status='rejected').count(),
                'suspended_courses': Course.objects.filter(moderation_status='suspended').count(),
                'active_courses': Course.objects.filter(is_active=True).count(),
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"All courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def get_complete_course_details(request, course_id):
    """
    Super Admin: Get Complete Course Details with All Related Data
    GET /api/admin/courses/{course_id}/complete/
    
    Returns:
    - Course basic info
    - All sections with lessons
    - All exams with questions and answers
    - Progress statistics
    - Enrollment data
    """
    try:
        # Get the course with related data
        course = Course.objects.select_related(
            'category', 'created_by', 'updated_by'
        ).prefetch_related(
            'sections__lessons__user_progress',
            'exams__questions__answers',
            'user_progress__user',
            'enrollments__user',
            'reviews'
        ).get(id=course_id)
        
        # Build the complete response
        response_data = {
            # Basic course information
            'course': {
                'id': str(course.id),
                'title': course.title,
                'description': course.description,
                'video_source': course.video_source,
                'video_url': course.get_video_url(),
                'thumbnail_url': course.thumbnail.url if course.thumbnail else None,
                'course_type': course.course_type,
                'price': float(course.price),
                'effective_price': course.get_effective_price(),
                'currency': course.currency,
                'has_discount': course.has_discount,
                'discount_percentage': course.discount_percentage,
                'is_discount_active': course.is_discount_active(),
                'difficulty_level': course.difficulty_level,
                'category': {
                    'id': str(course.category.id) if course.category else None,
                    'name': course.category.name if course.category else None,
                    'slug': course.category.slug if course.category else None,
                } if course.category else None,
                'requirements': course.requirements,
                'what_you_will_learn': course.what_you_will_learn,
                'is_active': course.is_active,
                'is_featured': course.is_featured,
                'created_at': course.created_at,
                'updated_at': course.updated_at,
                'created_by': {
                    'id': str(course.created_by.id) if course.created_by else None,
                    'name': course.created_by.full_name if course.created_by else None,
                } if course.created_by else None,
                
                # Course totals
                'total_sections': course.total_sections,
                'total_lessons': course.total_lessons,
                'total_duration_seconds': course.total_duration_seconds,
                'total_duration_display': format_duration(course.total_duration_seconds),
                
                # Course stats
                'total_enrollments': course.user_progress.count(),
                'completion_rate': course.get_completion_rate(),
                'average_progress': course.get_average_progress(),
                'total_revenue': float(course.get_total_revenue()),
                'average_rating': course.get_average_rating(),
                'review_count': course.get_review_count(),
            },
            
            # Sections with lessons
            'sections': [],
            
            # Exams with questions and answers
            'exams': [],
            
            # Enrollment statistics
            'enrollment_stats': {
                'total_enrolled': course.user_progress.count(),
                'active_enrollments': course.enrollments.filter(is_active=True).count(),
                'completed_courses': course.user_progress.filter(progress_percentage=100).count(),
                'average_progress': course.get_average_progress(),
                'recent_enrollments': course.user_progress.filter(
                    started_at__gte=timezone.now() - timedelta(days=30)
                ).count(),
            },
            
            # Recent activity
            'recent_activity': {
                'recent_enrollments': [],
                'recent_completions': [],
                'recent_reviews': [],
            }
        }
        
        # Get sections with lessons
        sections = course.sections.filter(is_active=True).order_by('order')
        for section in sections:
            section_data = {
                'id': str(section.id),
                'title': section.title,
                'description': section.description,
                'order': section.order,
                'is_active': section.is_active,
                'is_preview': section.is_preview,
                'required_previous_completion': section.required_previous_completion,
                'total_lessons': section.total_lessons,
                'total_duration_seconds': section.total_duration_seconds,
                'total_duration_display': format_duration(section.total_duration_seconds),
                'created_at': section.created_at,
                'created_by': {
                    'id': str(section.created_by.id) if section.created_by else None,
                    'name': section.created_by.full_name if section.created_by else None,
                } if section.created_by else None,
                'lessons': []
            }
            
            # Get lessons for this section
            lessons = section.lessons.filter(is_active=True).order_by('order')
            for lesson in lessons:
                lesson_data = {
                    'id': str(lesson.id),
                    'title': lesson.title,
                    'description': lesson.description,
                    'lesson_type': lesson.lesson_type,
                    'order': lesson.order,
                    'is_active': lesson.is_active,
                    'video_source': lesson.video_source,
                    'video_url': lesson.get_video_url(),
                    'thumbnail_url': lesson.thumbnail.url if lesson.thumbnail else None,
                    'text_content': lesson.text_content,
                    'attachments': lesson.attachments,
                    'duration_seconds': lesson.duration_seconds,
                    'duration_display': lesson.get_duration_display(),
                    'is_preview': lesson.is_preview,
                    'is_downloadable': lesson.is_downloadable,
                    'require_completion': lesson.require_completion,
                    'minimum_watch_percentage': lesson.minimum_watch_percentage,
                    'auto_play_next': lesson.auto_play_next,
                    'keywords': lesson.keywords,
                    'created_at': lesson.created_at,
                    'created_by': {
                        'id': str(lesson.created_by.id) if lesson.created_by else None,
                        'name': lesson.created_by.full_name if lesson.created_by else None,
                    } if lesson.created_by else None,
                    
                    # Lesson progress stats
                    'progress_stats': {
                        'total_views': lesson.user_progress.count(),
                        'completed_views': lesson.user_progress.filter(is_completed=True).count(),
                        'average_watch_percentage': lesson.user_progress.aggregate(
                            avg=Avg('watch_percentage')
                        )['avg'] or 0,
                        'average_completion_time': lesson.user_progress.filter(
                            is_completed=True
                        ).aggregate(avg=Avg('watch_time_seconds'))['avg'] or 0,
                    }
                }
                section_data['lessons'].append(lesson_data)
            
            response_data['sections'].append(section_data)
        
        # Get exams with questions and answers
        exams = course.exams.filter(is_active=True).order_by('exam_type', 'title')
        for exam in exams:
            exam_data = {
                'id': str(exam.id),
                'title': exam.title,
                'description': exam.description,
                'instructions': exam.instructions,
                'exam_type': exam.exam_type,
                'difficulty_level': exam.difficulty_level,
                'total_questions': exam.total_questions,
                'time_limit_minutes': exam.time_limit_minutes,
                'time_limit_display': exam.get_duration_display(),
                'passing_score': exam.passing_score,
                'max_attempts': exam.max_attempts,
                'shuffle_questions': exam.shuffle_questions,
                'shuffle_answers': exam.shuffle_answers,
                'show_results_immediately': exam.show_results_immediately,
                'show_correct_answers': exam.show_correct_answers,
                'allow_review': exam.allow_review,
                'required_course_progress': exam.required_course_progress,
                'is_active': exam.is_active,
                'is_published': exam.is_published,
                'is_available': exam.is_available(),
                'available_from': exam.available_from,
                'available_until': exam.available_until,
                'created_at': exam.created_at,
                'created_by': {
                    'id': str(exam.created_by.id) if exam.created_by else None,
                    'name': exam.created_by.full_name if exam.created_by else None,
                } if exam.created_by else None,
                
                # Exam statistics
                'stats': {
                    'total_attempts': exam.attempts.count(),
                    'completed_attempts': exam.attempts.filter(status='completed').count(),
                    'passed_attempts': exam.attempts.filter(status='completed', passed=True).count(),
                    'pass_rate': exam.get_pass_rate(),
                    'average_score': exam.get_average_score(),
                    'average_time_taken': exam.attempts.filter(
                        status='completed'
                    ).aggregate(avg=Avg('time_taken_minutes'))['avg'] or 0,
                },
                
                'questions': []
            }
            
            # Get questions with answers
            questions = exam.questions.filter(is_active=True).order_by('order')
            for question in questions:
                question_data = {
                    'id': str(question.id),
                    'question_text': question.question_text,
                    'question_type': question.question_type,
                    'points': question.points,
                    'order': question.order,
                    'is_active': question.is_active,
                    'explanation': question.explanation,
                    'image_url': question.image.url if question.image else None,
                    'difficulty_level': question.difficulty_level,
                    'tags': question.tags,
                    'created_at': question.created_at,
                    'answers': []
                }
                
                # Get answers for this question
                answers = question.answers.all().order_by('order')
                for answer in answers:
                    answer_data = {
                        'id': str(answer.id),
                        'answer_text': answer.answer_text,
                        'is_correct': answer.is_correct,
                        'order': answer.order,
                        'image_url': answer.image.url if answer.image else None,
                    }
                    question_data['answers'].append(answer_data)
                
                exam_data['questions'].append(question_data)
            
            response_data['exams'].append(exam_data)
        
        # Get recent activity data
        recent_enrollments = course.user_progress.select_related('user').order_by('-started_at')[:10]
        response_data['recent_activity']['recent_enrollments'] = [
            {
                'id': str(progress.id),
                'user': {
                    'id': str(progress.user.id),
                    'name': progress.user.full_name,
                    'email': progress.user.email,
                },
                'started_at': progress.started_at,
                'progress_percentage': progress.progress_percentage,
            }
            for progress in recent_enrollments
        ]
        
        recent_completions = course.user_progress.filter(
            progress_percentage=100
        ).select_related('user').order_by('-completed_at')[:10]
        response_data['recent_activity']['recent_completions'] = [
            {
                'id': str(progress.id),
                'user': {
                    'id': str(progress.user.id),
                    'name': progress.user.full_name,
                    'email': progress.user.email,
                },
                'completed_at': progress.completed_at,
            }
            for progress in recent_completions
        ]
        
        recent_reviews = course.reviews.filter(
            is_approved=True
        ).select_related('user').order_by('-created_at')[:10]
        response_data['recent_activity']['recent_reviews'] = [
            {
                'id': str(review.id),
                'user': {
                    'id': str(review.user.id),
                    'name': review.user.full_name,
                },
                'rating': review.rating,
                'review_text': review.review_text[:200] + '...' if len(review.review_text) > 200 else review.review_text,
                'created_at': review.created_at,
            }
            for review in recent_reviews
        ]
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    
    except Exception as e:
        logger.error(f"Get complete course details error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course details.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def course_detail_for_review(request, course_id):
    """
    Super Admin: Get detailed course info for review/moderation
    GET /api/super-admin/courses/{course_id}/
    """
    try:
        course = Course.objects.select_related(
            'created_by', 'moderated_by'
        ).prefetch_related(
            'enrollments', 'reviews', 'user_progress'
        ).get(id=course_id)
        
        course_data = {
            'id': str(course.id),
            'title': course.title,
            'description': course.description,
            'video_url': course.get_video_url(),
            'video_source': course.video_source,
            'thumbnail_url': course.thumbnail.url if course.thumbnail else None,
            'course_type': course.course_type,
            'price': float(course.price),
            'currency': course.currency,
            'effective_price': course.get_effective_price(),
            'has_discount': course.has_discount,
            'discount_percentage': course.discount_percentage,
            'category': course.category,
            'difficulty_level': course.difficulty_level,
            'duration_minutes': course.duration_minutes,
            'prerequisites': [str(p.id) for p in course.prerequisites.all()],
            'is_active': course.is_active,
            'is_featured': course.is_featured,
            
            # Moderation info
            'moderation_status': course.moderation_status,
            'moderated_by': course.moderated_by.full_name if course.moderated_by else None,
            'moderated_at': course.moderated_at,
            'moderation_reason': course.moderation_reason,
            
            # Instructor info
            'instructor': {
                'id': str(course.created_by.id),
                'name': course.created_by.full_name,
                'email': course.created_by.email,
                'is_active': course.created_by.is_active,
                'created_at': course.created_by.created_at,
                'total_courses': course.created_by.created_courses.count(),
                'total_revenue': float(course.created_by.created_courses.aggregate(
                    total=Sum('enrollments__amount_paid', 
                             filter=Q(enrollments__payment_status='completed'))
                )['total'] or 0)
            },
            
            # Course stats
            'stats': {
                'total_enrollments': course.enrollments.count(),
                'paid_enrollments': course.enrollments.filter(payment_status='completed').count(),
                'total_revenue': float(course.get_total_revenue()),
                'completion_rate': course.get_completion_rate(),
                'average_progress': course.get_average_progress(),
                'average_rating': course.get_average_rating(),
                'review_count': course.get_review_count(),
            },
            
            'created_at': course.created_at,
            'updated_at': course.updated_at
        }
        
        return Response(course_data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Course detail error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course details.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def moderate_course(request, course_id):
    """
    Super Admin: Approve/Reject/Suspend courses
    POST /api/super-admin/courses/{course_id}/moderate/
    """
    try:
        course = Course.objects.get(id=course_id)
        action = request.data.get('action')  # approve, reject, suspend
        reason = request.data.get('reason', '')
        
        if action not in ['approve', 'reject', 'suspend']:
            return Response(
                {'detail': 'Invalid action. Use: approve, reject, suspend'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            if action == 'approve':
                course.is_active = True
                course.moderation_status = 'approved'
                message = 'Course approved successfully.'
                
            elif action == 'reject':
                course.is_active = False
                course.moderation_status = 'rejected'
                message = 'Course rejected.'
                
            elif action == 'suspend':
                course.is_active = False
                course.moderation_status = 'suspended'
                message = 'Course suspended.'
            
            course.moderation_reason = reason
            course.moderated_by = request.user
            course.moderated_at = timezone.now()
            course.save()
            
            # Send email notification to instructor
            # EmailService.send_course_moderation_notification(course, action, reason)

            # Send notification to course creator about moderation decision
            try:
                AdminEmailService.notify_course_creator_decision(course, action, reason)
                logger.info(f"Moderation notification sent to instructor: {course.created_by.email}")
            except Exception as email_error:
                logger.error(f"Failed to send moderation notification: {str(email_error)}")
                # Continue execution even if email fails
            
            logger.info(f"Course {action}d: {course.title} by super admin {request.user.email}")
            
            return Response({
                'message': message,
                'course_id': str(course.id),
                'action': action,
                'reason': reason,
                'course_status': {
                    'is_active': course.is_active,
                    'moderation_status': course.moderation_status,
                    'moderated_at': course.moderated_at
                }
            }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Course moderation error: {str(e)}")
        return Response(
            {'detail': 'Failed to moderate course.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def bulk_course_actions(request):
    """
    Super Admin: Bulk actions on courses
    POST /api/super-admin/courses/bulk-actions/
    Body: {
        "action": "approve|reject|suspend|activate|deactivate",
        "course_ids": ["uuid1", "uuid2", ...],
        "reason": "optional reason"
    }
    """
    try:
        action = request.data.get('action')
        course_ids = request.data.get('course_ids', [])
        reason = request.data.get('reason', '')
        
        if action not in ['approve', 'reject', 'suspend', 'activate', 'deactivate']:
            return Response(
                {'detail': 'Invalid action.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not course_ids:
            return Response(
                {'detail': 'No courses selected.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get courses
        courses = Course.objects.filter(id__in=course_ids)
        
        if not courses.exists():
            return Response(
                {'detail': 'No valid courses found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        updated_count = 0
        
        with transaction.atomic():
            for course in courses:
                if action == 'approve':
                    course.is_active = True
                    course.moderation_status = 'approved'
                elif action == 'reject':
                    course.is_active = False
                    course.moderation_status = 'rejected'
                elif action == 'suspend':
                    course.is_active = False
                    course.moderation_status = 'suspended'
                elif action == 'activate':
                    course.is_active = True
                elif action == 'deactivate':
                    course.is_active = False
                
                course.moderation_reason = reason
                course.moderated_by = request.user
                course.moderated_at = timezone.now()
                course.save()
                
                # Send notification to instructor
                try:
                    AdminEmailService.notify_course_creator_decision(course, action, reason)
                except Exception as e:
                    logger.error(f"Failed to send bulk notification: {str(e)}")
                
                updated_count += 1
        
        return Response({
            'message': f'{updated_count} courses {action}d successfully.',
            'updated_count': updated_count,
            'action': action
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Bulk course actions error: {str(e)}")
        return Response(
            {'detail': 'Failed to perform bulk action.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def course_moderation_stats(request):
    """
    Super Admin: Get course moderation statistics
    GET /api/super-admin/courses/moderation-stats/
    """
    try:
        # Overall stats
        total_courses = Course.objects.count()
        pending_courses = Course.objects.filter(moderation_status='pending').count()
        approved_courses = Course.objects.filter(moderation_status='approved').count()
        rejected_courses = Course.objects.filter(moderation_status='rejected').count()
        suspended_courses = Course.objects.filter(moderation_status='suspended').count()
        
        # Recent activity (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_submissions = Course.objects.filter(created_at__gte=thirty_days_ago).count()
        recent_approvals = Course.objects.filter(
            moderation_status='approved',
            moderated_at__gte=thirty_days_ago
        ).count()
        recent_rejections = Course.objects.filter(
            moderation_status='rejected',
            moderated_at__gte=thirty_days_ago
        ).count()
        
        # By category
        courses_by_category = Course.objects.values('category').annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(moderation_status='pending')),
            approved=Count('id', filter=Q(moderation_status='approved'))
        ).order_by('-total')
        
        # By course type
        courses_by_type = Course.objects.values('course_type').annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(moderation_status='pending')),
            approved=Count('id', filter=Q(moderation_status='approved'))
        ).order_by('-total')
        
        return Response({
            'overall_stats': {
                'total_courses': total_courses,
                'pending_courses': pending_courses,
                'approved_courses': approved_courses,
                'rejected_courses': rejected_courses,
                'suspended_courses': suspended_courses,
                'approval_rate': round((approved_courses / total_courses * 100), 2) if total_courses > 0 else 0
            },
            'recent_activity': {
                'recent_submissions': recent_submissions,
                'recent_approvals': recent_approvals,
                'recent_rejections': recent_rejections
            },
            'courses_by_category': list(courses_by_category),
            'courses_by_type': list(courses_by_type)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Course moderation stats error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch moderation statistics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    
@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def pending_reviews(request):
    """
    Admin: Get pending course reviews for approval
    GET /api/super-admin/reviews/pending/
    """
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        reviews = CourseReview.objects.filter(
            is_approved=False
        ).select_related('user', 'course').order_by('-created_at')
        
        paginator = Paginator(reviews, per_page)
        page_obj = paginator.get_page(page)
        
        serializer = CourseReviewSerializer(page_obj.object_list, many=True)
        
        return Response({
            'pending_reviews': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_reviews': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Pending reviews error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch pending reviews.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    
@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def approve_review(request, review_id):
    """
    Super Admin: Approve or reject a course review
    POST /api/super-admin/reviews/{review_id}/approve/
    """
    try:
        review = CourseReview.objects.select_related('user', 'course').get(id=review_id)
        
        action = request.data.get('action')  # 'approve' or 'reject'
        admin_notes = request.data.get('admin_notes', '')
        
        if action not in ['approve', 'reject']:
            return Response(
                {'detail': 'Action must be either "approve" or "reject"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            if action == 'approve':
                review.is_approved = True
                review.approved_by = request.user
                review.approved_at = timezone.now()
                review.admin_notes = admin_notes
                review.save()
                
                message = 'Review approved successfully.'
                
                # Send notification to user
                try:
                    EmailService.send_review_approved_notification(review.user, review)
                except Exception as email_error:
                    logger.error(f"Failed to send review approval notification: {str(email_error)}")
                
            else:  # reject
                # Store rejection reason
                review.admin_notes = admin_notes
                review.is_approved = False
                review.approved_by = request.user
                review.approved_at = timezone.now()
                review.save()
                
                # Or delete the review entirely (uncomment next line if preferred)
                # review.delete()
                
                message = 'Review rejected.'
                
                # Send notification to user about rejection
                try:
                    EmailService.send_review_rejected_notification(review.user, review, admin_notes)
                except Exception as email_error:
                    logger.error(f"Failed to send review rejection notification: {str(email_error)}")
        
        logger.info(f"Review {action}d: {review.course.title} review by {review.user.email} - Super admin: {request.user.email}")
        
        return Response({
            'message': message,
            'review_id': str(review.id),
            'action': action,
            'admin_notes': admin_notes
        }, status=status.HTTP_200_OK)
    
    except CourseReview.DoesNotExist:
        return Response(
            {'detail': 'Review not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Approve review error: {str(e)}")
        return Response(
            {'detail': 'Failed to process review approval.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def all_reviews(request):
    """
    Super Admin: Get all course reviews with filtering
    GET /api/super-admin/reviews/
    """
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        status_filter = request.GET.get('status', '')  # approved, pending, rejected
        rating_filter = request.GET.get('rating', '')
        course_id = request.GET.get('course_id', '')
        
        # Build queryset
        queryset = CourseReview.objects.select_related('user', 'course', 'approved_by').order_by('-created_at')
        
        if status_filter == 'approved':
            queryset = queryset.filter(is_approved=True)
        elif status_filter == 'pending':
            queryset = queryset.filter(is_approved=False, approved_at__isnull=True)
        elif status_filter == 'rejected':
            queryset = queryset.filter(is_approved=False, approved_at__isnull=False)
        
        if rating_filter:
            queryset = queryset.filter(rating=int(rating_filter))
        
        if course_id:
            queryset = queryset.filter(course_id=course_id)
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        reviews_data = []
        for review in page_obj.object_list:
            reviews_data.append({
                'id': str(review.id),
                'course_title': review.course.title,
                'course_id': str(review.course.id),
                'instructor_name': review.course.created_by.full_name,
                'student_name': review.user.full_name,
                'student_email': review.user.email,
                'rating': review.rating,
                'review_text': review.review_text,
                'is_approved': review.is_approved,
                'approved_by': review.approved_by.full_name if review.approved_by else None,
                'approved_at': review.approved_at,
                'admin_notes': review.admin_notes,
                'created_at': review.created_at
            })
        
        return Response({
            'reviews': reviews_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_reviews': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'summary': {
                'total_reviews': queryset.count(),
                'approved_reviews': queryset.filter(is_approved=True).count(),
                'pending_reviews': queryset.filter(is_approved=False, approved_at__isnull=True).count(),
                'rejected_reviews': queryset.filter(is_approved=False, approved_at__isnull=False).count()
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"All reviews error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch reviews.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def manage_instructor_status(request, instructor_id):
    """
    Super Admin: Activate/Deactivate/Suspend instructors
    POST /api/super-admin/instructors/{instructor_id}/manage/
    """
    try:
        instructor = User.objects.get(id=instructor_id, role='admin')
        action = request.data.get('action')  # activate, deactivate, suspend
        reason = request.data.get('reason', '')
        restore_courses = request.data.get('restore_courses', True)  # For activation
        
        if action not in ['activate', 'deactivate', 'suspend']:
            return Response(
                {'detail': 'Invalid action. Use: activate, deactivate, suspend'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Store previous instructor status for comparison
            was_active = instructor.is_active
            
            if action == 'activate':
                instructor.is_active = True
                instructor.moderation_status = 'approved'
                message = 'Instructor activated successfully.'

                # Count courses for notification context
                total_courses = Course.objects.filter(created_by=instructor).count()
                suspended_courses_count = Course.objects.filter(
                    created_by=instructor, 
                    moderation_status='suspended'
                ).count()

                # Reactivate instructor's approved courses
                if restore_courses:
                    reactivated_courses = Course.objects.filter(
                        created_by=instructor,
                        moderation_status='approved'
                    ).update(
                        is_active=True,
                        moderation_reason=f'Auto-reactivated due to instructor activation by {request.user.full_name}',
                        moderated_by=request.user,
                        moderated_at=timezone.now()
                    )

                    message += f' {reactivated_courses} approved courses reactivated.'

                    # Prepare additional context for activation email
                    additional_context = {
                        'reactivated_courses_count': reactivated_courses,
                        'suspended_courses_count': suspended_courses_count,
                        'total_courses': total_courses
                    }
                else:
                    additional_context = {
                        'reactivated_courses_count': 0,
                        'suspended_courses_count': suspended_courses_count,
                        'total_courses': total_courses
                    }
                
            elif action == 'deactivate':
                instructor.is_active = False
                instructor.moderation_status = 'suspended'  # Mark as suspended in moderation
                message = 'Instructor deactivated.'
                
                # Deactivate all instructor's courses but keep their approval status
                deactivated_courses = Course.objects.filter(
                    created_by=instructor,
                    is_active=True
                ).update(
                    is_active=False,
                    moderation_reason=f'Auto-deactivated due to instructor deactivation: {reason}',
                    moderated_by=request.user,
                    moderated_at=timezone.now()
                    # Note: We don't change moderation_status, so we remember if they were approved
                )
                message += f' {deactivated_courses} courses deactivated.'
                
            elif action == 'suspend':
                instructor.is_active = False
                instructor.moderation_status = 'suspended'
                message = 'Instructor suspended.'

                # Suspend all instructor's courses
                suspended_courses = Course.objects.filter(
                    created_by=instructor
                ).update(
                    is_active=False,
                    moderation_status='suspended',
                    moderation_reason=f'Auto-suspended due to instructor suspension: {reason}',
                    moderated_by=request.user,
                    moderated_at=timezone.now()
                )
                message += f' {suspended_courses} courses suspended.'

                # ADD THIS BLOCK HERE:
                try:
                    suspended_course_list = Course.objects.filter(
                        created_by=instructor,
                        moderation_status='suspended'
                    )
                    for course in suspended_course_list:
                        EmailService.send_course_suspension_to_students(course, reason)
                except Exception as email_error:
                    logger.error(f"Failed to send suspension notification to students: {str(email_error)}")
            
            # Update instructor record
            instructor.save()
            
            # Log the action
            logger.info(f"Instructor {action}d: {instructor.email} by super admin {request.user.email}. Reason: {reason}")

            if action in ['activate', 'deactivate', 'suspend']:
                # Get affected courses for student notifications
                if action == 'activate' and restore_courses:
                    affected_courses = Course.objects.filter(
                        created_by=instructor,
                        moderation_status='approved',
                        is_active=True
                    )
                elif action in ['deactivate', 'suspend']:
                    affected_courses = Course.objects.filter(
                        created_by=instructor,
                        is_active=False
                    )
                else:
                    affected_courses = Course.objects.none()

                # Send notifications to affected students
                if affected_courses.exists():
                    try:
                        EmailService.send_instructor_status_change_to_students(
                            instructor, action, affected_courses
                        )
                    except Exception as email_error:
                        logger.error(f"Failed to send student notifications: {str(email_error)}")
            
            # Send notification email to instructor
            try:
                # Pass additional context for activation emails
                if action == 'activate':
                    EmailService.send_instructor_status_notification(
                        instructor, action, reason, additional_context
                    )
                else:
                    EmailService.send_instructor_status_notification(instructor, action, reason)
            except Exception as email_error:
                logger.error(f"Failed to send instructor status notification: {str(email_error)}")

            
            # If instructor was reactivated, also send course reactivation notifications
            if action == 'activate' and restore_courses and not was_active:
                try:
                    # Get reactivated courses for notification
                    reactivated_course_list = Course.objects.filter(
                        created_by=instructor,
                        is_active=True,
                        moderation_status='approved'
                    )
                    
                    # Send notification about course reactivations
                    EmailService.send_bulk_course_reactivation_notification(
                        instructor, reactivated_course_list, reason
                    )
                except Exception as email_error:
                    logger.error(f"Failed to send course reactivation notification: {str(email_error)}")
            
            return Response({
                'message': message,
                'instructor_id': str(instructor.id),
                'instructor_name': instructor.full_name,
                'action': action,
                'reason': reason,
                'instructor_status': {
                    'is_active': instructor.is_active,
                    'moderation_status': instructor.moderation_status
                }
            }, status=status.HTTP_200_OK)
    
    except User.DoesNotExist:
        return Response(
            {'detail': 'Instructor not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Instructor management error: {str(e)}")
        return Response(
            {'detail': 'Failed to manage instructor status.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def instructor_course_impact_preview(request, instructor_id):
    """
    Super Admin: Preview what courses will be affected by instructor status change
    GET /api/super-admin/instructors/{instructor_id}/course-impact/
    """
    try:
        instructor = User.objects.get(id=instructor_id, role='admin')
        action = request.GET.get('action', 'deactivate')  # What action are we previewing
        
        # Get instructor's courses with their current status
        courses = Course.objects.filter(created_by=instructor).values(
            'id', 'title', 'is_active', 'moderation_status', 'course_type',
            'price', 'created_at'
        ).annotate(
            total_enrollments=Count('enrollments'),
            active_enrollments=Count('enrollments', filter=Q(enrollments__is_active=True))
        )
        
        courses_data = []
        for course in courses:
            # Predict what will happen to this course
            if action == 'activate':
                new_status = 'Will be reactivated' if course['moderation_status'] == 'approved' else 'Will remain inactive (needs review)'
                new_active = course['moderation_status'] == 'approved'
            elif action == 'deactivate':
                new_status = 'Will be deactivated (but keeps approval status)'
                new_active = False
            elif action == 'suspend':
                new_status = 'Will be suspended'
                new_active = False
            else:
                new_status = 'No change'
                new_active = course['is_active']
            
            courses_data.append({
                'id': str(course['id']),
                'title': course['title'],
                'current_status': {
                    'is_active': course['is_active'],
                    'moderation_status': course['moderation_status']
                },
                'predicted_status': {
                    'is_active': new_active,
                    'status_description': new_status
                },
                'course_type': course['course_type'],
                'price': float(course['price']),
                'total_enrollments': course['total_enrollments'],
                'active_enrollments': course['active_enrollments'],
                'created_at': course['created_at']
            })
        
        # Summary of impact
        total_courses = len(courses_data)
        currently_active = sum(1 for c in courses_data if c['current_status']['is_active'])
        will_be_affected = sum(1 for c in courses_data if c['current_status']['is_active'] != c['predicted_status']['is_active'])
        total_active_enrollments = sum(c['active_enrollments'] for c in courses_data)
        
        return Response({
            'instructor': {
                'id': str(instructor.id),
                'name': instructor.full_name,
                'email': instructor.email,
                'current_status': instructor.is_active
            },
            'impact_summary': {
                'total_courses': total_courses,
                'currently_active_courses': currently_active,
                'courses_will_be_affected': will_be_affected,
                'total_active_enrollments_affected': total_active_enrollments,
                'action': action
            },
            'courses': courses_data
        }, status=status.HTTP_200_OK)
    
    except User.DoesNotExist:
        return Response(
            {'detail': 'Instructor not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Course impact preview error: {str(e)}")
        return Response(
            {'detail': 'Failed to preview course impact.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def bulk_instructor_actions(request):
    """
    Super Admin: Bulk actions on multiple instructors
    POST /api/super-admin/instructors/bulk-actions/
    """
    try:
        action = request.data.get('action')  # activate, deactivate, suspend
        instructor_ids = request.data.get('instructor_ids', [])
        reason = request.data.get('reason', '')
        restore_courses = request.data.get('restore_courses', True)
        
        if action not in ['activate', 'deactivate', 'suspend']:
            return Response(
                {'detail': 'Invalid action.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not instructor_ids:
            return Response(
                {'detail': 'No instructors selected.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get instructors
        instructors = User.objects.filter(id__in=instructor_ids, role='admin')
        
        if not instructors.exists():
            return Response(
                {'detail': 'No valid instructors found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        results = []
        total_courses_affected = 0
        
        with transaction.atomic():
            for instructor in instructors:
                try:
                    courses_affected = 0
                    
                    if action == 'activate':
                        instructor.is_active = True
                        instructor.moderation_status = 'approved'
                        
                        if restore_courses:
                            courses_affected = Course.objects.filter(
                                created_by=instructor,
                                moderation_status='approved'
                            ).update(
                                is_active=True,
                                moderation_reason=f'Bulk reactivation: {reason}',
                                moderated_by=request.user,
                                moderated_at=timezone.now()
                            )
                    
                    elif action == 'deactivate':
                        instructor.is_active = False
                        instructor.moderation_status = 'suspended'
                        
                        courses_affected = Course.objects.filter(
                            created_by=instructor,
                            is_active=True
                        ).update(
                            is_active=False,
                            moderation_reason=f'Bulk deactivation: {reason}',
                            moderated_by=request.user,
                            moderated_at=timezone.now()
                        )
                    
                    elif action == 'suspend':
                        instructor.is_active = False
                        instructor.moderation_status = 'suspended'
                        
                        courses_affected = Course.objects.filter(
                            created_by=instructor
                        ).update(
                            is_active=False,
                            moderation_status='suspended',
                            moderation_reason=f'Bulk suspension: {reason}',
                            moderated_by=request.user,
                            moderated_at=timezone.now()
                        )
                    
                    instructor.save()
                    total_courses_affected += courses_affected
                    
                    results.append({
                        'instructor_id': str(instructor.id),
                        'instructor_name': instructor.full_name,
                        'instructor_email': instructor.email,
                        'success': True,
                        'courses_affected': courses_affected
                    })
                    
                    # Send notification
                    try:
                        EmailService.send_instructor_status_notification(instructor, action, reason)
                    except Exception:
                        pass  # Don't fail the whole operation for email issues
                        
                except Exception as e:
                    results.append({
                        'instructor_id': str(instructor.id),
                        'instructor_name': instructor.full_name,
                        'success': False,
                        'error': str(e)
                    })
        
        successful_count = sum(1 for r in results if r['success'])
        
        return Response({
            'message': f'Bulk {action} completed. {successful_count} instructors processed.',
            'total_instructors_processed': successful_count,
            'total_courses_affected': total_courses_affected,
            'action': action,
            'results': results
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Bulk instructor actions error: {str(e)}")
        return Response(
            {'detail': 'Failed to perform bulk action.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def revenue_analytics(request):
    """
    Super Admin: Detailed revenue analytics and payouts
    GET /api/super-admin/revenue-analytics/
    """
    try:
        # Date range
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)
        
        # Revenue breakdown
        total_revenue = CourseEnrollment.objects.filter(
            payment_status='completed'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        recent_revenue = CourseEnrollment.objects.filter(
            payment_status='completed',
            enrolled_at__gte=start_date
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        platform_commission = 0.30
        platform_total = float(total_revenue) * platform_commission
        instructor_total = float(total_revenue) * (1 - platform_commission)
        
        # Revenue by course type
        revenue_by_type = CourseEnrollment.objects.filter(
            payment_status='completed'
        ).values('course__course_type').annotate(
            total_revenue=Sum('amount_paid'),
            enrollments=Count('id')
        ).order_by('-total_revenue')
        
        # Top earning courses
        top_courses = Course.objects.annotate(
            total_revenue=Sum(
                'enrollments__amount_paid',
                filter=Q(enrollments__payment_status='completed')
            ),
            total_enrollments=Count(
                'enrollments',
                filter=Q(enrollments__payment_status='completed')
            )
        ).filter(total_revenue__gt=0).order_by('-total_revenue')[:20]
        
        top_courses_data = []
        for course in top_courses:
            course_revenue = float(course.total_revenue or 0)
            platform_share = course_revenue * platform_commission
            instructor_share = course_revenue * (1 - platform_commission)
            
            top_courses_data.append({
                'id': str(course.id),
                'title': course.title,
                'instructor': course.created_by.full_name,
                'instructor_email': course.created_by.email,
                'total_revenue': course_revenue,
                'total_enrollments': course.total_enrollments,
                'platform_share': platform_share,
                'instructor_share': instructor_share
            })
        
        return Response({
            'summary': {
                'total_revenue': float(total_revenue),
                'recent_revenue': float(recent_revenue),
                'platform_total_earnings': platform_total,
                'instructor_total_earnings': instructor_total,
                'commission_rate': platform_commission
            },
            'revenue_by_type': list(revenue_by_type),
            'top_earning_courses': top_courses_data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Revenue analytics error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch revenue analytics.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
@api_view(['GET'])
@permission_classes([IsSuperAdmin])
def get_pending_appeals(request):
    """
    Super Admin: Get all pending course appeals
    GET /api/super-admin/appeals/pending/
    """
    try:
        status_filter = request.GET.get('status', 'pending')
        instructor_id = request.GET.get('instructor_id')
        
        appeals = CourseAppeal.objects.select_related(
            'course', 'instructor', 'reviewed_by'
        ).filter(status=status_filter)
        
        if instructor_id:
            appeals = appeals.filter(instructor_id=instructor_id)
        
        appeals = appeals.order_by('-created_at')
        
        appeals_data = []
        for appeal in appeals:
            appeals_data.append({
                'id': str(appeal.id),
                'course': {
                    'id': str(appeal.course.id),
                    'title': appeal.course.title,
                    'course_type': appeal.course.course_type,
                    'suspension_reason': appeal.course.moderation_reason,
                    'suspended_at': appeal.course.moderated_at
                },
                'instructor': {
                    'id': str(appeal.instructor.id),
                    'name': appeal.instructor.full_name,
                    'email': appeal.instructor.email
                },
                'appeal_reason': appeal.appeal_reason,
                'supporting_documents': appeal.supporting_documents,
                'status': appeal.status,
                'submitted_at': appeal.created_at,
                'reviewed_by': appeal.reviewed_by.full_name if appeal.reviewed_by else None,
                'review_notes': appeal.review_notes,
                'reviewed_at': appeal.reviewed_at
            })
        
        return Response({
            'appeals': appeals_data,
            'total_appeals': len(appeals_data),
            'filter_applied': status_filter
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Get pending appeals error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch pending appeals.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def review_course_appeal(request, appeal_id):
    """
    Super Admin: Review and decide on course appeal
    POST /api/super-admin/appeals/{appeal_id}/review/
    """
    try:
        appeal = CourseAppeal.objects.select_related('course', 'instructor').get(
            id=appeal_id,
            status__in=['pending', 'under_review']
        )
        
        decision = request.data.get('decision')  # approved, rejected
        review_notes = request.data.get('review_notes', '').strip()
        
        if decision not in ['approved', 'rejected']:
            return Response(
                {'detail': 'Invalid decision. Use: approved, rejected'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not review_notes:
            return Response(
                {'detail': 'Review notes are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        with transaction.atomic():
            # Update appeal
            appeal.status = decision
            appeal.review_notes = review_notes
            appeal.reviewed_by = request.user
            appeal.reviewed_at = timezone.now()
            appeal.save()
            
            # If approved, reactivate the course
            if decision == 'approved':
                appeal.course.is_active = True
                appeal.course.moderation_status = 'approved'
                appeal.course.moderation_reason = f'Appeal approved: {review_notes}'
                appeal.course.moderated_by = request.user
                appeal.course.moderated_at = timezone.now()
                appeal.course.save()
                
                message = f'Course appeal approved and course reactivated.'
            else:
                message = f'Course appeal rejected.'
            
            # Log the decision
            logger.info(f"Appeal {decision}: Course {appeal.course.title} appeal by {request.user.email}")
            
            # Send notification to instructor
            try:
                EmailService.send_appeal_decision_notification(appeal, decision)
            except Exception as email_error:
                logger.error(f"Failed to send appeal decision notification: {str(email_error)}")
            
            # If approved, also notify enrolled students
            if decision == 'approved':
                try:
                    EmailService.send_course_reactivation_to_students(appeal.course)
                except Exception as email_error:
                    logger.error(f"Failed to send student notifications: {str(email_error)}")
        
        return Response({
            'message': message,
            'appeal_id': str(appeal.id),
            'course_title': appeal.course.title,
            'decision': decision,
            'instructor_name': appeal.instructor.full_name,
            'course_status': {
                'is_active': appeal.course.is_active,
                'moderation_status': appeal.course.moderation_status
            }
        }, status=status.HTTP_200_OK)
    
    except CourseAppeal.DoesNotExist:
        return Response(
            {'detail': 'Pending appeal not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Review appeal error: {str(e)}")
        return Response(
            {'detail': 'Failed to review appeal.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

@api_view(['POST'])
@permission_classes([IsSuperAdmin])
def bulk_course_status_update(request):
    """
    Super Admin: Bulk approve/reject suspended courses or appeals
    POST /api/super-admin/courses/bulk-status-update/
    """
    try:
        action = request.data.get('action')  # approve_courses, reject_courses, approve_appeals, reject_appeals
        item_ids = request.data.get('item_ids', [])  # Course IDs or Appeal IDs
        reason = request.data.get('reason', '').strip()
        
        valid_actions = ['approve_courses', 'reject_courses', 'approve_appeals', 'reject_appeals']
        if action not in valid_actions:
            return Response(
                {'detail': f'Invalid action. Use: {", ".join(valid_actions)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not item_ids:
            return Response(
                {'detail': 'No items selected.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not reason:
            return Response(
                {'detail': 'Reason is required for bulk actions.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        results = []
        total_affected = 0
        
        with transaction.atomic():
            if action in ['approve_courses', 'reject_courses']:
                # Bulk course status update
                courses = Course.objects.filter(
                    id__in=item_ids,
                    moderation_status='suspended'
                ).select_related('created_by')
                
                for course in courses:
                    try:
                        if action == 'approve_courses':
                            course.is_active = True
                            course.moderation_status = 'approved'
                            course.moderation_reason = f'Bulk approval: {reason}'
                        else:  # reject_courses
                            course.is_active = False
                            course.moderation_status = 'rejected'
                            course.moderation_reason = f'Bulk rejection: {reason}'
                        
                        course.moderated_by = request.user
                        course.moderated_at = timezone.now()
                        course.save()
                        
                        total_affected += 1
                        
                        results.append({
                            'item_id': str(course.id),
                            'item_title': course.title,
                            'instructor_name': course.created_by.full_name,
                            'success': True,
                            'new_status': course.moderation_status
                        })
                        
                        # Send notification to instructor
                        try:
                            EmailService.send_course_status_notification(
                                course, action.replace('_courses', ''), reason
                            )
                        except Exception:
                            pass  # Don't fail bulk operation for email issues
                        
                        # If approved, notify students
                        if action == 'approve_courses':
                            try:
                                EmailService.send_course_reactivation_to_students(course)
                            except Exception:
                                pass
                                
                    except Exception as e:
                        results.append({
                            'item_id': str(course.id),
                            'item_title': course.title,
                            'success': False,
                            'error': str(e)
                        })
            
            else:  # approve_appeals, reject_appeals
                # Bulk appeal processing
                appeals = CourseAppeal.objects.select_related(
                    'course', 'instructor'
                ).filter(
                    id__in=item_ids,
                    status__in=['pending', 'under_review']
                )
                
                for appeal in appeals:
                    try:
                        decision = 'approved' if action == 'approve_appeals' else 'rejected'
                        
                        appeal.status = decision
                        appeal.review_notes = f'Bulk {decision}: {reason}'
                        appeal.reviewed_by = request.user
                        appeal.reviewed_at = timezone.now()
                        appeal.save()
                        
                        # If appeal approved, reactivate course
                        if decision == 'approved':
                            appeal.course.is_active = True
                            appeal.course.moderation_status = 'approved'
                            appeal.course.moderation_reason = f'Appeal approved: {reason}'
                            appeal.course.moderated_by = request.user
                            appeal.course.moderated_at = timezone.now()
                            appeal.course.save()
                        
                        total_affected += 1
                        
                        results.append({
                            'item_id': str(appeal.id),
                            'item_title': f"Appeal for {appeal.course.title}",
                            'instructor_name': appeal.instructor.full_name,
                            'success': True,
                            'decision': decision
                        })
                        
                        # Send notifications
                        try:
                            EmailService.send_appeal_decision_notification(appeal, decision)
                            if decision == 'approved':
                                EmailService.send_course_reactivation_to_students(appeal.course)
                        except Exception:
                            pass
                            
                    except Exception as e:
                        results.append({
                            'item_id': str(appeal.id),
                            'item_title': f"Appeal for {appeal.course.title}",
                            'success': False,
                            'error': str(e)
                        })
        
        successful_count = sum(1 for r in results if r['success'])
        
        return Response({
            'message': f'Bulk {action} completed. {successful_count} items processed.',
            'total_processed': successful_count,
            'total_selected': len(item_ids),
            'action': action,
            'results': results
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Bulk course status update error: {str(e)}")
        return Response(
            {'detail': 'Failed to perform bulk action.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )