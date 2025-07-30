# courses/student_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.db import transaction
from django.utils import timezone
from django.db.models import Count, Avg, Q, Sum, F
from django.core.paginator import Paginator
from django.conf import settings
from django.core.cache import cache
from .models import (
    Course, UserCourseProgress, CourseEnrollment, CourseCategory, 
    CourseReview, CourseExam, ExamQuestion, ExamAnswer, UserExamAttempt, 
    UserExamAnswer, ExamCertificate, CourseSection, CourseLesson, UserLessonProgress
)
from .serializers import (
    CourseSerializer, UserCourseProgressSerializer, UserCourseProgressUpdateSerializer,
    CourseEnrollmentSerializer, CourseCategorySerializer, CourseReviewSerializer,
    CourseExamSerializer, ExamQuestionSerializer, UserExamAttemptSerializer
)
from users.models import User
from utils.auth import EmailService
from utils.admin_email_service import AdminEmailService
# Import payment services
from payments.services import PaymentServiceFactory
from payments.models import Payment
import logging
import random

logger = logging.getLogger(__name__)


# Create your views here.

# COURSE LISTING AND DISCOVERY
@api_view(['GET'])
@permission_classes([AllowAny])
def list_courses(request):
    """
    List all active courses with filtering and search
    GET /api/courses/
    """
    try:
        # Cache key for course listing
        cache_key = f"courses_list_{request.GET.urlencode()}"
        cached_data = cache.get(cache_key)
        
        if cached_data and not request.user.is_authenticated:
            return Response(cached_data, status=status.HTTP_200_OK)
        
        # Get query parameters
        search = request.GET.get('search', '')
        category = request.GET.get('category', '')
        course_type = request.GET.get('course_type', '')
        difficulty = request.GET.get('difficulty', '')
        min_price = request.GET.get('min_price')
        max_price = request.GET.get('max_price')
        is_featured = request.GET.get('is_featured', '')
        sort_by = request.GET.get('sort_by', '-created_at')
        page = int(request.GET.get('page', 1))
        per_page = min(int(request.GET.get('per_page', 12)), 50)  # Max 50 per page
        
        # Build queryset
        queryset = Course.objects.filter(is_active=True).select_related('created_by').prefetch_related('reviews')
        
        # Apply filters
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | 
                Q(description__icontains=search) |
                Q(category__icontains=search)
            )
        
        if category:
            queryset = queryset.filter(category=category)
        
        if course_type:
            queryset = queryset.filter(course_type=course_type)
        
        if difficulty:
            queryset = queryset.filter(difficulty_level=difficulty)
        
        if min_price:
            queryset = queryset.filter(price__gte=min_price)
        
        if max_price:
            queryset = queryset.filter(price__lte=max_price)
        
        if is_featured:
            queryset = queryset.filter(is_featured=is_featured.lower() == 'true')
        
        # Apply sorting
        valid_sort_fields = ['title', 'price', 'created_at', '-created_at', '-price', '-title']
        if sort_by in valid_sort_fields:
            queryset = queryset.order_by(sort_by)
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = CourseSerializer(page_obj.object_list, many=True)
        
        # Add user enrollment status if authenticated
        courses_data = serializer.data
        if request.user.is_authenticated:
            user_enrollments = set(
                CourseEnrollment.objects.filter(
                    user=request.user,
                    is_active=True
                ).values_list('course_id', flat=True)
            )
            
            for course in courses_data:
                course['is_enrolled'] = course['id'] in user_enrollments
        
        response_data = {
            'courses': courses_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_courses': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'filters': {
                'categories': list(Course.objects.filter(is_active=True).values_list('category', flat=True).distinct()),
                'course_types': [choice[0] for choice in Course.COURSE_TYPES],
                'difficulty_levels': ['beginner', 'intermediate', 'advanced']
            }
        }
        
        # Cache for 15 minutes for anonymous users
        if not request.user.is_authenticated:
            cache.set(cache_key, response_data, 900)
        
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"List courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_course_detail(request, course_id):
    """
    Get detailed course information
    GET /api/courses/{course_id}/
    """
    try:
        course = Course.objects.select_related('created_by').prefetch_related(
            'reviews__user', 'user_progress', 'exams'
        ).get(id=course_id, is_active=True)
        
        serializer = CourseSerializer(course)
        data = serializer.data
        
        # Add enrollment info if user is authenticated
        if request.user.is_authenticated:
            try:
                enrollment = CourseEnrollment.objects.get(user=request.user, course=course)
                progress = UserCourseProgress.objects.get(user=request.user, course=course)
                
                data['enrollment_info'] = {
                    'is_enrolled': True,
                    'enrollment_date': enrollment.enrolled_at,
                    'payment_status': enrollment.payment_status,
                    'progress_percentage': progress.progress_percentage,
                    'last_accessed': progress.last_accessed,
                    'is_completed': progress.is_completed()
                }
            except (CourseEnrollment.DoesNotExist, UserCourseProgress.DoesNotExist):
                data['enrollment_info'] = {'is_enrolled': False}
        
        # Add reviews
        reviews = course.reviews.filter(is_approved=True).select_related('user')[:10]
        data['recent_reviews'] = CourseReviewSerializer(reviews, many=True).data
        
        # Add course exams info
        exams = course.exams.filter(is_active=True, is_published=True)
        data['exams_info'] = {
            'total_exams': exams.count(),
            'exam_types': list(exams.values_list('exam_type', flat=True).distinct())
        }
        
        # Add similar courses
        similar_courses = Course.objects.filter(
            category=course.category,
            is_active=True
        ).exclude(id=course.id)[:4]
        
        data['similar_courses'] = CourseSerializer(similar_courses, many=True).data
        
        return Response(data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get course detail error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course details.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_featured_courses(request):
    """
    Get featured courses
    GET /api/courses/featured/
    """
    try:
        courses = Course.objects.filter(
            is_active=True, 
            is_featured=True
        ).order_by('-created_at')[:8]
        
        serializer = CourseSerializer(courses, many=True)
        
        return Response({
            'featured_courses': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Get featured courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch featured courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def get_course_categories(request):
    """
    Get all course categories
    GET /api/courses/categories/
    """
    try:
        categories = CourseCategory.objects.filter(is_active=True).order_by('order', 'name')
        serializer = CourseCategorySerializer(categories, many=True)
        
        return Response({
            'categories': serializer.data
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Get course categories error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course categories.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# COURSE ENROLLMENT AND PAYMENT

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enroll_course(request, course_id):
    """
    Enroll in a course (free or paid)
    POST /api/courses/{course_id}/enroll/
    """
    try:
        course = Course.objects.get(id=course_id, is_active=True)
        user = request.user
        
        # Check if already enrolled
        existing_enrollment = CourseEnrollment.objects.filter(
            user=user, 
            course=course,
            payment_status='completed'
        ).first()
        
        if existing_enrollment:
            return Response(
                {
                    'detail': 'You are already enrolled in this course.',
                    'enrollment_id': str(existing_enrollment.id),
                    'enrolled_at': existing_enrollment.enrolled_at
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check for pending enrollment
        pending_enrollment = CourseEnrollment.objects.filter(
            user=user,
            course=course,
            payment_status='pending'
        ).first()
        
        if pending_enrollment:
            # Return existing payment details
            try:
                payment = Payment.objects.get(reference=pending_enrollment.payment_id)
                return Response({
                    'message': 'You have a pending payment for this course.',
                    'payment_reference': payment.reference,
                    'amount': float(payment.amount),
                    'currency': payment.currency,
                    'can_verify': True,
                    'enrollment_id': str(pending_enrollment.id)
                }, status=status.HTTP_200_OK)
            except Payment.DoesNotExist:
                # Clean up orphaned enrollment
                pending_enrollment.delete()
        
        # Check if course is free
        if course.is_free():
            # Free enrollment
            with transaction.atomic():
                enrollment = CourseEnrollment.objects.create(
                    user=user,
                    course=course,
                    payment_status='completed',
                    payment_method='free',
                    amount_paid=0.00,
                    currency='NGN'
                )
                
                UserCourseProgress.objects.create(
                    user=user,
                    course=course,
                    progress_percentage=0
                )

                # Check for high-value enrollment notification (though free courses will also trigger this)
                try:
                    AdminEmailService.notify_high_value_enrollment(enrollment)
                except Exception as e:
                    logger.warning(f"High value enrollment notification failed: {str(e)}")
                
                # Send confirmation email
                EmailService.send_enrollment_confirmation(user, course, enrollment)
                
                logger.info(f"Free enrollment: {user.email} -> {course.title}")
                
                return Response({
                    'message': 'Successfully enrolled in the course.',
                    'enrollment': CourseEnrollmentSerializer(enrollment).data,
                    'course_access': True,
                    'redirect_url': f"/dashboard/courses/{course.id}"
                }, status=status.HTTP_201_CREATED)
        
        else:
            # Paid enrollment
            callback_url = request.data.get('callback_url', f"{settings.FRONTEND_URL}/payment/callback")
            amount = course.get_effective_price()
            gateway_name = request.data.get('gateway', 'paystack')  # Default to paystack
            currency = request.data.get('currency', course.currency or 'NGN')  # Use course currency

            # Validate amount
            if amount <= 0:
                return Response(
                    {'detail': 'Invalid course price. Please contact support.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validate gateway
            if gateway_name not in ['paystack', 'flutterwave']:  # Add your supported gateways
                return Response(
                    {'detail': 'Unsupported payment gateway.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create payment record
            payment = Payment.objects.create(
                user=user,
                course=course,
                amount=amount,
                currency=currency,
                customer_email=user.email,
                customer_name=user.full_name,
                customer_phone=getattr(user, 'phone', ''),
                gateway_name=gateway_name,
                metadata={
                    'course_id': str(course.id),
                    'course_title': course.title,
                    'user_id': str(user.id)
                }
            )

            # Initialize payment
            try:
                payment_service = PaymentServiceFactory.get_service(gateway_name)
                payment_result = payment_service.initialize_payment(payment, callback_url)

                if payment_result['success']:
                    # Create pending enrollment with payment reference
                    enrollment = CourseEnrollment.objects.create(
                        user=user,
                        course=course,
                        payment_status='pending',
                        payment_method=gateway_name,
                        payment_id=payment.reference,
                        amount_paid=amount,
                        currency=currency
                    )

                    logger.info(f"Payment initialized: {user.email} -> {course.title} (Ref: {payment.reference})")

                    return Response({
                        'message': 'Payment initialized successfully.',
                        'payment_url': payment_result['payment_url'],
                        'reference': payment.reference,
                        'enrollment_id': str(enrollment.id),
                        'amount': float(amount),
                        'currency': currency,
                        'gateway': gateway_name,
                        'expires_at': (timezone.now() + timezone.timedelta(minutes=30)).isoformat()
                    }, status=status.HTTP_200_OK)

                else:
                    payment.status = 'failed'
                    payment.gateway_response = payment_result
                    payment.save()
                    return Response(
                        {'detail': payment_result.get('message', 'Payment initialization failed')},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            except ValueError as e:
                return Response(
                    {'detail': str(e)},
                    status=status.HTTP_400_BAD_REQUEST
                )
            except Exception as e:
                logger.error(f"Payment initialization error: {str(e)}")
                return Response(
                    {'detail': 'Payment service temporarily unavailable. Please try again.'},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE
                )
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Course enrollment error: {str(e)}")
        return Response(
            {'detail': 'Enrollment failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    """
    Verify payment and complete enrollment
    POST /api/courses/verify-payment/
    """
    reference = request.data.get('reference')
    
    if not reference:
        return Response(
            {'detail': 'Payment reference is required.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        # Get payment record
        payment = Payment.objects.get(reference=reference)
        
        # Get enrollment by payment reference
        enrollment = CourseEnrollment.objects.get(
            payment_id=reference,
            payment_status='pending'
        )
        
        # Verify payment
        try:
            payment_service = PaymentServiceFactory.get_service(payment.gateway_name)
            verification_result = payment_service.verify_payment(reference)
            
            if verification_result['success'] and verification_result['verified']:
                # Check if payment was actually successful
                if verification_result.get('status') == 'success':
                    with transaction.atomic():
                        # Update payment record
                        payment.status = 'completed'
                        payment.paid_at = timezone.now()
                        payment.gateway_response = verification_result['data']
                        payment.save()
                        
                        # Update enrollment
                        enrollment.payment_status = 'completed'
                        enrollment.save(update_fields=['payment_status'])
                        
                        # Create progress record
                        UserCourseProgress.objects.get_or_create(
                            user=enrollment.user,
                            course=enrollment.course,
                            defaults={'progress_percentage': 0}
                        )

                        # Notify about high-value enrollment
                        try:
                            AdminEmailService.notify_high_value_enrollment(enrollment)
                        except Exception as e:
                            logger.warning(f"High value enrollment notification failed: {str(e)}")
                        
                        # Send confirmation email
                        try:
                            EmailService.send_enrollment_confirmation(
                                enrollment.user, 
                                enrollment.course, 
                                enrollment
                            )
                        except Exception as email_error:
                            logger.warning(f"Email sending failed: {str(email_error)}")
                        
                        logger.info(f"Payment verified: {enrollment.user.email} -> {enrollment.course.title}")
                        
                        return Response({
                            'message': 'Payment verified successfully. You are now enrolled!',
                            'enrollment': CourseEnrollmentSerializer(enrollment).data,
                            'course_access': True,
                            'course_id': str(enrollment.course.id),
                            'course_title': enrollment.course.title,
                            'redirect_url': f"/dashboard/courses/{enrollment.course.id}"
                        }, status=status.HTTP_200_OK)
                
                else:
                    # Payment failed
                    payment.status = 'failed'
                    payment.save()
                    enrollment.payment_status = 'failed'
                    enrollment.save(update_fields=['payment_status'])
                    
                    return Response(
                        {'detail': f'Payment failed: {verification_result.get("message", "Unknown error")}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            else:
                return Response(
                    {'detail': verification_result.get('message', 'Payment verification failed')},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except ValueError as e:
            return Response(
                {'detail': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except (Payment.DoesNotExist, CourseEnrollment.DoesNotExist):
        return Response(
            {'detail': 'Payment or enrollment not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Payment verification error: {str(e)}")
        return Response(
            {'detail': 'Payment verification failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
# Payment status checking
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def check_payment_status(request, reference):
    """
    Check payment status without processing
    GET /api/courses/payment-status/{reference}/
    """
    try:
        payment = Payment.objects.get(reference=reference, user=request.user)
        
        # Get associated enrollment
        try:
            enrollment = CourseEnrollment.objects.get(payment_id=reference)
        except CourseEnrollment.DoesNotExist:
            enrollment = None
        
        return Response({
            'reference': payment.reference,
            'status': payment.status,
            'amount': float(payment.amount),
            'currency': payment.currency,
            'gateway': payment.gateway_name,
            'course_title': payment.course.title,
            'enrollment_status': enrollment.payment_status if enrollment else None,
            'can_verify': payment.status in ['pending', 'processing'],
            'is_completed': payment.status == 'completed',
            'created_at': payment.created_at
        }, status=status.HTTP_200_OK)
    
    except Payment.DoesNotExist:
        return Response(
            {'detail': 'Payment not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Payment status check error: {str(e)}")
        return Response(
            {'detail': 'Failed to check payment status.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# COURSE SECTIONS AND LESSONS ACCESS

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_content(request, course_id):
    """
    Get course sections and lessons structure
    GET /api/courses/{course_id}/content/
    """
    try:
        course = Course.objects.get(id=course_id, is_active=True)
        
        # Check if user is enrolled
        try:
            enrollment = CourseEnrollment.objects.get(
                user=request.user,
                course=course,
                is_active=True,
                payment_status='completed'
            )
        except CourseEnrollment.DoesNotExist:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get user progress
        progress, _ = UserCourseProgress.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={'progress_percentage': 0}
        )
        
        # Get course sections with lessons
        sections = CourseSection.objects.filter(
            course=course,
            is_active=True
        ).prefetch_related('lessons').order_by('order')
        
        sections_data = []
        for section in sections:
            section_data = {
                'id': str(section.id),
                'title': section.title,
                'description': section.description,
                'order': section.order,
                'is_preview': section.is_preview,
                'total_lessons': section.total_lessons,
                'total_duration_seconds': section.total_duration_seconds,
                'is_accessible': section.is_accessible_by_user(request.user),
                'completion_rate': section.get_completion_rate(request.user),
                'lessons': []
            }
            
            # Get lessons
            lessons = section.lessons.filter(is_active=True).order_by('order')
            for lesson in lessons:
                lesson_progress = None
                try:
                    lesson_progress = UserLessonProgress.objects.get(
                        user=request.user,
                        lesson=lesson
                    )
                except UserLessonProgress.DoesNotExist:
                    pass
                
                lesson_data = {
                    'id': str(lesson.id),
                    'title': lesson.title,
                    'lesson_type': lesson.lesson_type,
                    'order': lesson.order,
                    'duration_seconds': lesson.duration_seconds,
                    'is_preview': lesson.is_preview,
                    'is_accessible': lesson.is_accessible_by_user(request.user),
                    'is_completed': lesson_progress.is_completed if lesson_progress else False,
                    'watch_percentage': lesson_progress.watch_percentage if lesson_progress else 0,
                    'last_accessed': lesson_progress.last_accessed if lesson_progress else None
                }
                section_data['lessons'].append(lesson_data)
            
            sections_data.append(section_data)
        
        return Response({
            'course': {
                'id': str(course.id),
                'title': course.title,
                'description': course.description,
                'total_sections': course.total_sections,
                'total_lessons': course.total_lessons,
                'total_duration_seconds': course.total_duration_seconds
            },
            'progress': {
                'percentage': progress.progress_percentage,
                'current_section_id': str(progress.current_section_id) if progress.current_section_id else None,
                'current_lesson_id': str(progress.current_lesson_id) if progress.current_lesson_id else None
            },
            'sections': sections_data
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get course content error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course content.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lesson_detail(request, course_id, section_id, lesson_id):
    """
    Get detailed lesson information
    GET /api/courses/{course_id}/sections/{section_id}/lessons/{lesson_id}/
    """
    try:
        # Get lesson with related data
        lesson = CourseLesson.objects.select_related('section', 'section__course').get(
            id=lesson_id,
            section_id=section_id,
            section__course_id=course_id,
            is_active=True
        )
        
        # Check course enrollment
        try:
            enrollment = CourseEnrollment.objects.get(
                user=request.user,
                course=lesson.section.course,
                is_active=True,
                payment_status='completed'
            )
        except CourseEnrollment.DoesNotExist:
            # Check if lesson is preview
            if not lesson.is_preview:
                return Response(
                    {'detail': 'You are not enrolled in this course.'},
                    status=status.HTTP_403_FORBIDDEN
                )
        
        # Check if lesson is accessible
        if not lesson.is_accessible_by_user(request.user):
            return Response(
                {'detail': 'This lesson is not accessible yet. Complete previous lessons first.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get or create lesson progress
        lesson_progress, created = UserLessonProgress.objects.get_or_create(
            user=request.user,
            lesson=lesson,
            defaults={
                'watch_time_seconds': 0,
                'current_position_seconds': 0,
                'watch_percentage': 0
            }
        )
        
        if not created:
            lesson_progress.access_count += 1
            lesson_progress.save(update_fields=['access_count'])
        
        # Get next and previous lessons
        next_lesson = lesson.get_next_lesson()
        previous_lesson = lesson.get_previous_lesson()
        
        lesson_data = {
            'id': str(lesson.id),
            'title': lesson.title,
            'description': lesson.description,
            'lesson_type': lesson.lesson_type,
            'duration_seconds': lesson.duration_seconds,
            'video_url': lesson.get_video_url(),
            'text_content': lesson.text_content,
            'thumbnail_url': lesson.thumbnail.url if lesson.thumbnail else None,
            'attachments': lesson.attachments,
            'is_downloadable': lesson.is_downloadable,
            'auto_play_next': lesson.auto_play_next,
            'minimum_watch_percentage': lesson.minimum_watch_percentage,
            'progress': {
                'watch_time_seconds': lesson_progress.watch_time_seconds,
                'current_position_seconds': lesson_progress.current_position_seconds,
                'watch_percentage': lesson_progress.watch_percentage,
                'is_completed': lesson_progress.is_completed,
                'bookmarks': lesson_progress.bookmarks,
                'notes': lesson_progress.notes,
                'last_accessed': lesson_progress.last_accessed
            },
            'navigation': {
                'next_lesson': {
                    'id': str(next_lesson.id),
                    'title': next_lesson.title,
                    'section_id': str(next_lesson.section.id)
                } if next_lesson else None,
                'previous_lesson': {
                    'id': str(previous_lesson.id),
                    'title': previous_lesson.title,
                    'section_id': str(previous_lesson.section.id)
                } if previous_lesson else None
            },
            'section': {
                'id': str(lesson.section.id),
                'title': lesson.section.title,
                'order': lesson.section.order
            },
            'course': {
                'id': str(lesson.section.course.id),
                'title': lesson.section.course.title
            }
        }
        
        return Response(lesson_data, status=status.HTTP_200_OK)
    
    except CourseLesson.DoesNotExist:
        return Response(
            {'detail': 'Lesson not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Lesson detail error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch lesson details.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_lesson_progress(request, course_id, section_id, lesson_id):
    """
    Update lesson progress
    PUT/PATCH /api/courses/{course_id}/sections/{section_id}/lessons/{lesson_id}/progress/
    """
    try:
        lesson = CourseLesson.objects.select_related('section', 'section__course').get(
            id=lesson_id,
            section_id=section_id,
            section__course_id=course_id,
            is_active=True
        )
        
        # Check enrollment
        try:
            enrollment = CourseEnrollment.objects.get(
                user=request.user,
                course=lesson.section.course,
                is_active=True,
                payment_status='completed'
            )
        except CourseEnrollment.DoesNotExist:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get lesson progress
        lesson_progress, created = UserLessonProgress.objects.get_or_create(
            user=request.user,
            lesson=lesson
        )
        
        # Update progress fields
        watch_time = request.data.get('watch_time_seconds')
        current_position = request.data.get('current_position_seconds')
        watch_percentage = request.data.get('watch_percentage')
        
        if watch_time is not None:
            lesson_progress.watch_time_seconds = max(lesson_progress.watch_time_seconds, int(watch_time))
        
        if current_position is not None:
            lesson_progress.current_position_seconds = int(current_position)
        
        if watch_percentage is not None:
            lesson_progress.watch_percentage = min(100, max(0, int(watch_percentage)))
        
        lesson_progress.save()
        
        return Response({
            'message': 'Progress updated successfully.',
            'progress': {
                'watch_time_seconds': lesson_progress.watch_time_seconds,
                'current_position_seconds': lesson_progress.current_position_seconds,
                'watch_percentage': lesson_progress.watch_percentage,
                'is_completed': lesson_progress.is_completed,
                'completed_at': lesson_progress.completed_at
            }
        }, status=status.HTTP_200_OK)
    
    except CourseLesson.DoesNotExist:
        return Response(
            {'detail': 'Lesson not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Update lesson progress error: {str(e)}")
        return Response(
            {'detail': 'Failed to update lesson progress.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'POST', 'DELETE'])
@permission_classes([IsAuthenticated])
def manage_bookmarks(request, lesson_id):
    """
    Manage lesson bookmarks
    GET/POST/DELETE /api/lessons/{lesson_id}/bookmarks/
    """
    try:
        lesson = CourseLesson.objects.get(id=lesson_id, is_active=True)
        
        # Check access
        if not lesson.is_accessible_by_user(request.user):
            return Response(
                {'detail': 'You do not have access to this lesson.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        lesson_progress, _ = UserLessonProgress.objects.get_or_create(
            user=request.user,
            lesson=lesson
        )
        
        if request.method == 'GET':
            return Response({
                'bookmarks': lesson_progress.bookmarks
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'POST':
            position = request.data.get('position_seconds')
            title = request.data.get('title', '')
            description = request.data.get('description', '')
            
            if position is None:
                return Response(
                    {'detail': 'Position is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            bookmark = lesson_progress.add_bookmark(position, title, description)
            
            return Response({
                'message': 'Bookmark added successfully.',
                'bookmark': bookmark
            }, status=status.HTTP_201_CREATED)
        
        elif request.method == 'DELETE':
            index = request.data.get('index')
            
            if index is None:
                return Response(
                    {'detail': 'Bookmark index is required.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            removed = lesson_progress.remove_bookmark(index)
            
            if removed:
                return Response({
                    'message': 'Bookmark removed successfully.'
                }, status=status.HTTP_200_OK)
            else:
                return Response(
                    {'detail': 'Bookmark not found.'},
                    status=status.HTTP_404_NOT_FOUND
                )
    
    except CourseLesson.DoesNotExist:
        return Response(
            {'detail': 'Lesson not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Manage bookmarks error: {str(e)}")
        return Response(
            {'detail': 'Failed to manage bookmarks.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def manage_notes(request, lesson_id):
    """
    Manage lesson notes
    GET/PUT /api/lessons/{lesson_id}/notes/
    """
    try:
        lesson = CourseLesson.objects.get(id=lesson_id, is_active=True)
        
        # Check access
        if not lesson.is_accessible_by_user(request.user):
            return Response(
                {'detail': 'You do not have access to this lesson.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        lesson_progress, _ = UserLessonProgress.objects.get_or_create(
            user=request.user,
            lesson=lesson
        )
        
        if request.method == 'GET':
            return Response({
                'notes': lesson_progress.notes
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'PUT':
            notes = request.data.get('notes', '')
            lesson_progress.notes = notes
            lesson_progress.save(update_fields=['notes'])
            
            return Response({
                'message': 'Notes updated successfully.',
                'notes': lesson_progress.notes
            }, status=status.HTTP_200_OK)
    
    except CourseLesson.DoesNotExist:
        return Response(
            {'detail': 'Lesson not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Manage notes error: {str(e)}")
        return Response(
            {'detail': 'Failed to manage notes.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_progress(request):
    """
    Get comprehensive user progress across all courses
    GET /api/student/progress/
    """
    try:
        user = request.user
        
        # Get all course progress
        course_progress = UserCourseProgress.objects.filter(
            user=user
        ).select_related('course').order_by('-last_accessed')
        
        # Get recent lesson activity
        recent_lessons = UserLessonProgress.objects.filter(
            user=user
        ).select_related('lesson', 'lesson__section', 'lesson__section__course').order_by('-last_accessed')[:10]
        
        # Calculate overall statistics
        total_courses = course_progress.count()
        completed_courses = course_progress.filter(progress_percentage=100).count()
        total_watch_time = course_progress.aggregate(
            total=Sum('total_watch_time_seconds')
        )['total'] or 0
        
        # Get certificates
        certificates = ExamCertificate.objects.filter(
            user=user,
            is_valid=True
        ).select_related('exam', 'exam__course').count()
        
        return Response({
            'statistics': {
                'total_courses': total_courses,
                'completed_courses': completed_courses,
                'in_progress_courses': course_progress.filter(
                    progress_percentage__gt=0,
                    progress_percentage__lt=100
                ).count(),
                'total_watch_time_hours': round(total_watch_time / 3600, 2),
                'certificates_earned': certificates,
                'completion_rate': round((completed_courses / total_courses * 100), 2) if total_courses > 0 else 0
            },
            'course_progress': UserCourseProgressSerializer(course_progress, many=True).data,
            'recent_activity': [
                {
                    'lesson_id': str(lesson.lesson.id),
                    'lesson_title': lesson.lesson.title,
                    'course_title': lesson.lesson.section.course.title,
                    'section_title': lesson.lesson.section.title,
                    'watch_percentage': lesson.watch_percentage,
                    'is_completed': lesson.is_completed,
                    'last_accessed': lesson.last_accessed
                }
                for lesson in recent_lessons
            ]
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"My progress error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch progress data.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# USER COURSE PROGRESS
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_courses(request):
    """
    Get user's enrolled courses
    GET /api/courses/my-courses/
    """
    try:
        # Get query parameters
        status_filter = request.GET.get('status', '')  # completed, in_progress, not_started
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 12))
        
        # Build queryset
        queryset = UserCourseProgress.objects.filter(user=request.user).select_related('course')
        
        # Apply status filter
        if status_filter == 'completed':
            queryset = queryset.filter(progress_percentage=100)
        elif status_filter == 'in_progress':
            queryset = queryset.filter(progress_percentage__gt=0, progress_percentage__lt=100)
        elif status_filter == 'not_started':
            queryset = queryset.filter(progress_percentage=0)
        
        # Order by last accessed
        queryset = queryset.order_by('-last_accessed')
        
        # Paginate
        paginator = Paginator(queryset, per_page)
        page_obj = paginator.get_page(page)
        
        # Serialize data
        serializer = UserCourseProgressSerializer(page_obj.object_list, many=True)
        
        # Calculate summary stats
        total_courses = queryset.count()
        completed_courses = queryset.filter(progress_percentage=100).count()
        in_progress_courses = queryset.filter(progress_percentage__gt=0, progress_percentage__lt=100).count()
        
        return Response({
            'my_courses': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_courses': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            },
            'summary': {
                'total_courses': total_courses,
                'completed_courses': completed_courses,
                'in_progress_courses': in_progress_courses,
                'completion_rate': round((completed_courses / total_courses * 100), 2) if total_courses > 0 else 0
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"My courses error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch your courses.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def course_progress(request, course_id):
    """
    Get or update course progress
    GET/PUT /api/courses/{course_id}/progress/
    """
    try:
        course = Course.objects.get(id=course_id, is_active=True)
        
        # Check if user is enrolled
        try:
            enrollment = CourseEnrollment.objects.get(
                user=request.user, 
                course=course,
                is_active=True,
                payment_status='completed'
            )
        except CourseEnrollment.DoesNotExist:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get or create progress
        progress, created = UserCourseProgress.objects.get_or_create(
            user=request.user,
            course=course,
            defaults={'progress_percentage': 0}
        )
        
        if request.method == 'GET':
            serializer = UserCourseProgressSerializer(progress)
            data = serializer.data
            
            # Add course exams if available
            exams = course.exams.filter(is_active=True, is_published=True)
            user_attempts = UserExamAttempt.objects.filter(
                user=request.user,
                exam__in=exams
            ).select_related('exam')
            
            exams_data = []
            for exam in exams:
                user_attempt = user_attempts.filter(exam=exam).order_by('-attempt_number').first()
                exam_data = {
                    'id': str(exam.id),
                    'title': exam.title,
                    'exam_type': exam.exam_type,
                    'total_questions': exam.total_questions,
                    'time_limit_minutes': exam.time_limit_minutes,
                    'max_attempts': exam.max_attempts,
                    'passing_score': exam.passing_score,
                    'user_attempts': user_attempts.filter(exam=exam).count(),
                    'last_attempt': UserExamAttemptSerializer(user_attempt).data if user_attempt else None,
                    'can_attempt': user_attempts.filter(exam=exam).count() < exam.max_attempts,
                    'is_available': exam.is_available()
                }
                exams_data.append(exam_data)
            
            data['exams'] = exams_data
            
            return Response(data, status=status.HTTP_200_OK)
        
        elif request.method == 'PUT':
            serializer = UserCourseProgressUpdateSerializer(progress, data=request.data, partial=True)
            
            if not serializer.is_valid():
                return Response(
                    {'detail': 'Invalid data.', 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            updated_progress = serializer.save()
            
            # Check if course is completed
            if updated_progress.progress_percentage == 100 and not updated_progress.completed_at:
                updated_progress.mark_complete()
                
                # Send completion email
                EmailService.send_course_completion_notification(request.user, course)
            
            response_serializer = UserCourseProgressSerializer(updated_progress)
            return Response(response_serializer.data, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Course progress error: {str(e)}")
        return Response(
            {'detail': 'Failed to process course progress.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# COURSE REVIEWS

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def course_reviews(request, course_id):
    """
    Get course reviews or add a new review
    GET/POST /api/courses/{course_id}/reviews/
    """
    try:
        course = Course.objects.get(id=course_id, is_active=True)
        
        if request.method == 'GET':
            # Get course reviews
            page = int(request.GET.get('page', 1))
            per_page = int(request.GET.get('per_page', 10))
            
            reviews = CourseReview.objects.filter(
                course=course,
                is_approved=True
            ).select_related('user').order_by('-created_at')
            
            paginator = Paginator(reviews, per_page)
            page_obj = paginator.get_page(page)
            
            serializer = CourseReviewSerializer(page_obj.object_list, many=True)
            
            return Response({
                'reviews': serializer.data,
                'pagination': {
                    'current_page': page,
                    'total_pages': paginator.num_pages,
                    'total_reviews': paginator.count,
                    'per_page': per_page,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                }
            }, status=status.HTTP_200_OK)
        
        elif request.method == 'POST':
            # Check if user has completed the course
            try:
                progress = UserCourseProgress.objects.get(user=request.user, course=course)
                if not progress.is_completed():
                    return Response(
                        {'detail': 'You must complete the course before reviewing it.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except UserCourseProgress.DoesNotExist:
                return Response(
                    {'detail': 'You must be enrolled in the course to review it.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if user has already reviewed
            if CourseReview.objects.filter(user=request.user, course=course).exists():
                return Response(
                    {'detail': 'You have already reviewed this course.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Create review
            serializer = CourseReviewSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response(
                    {'detail': 'Invalid review data.', 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            review = serializer.save(user=request.user, course=course)
            
            # Send notification to super admins about new review
            EmailService.send_new_review_notification(review)
            
            logger.info(f"Course review created: {request.user.email} -> {course.title}")
            
            return Response(
                CourseReviewSerializer(review).data,
                status=status.HTTP_201_CREATED
            )
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Course reviews error: {str(e)}")
        return Response(
            {'detail': 'Failed to process course reviews.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# COURSE EXAMS AND ASSESSMENTS

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_course_exams(request, course_id):
    """
    Get available exams for a course
    GET /api/courses/{course_id}/exams/
    """
    try:
        course = Course.objects.get(id=course_id, is_active=True)
        
        # Check if user is enrolled
        try:
            enrollment = CourseEnrollment.objects.get(
                user=request.user,
                course=course,
                is_active=True,
                payment_status='completed'
            )
        except CourseEnrollment.DoesNotExist:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get user's course progress
        try:
            progress = UserCourseProgress.objects.get(user=request.user, course=course)
        except UserCourseProgress.DoesNotExist:
            return Response(
                {'detail': 'Course progress not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get available exams
        exams = CourseExam.objects.filter(
            course=course,
            is_active=True,
            is_published=True
        ).order_by('exam_type', 'title')
        
        exams_data = []
        for exam in exams:
            # Check if exam is available based on course progress
            is_available = (
                progress.progress_percentage >= exam.required_course_progress and
                exam.is_available()
            )
            
            # Get user's attempts for this exam
            user_attempts = UserExamAttempt.objects.filter(
                user=request.user,
                exam=exam
            ).order_by('-attempt_number')
            
            # Check if user can take the exam
            can_attempt = (
                is_available and
                user_attempts.count() < exam.max_attempts
            )
            
            # Get best attempt
            best_attempt = user_attempts.filter(status='completed').order_by('-percentage_score').first()
            
            exam_data = {
                'id': str(exam.id),
                'title': exam.title,
                'description': exam.description,
                'instructions': exam.instructions,
                'exam_type': exam.exam_type,
                'difficulty_level': exam.difficulty_level,
                'total_questions': exam.total_questions,
                'time_limit_minutes': exam.time_limit_minutes,
                'passing_score': exam.passing_score,
                'max_attempts': exam.max_attempts,
                'required_course_progress': exam.required_course_progress,
                'is_available': is_available,
                'can_attempt': can_attempt,
                'user_attempts_count': user_attempts.count(),
                'best_score': best_attempt.percentage_score if best_attempt else None,
                'last_attempt': UserExamAttemptSerializer(user_attempts.first()).data if user_attempts.exists() else None,
                'show_results_immediately': exam.show_results_immediately,
                'show_correct_answers': exam.show_correct_answers,
                'allow_review': exam.allow_review,
                'available_from': exam.available_from,
                'available_until': exam.available_until
            }
            exams_data.append(exam_data)
        
        return Response({
            'exams': exams_data,
            'course_progress': progress.progress_percentage
        }, status=status.HTTP_200_OK)
    
    except Course.DoesNotExist:
        return Response(
            {'detail': 'Course not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get course exams error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch course exams.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def start_exam(request, exam_id):
    """
    Start an exam attempt
    POST /api/exams/{exam_id}/start/
    """
    try:
        exam = CourseExam.objects.get(id=exam_id, is_active=True, is_published=True)
        
        # Check if user is enrolled in the course
        try:
            enrollment = CourseEnrollment.objects.get(
                user=request.user,
                course=exam.course,
                is_active=True,
                payment_status='completed'
            )
        except CourseEnrollment.DoesNotExist:
            return Response(
                {'detail': 'You are not enrolled in this course.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check course progress requirement
        try:
            progress = UserCourseProgress.objects.get(user=request.user, course=exam.course)
            if progress.progress_percentage < exam.required_course_progress:
                return Response(
                    {'detail': f'You need to complete at least {exam.required_course_progress}% of the course before taking this exam.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        except UserCourseProgress.DoesNotExist:
            return Response(
                {'detail': 'Course progress not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Check if exam is available
        if not exam.is_available():
            return Response(
                {'detail': 'This exam is not currently available.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check attempt limit
        user_attempts = UserExamAttempt.objects.filter(user=request.user, exam=exam)
        if user_attempts.count() >= exam.max_attempts:
            return Response(
                {'detail': f'You have reached the maximum number of attempts ({exam.max_attempts}) for this exam.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if user has an active attempt
        active_attempt = user_attempts.filter(status='in_progress').first()
        if active_attempt:
            return Response(
                {'detail': 'You already have an active attempt for this exam.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get exam questions
        questions = list(exam.questions.filter(is_active=True).prefetch_related('answers'))
        
        if not questions:
            return Response(
                {'detail': 'No questions available for this exam.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Shuffle questions if required
        if exam.shuffle_questions:
            random.shuffle(questions)
        
        # Prepare exam data
        exam_data = {
            'questions_order': [str(q.id) for q in questions],
            'shuffle_answers': exam.shuffle_answers,
            'started_at': timezone.now().isoformat()
        }
        
        # Create exam attempt
        attempt = UserExamAttempt.objects.create(
            user=request.user,
            exam=exam,
            exam_data=exam_data
        )
        
        # Send exam started notification
        EmailService.send_exam_started_notification(request.user, exam, attempt)
        
        logger.info(f"Exam started: {request.user.email} -> {exam.title} (Attempt {attempt.attempt_number})")
        
        return Response({
            'message': 'Exam started successfully.',
            'attempt_id': str(attempt.id),
            'attempt_number': attempt.attempt_number,
            'time_limit_minutes': exam.time_limit_minutes,
            'total_questions': len(questions),
            'instructions': exam.instructions
        }, status=status.HTTP_201_CREATED)
    
    except CourseExam.DoesNotExist:
        return Response(
            {'detail': 'Exam not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Start exam error: {str(e)}")
        return Response(
            {'detail': 'Failed to start exam.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exam_questions(request, attempt_id):
    """
    Get questions for an exam attempt
    GET /api/exam-attempts/{attempt_id}/questions/
    """
    try:
        attempt = UserExamAttempt.objects.select_related('exam', 'user').get(
            id=attempt_id,
            user=request.user,
            status='in_progress'
        )
        
        # Check if exam has time limit and is not expired
        if attempt.exam.time_limit_minutes:
            time_remaining = attempt.time_remaining()
            if time_remaining is not None and time_remaining <= 0:
                # Time's up - auto-complete the attempt
                attempt.status = 'timed_out'
                attempt.complete_attempt()
                
                return Response(
                    {'detail': 'Time limit exceeded. Exam has been automatically submitted.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Get questions in the order they were shuffled
        questions_order = attempt.exam_data.get('questions_order', [])
        questions = []
        
        for question_id in questions_order:
            try:
                question = ExamQuestion.objects.prefetch_related('answers').get(
                    id=question_id,
                    exam=attempt.exam,
                    is_active=True
                )
                
                question_data = {
                    'id': str(question.id),
                    'question_text': question.question_text,
                    'question_type': question.question_type,
                    'points': question.points,
                    'image_url': question.image.url if question.image else None,
                    'answers': []
                }
                
                # Add answers
                answers = list(question.answers.all())
                if attempt.exam_data.get('shuffle_answers', False):
                    random.shuffle(answers)
                
                for answer in answers:
                    answer_data = {
                        'id': str(answer.id),
                        'answer_text': answer.answer_text,
                        'image_url': answer.image.url if answer.image else None
                    }
                    question_data['answers'].append(answer_data)
                
                questions.append(question_data)
                
            except ExamQuestion.DoesNotExist:
                continue
        
        # Get user's existing answers
        user_answers = UserExamAnswer.objects.filter(attempt=attempt).select_related('question')
        answers_data = {}
        
        for user_answer in user_answers:
            question_id = str(user_answer.question.id)
            if user_answer.question.question_type == 'multiple_choice':
                answers_data[question_id] = [str(ans_id) for ans_id in user_answer.selected_answers.values_list('id', flat=True)]
            else:
                answers_data[question_id] = user_answer.text_answer
        
        return Response({
            'attempt_id': str(attempt.id),
            'exam_title': attempt.exam.title,
            'questions': questions,
            'user_answers': answers_data,
            'current_question_index': attempt.current_question_index,
            'time_remaining_minutes': attempt.time_remaining(),
            'total_questions': len(questions),
            'attempt_number': attempt.attempt_number
        }, status=status.HTTP_200_OK)
    
    except UserExamAttempt.DoesNotExist:
        return Response(
            {'detail': 'Exam attempt not found or not accessible.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get exam questions error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch exam questions.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def submit_exam_answer(request, attempt_id):
    """
    Submit answer for a question
    POST /api/exam-attempts/{attempt_id}/submit-answer/
    """
    try:
        attempt = UserExamAttempt.objects.get(
            id=attempt_id,
            user=request.user,
            status='in_progress'
        )
        
        question_id = request.data.get('question_id')
        answer_data = request.data.get('answer_data')
        
        if not question_id:
            return Response(
                {'detail': 'Question ID is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            question = ExamQuestion.objects.get(id=question_id, exam=attempt.exam)
        except ExamQuestion.DoesNotExist:
            return Response(
                {'detail': 'Question not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Create or update user answer
        user_answer, created = UserExamAnswer.objects.get_or_create(
            attempt=attempt,
            question=question,
            defaults={'answered_at': timezone.now()}
        )
        
        # Process answer based on question type
        if question.question_type == 'multiple_choice':
            selected_answer_ids = answer_data if isinstance(answer_data, list) else [answer_data]
            
            # Validate answer IDs
            valid_answers = ExamAnswer.objects.filter(
                id__in=selected_answer_ids,
                question=question
            )
            
            if valid_answers.count() != len(selected_answer_ids):
                return Response(
                    {'detail': 'Invalid answer selection.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user_answer.selected_answers.set(valid_answers)
            user_answer.text_answer = ''
        
        else:
            # Text-based answer
            user_answer.text_answer = str(answer_data) if answer_data else ''
            user_answer.selected_answers.clear()
        
        # Validate and score the answer
        user_answer.validate_and_score()
        
        # Update attempt's current question index
        questions_order = attempt.exam_data.get('questions_order', [])
        try:
            current_index = questions_order.index(str(question.id))
            attempt.current_question_index = max(attempt.current_question_index, current_index + 1)
            attempt.save(update_fields=['current_question_index'])
        except ValueError:
            pass
        
        return Response({
            'message': 'Answer submitted successfully.',
            'is_correct': user_answer.is_correct,
            'points_earned': user_answer.points_earned
        }, status=status.HTTP_200_OK)
    
    except UserExamAttempt.DoesNotExist:
        return Response(
            {'detail': 'Exam attempt not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Submit exam answer error: {str(e)}")
        return Response(
            {'detail': 'Failed to submit answer.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def complete_exam(request, attempt_id):
    """
    Complete an exam attempt
    POST /api/exam-attempts/{attempt_id}/complete/
    """
    try:
        attempt = UserExamAttempt.objects.get(
            id=attempt_id,
            user=request.user,
            status='in_progress'
        )
        
        # Complete the attempt
        attempt.complete_attempt()
        
        # Send completion notification
        EmailService.send_exam_completed_notification(request.user, attempt)
        
        # Check if certificate should be awarded
        if attempt.passed and attempt.exam.exam_type == 'final':
            try:
                certificate, created = ExamCertificate.objects.get_or_create(
                    user=request.user,
                    exam=attempt.exam,
                    defaults={'attempt': attempt}
                )
                
                if created:
                    EmailService.send_certificate_awarded_notification(request.user, certificate)
                    
            except Exception as cert_error:
                logger.error(f"Certificate creation error: {str(cert_error)}")
        
        logger.info(f"Exam completed: {request.user.email} -> {attempt.exam.title} (Score: {attempt.percentage_score}%)")
        
        return Response({
            'message': 'Exam completed successfully.',
            'score': attempt.percentage_score,
            'passed': attempt.passed,
            'correct_answers': attempt.correct_answers,
            'total_questions': attempt.total_questions,
            'time_taken_minutes': attempt.time_taken_minutes,
            'can_review': attempt.can_review()
        }, status=status.HTTP_200_OK)
    
    except UserExamAttempt.DoesNotExist:
        return Response(
            {'detail': 'Exam attempt not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Complete exam error: {str(e)}")
        return Response(
            {'detail': 'Failed to complete exam.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_exam_results(request, attempt_id):
    """
    Get exam results and review
    GET /api/exam-attempts/{attempt_id}/results/
    """
    try:
        attempt = UserExamAttempt.objects.select_related('exam').get(
            id=attempt_id,
            user=request.user,
            status='completed'
        )
        
        if not attempt.can_review():
            return Response(
                {'detail': 'Review is not allowed for this exam.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get user answers with question details
        user_answers = UserExamAnswer.objects.filter(
            attempt=attempt
        ).select_related('question').prefetch_related('selected_answers', 'question__answers')
        
        questions_data = []
        for user_answer in user_answers:
            question = user_answer.question
            
            question_data = {
                'id': str(question.id),
                'question_text': question.question_text,
                'question_type': question.question_type,
                'points': question.points,
                'explanation': question.explanation,
                'user_answer': {},
                'correct_answers': [],
                'is_correct': user_answer.is_correct,
                'points_earned': user_answer.points_earned
            }
            
            # Add user's answer
            if question.question_type == 'multiple_choice':
                question_data['user_answer'] = [
                    {
                        'id': str(ans.id),
                        'text': ans.answer_text
                    }
                    for ans in user_answer.selected_answers.all()
                ]
            else:
                question_data['user_answer'] = user_answer.text_answer
            
            # Add correct answers if allowed
            if attempt.exam.show_correct_answers:
                question_data['correct_answers'] = [
                    {
                        'id': str(ans.id),
                        'text': ans.answer_text
                    }
                    for ans in question.answers.filter(is_correct=True)
                ]
            
            questions_data.append(question_data)
        
        return Response({
            'attempt': UserExamAttemptSerializer(attempt).data,
            'questions': questions_data,
            'exam_title': attempt.exam.title,
            'show_correct_answers': attempt.exam.show_correct_answers
        }, status=status.HTTP_200_OK)
    
    except UserExamAttempt.DoesNotExist:
        return Response(
            {'detail': 'Exam results not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Get exam results error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch exam results.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# USER DASHBOARD AND ANALYTICS

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_dashboard(request):
    """
    Get user dashboard data
    GET /api/users/dashboard/
    """
    try:
        user = request.user
        
        # Get course enrollments and progress
        enrollments = CourseEnrollment.objects.filter(
            user=user,
            is_active=True
        ).select_related('course')
        
        progress_data = UserCourseProgress.objects.filter(user=user).select_related('course')
        
        # Calculate statistics
        total_courses = enrollments.count()
        completed_courses = progress_data.filter(progress_percentage=100).count()
        in_progress_courses = progress_data.filter(
            progress_percentage__gt=0,
            progress_percentage__lt=100
        ).count()
        
        # Get recent activity
        recent_progress = progress_data.order_by('-last_accessed')[:5]
        recent_enrollments = enrollments.order_by('-enrolled_at')[:5]
        
        # Get exam attempts
        recent_attempts = UserExamAttempt.objects.filter(
            user=user
        ).select_related('exam', 'exam__course').order_by('-started_at')[:5]
        
        # Get certificates
        certificates = ExamCertificate.objects.filter(
            user=user,
            is_valid=True
        ).select_related('exam', 'exam__course').order_by('-issued_at')
        
        # Calculate total spent
        total_spent = enrollments.filter(
            payment_status='completed'
        ).aggregate(
            total=Sum('amount_paid')
        )['total'] or 0
        
        return Response({
            'user_info': {
                'name': user.full_name,
                'email': user.email,
                'joined_date': user.date_joined
            },
            'statistics': {
                'total_courses': total_courses,
                'completed_courses': completed_courses,
                'in_progress_courses': in_progress_courses,
                'completion_rate': round((completed_courses / total_courses * 100), 2) if total_courses > 0 else 0,
                'total_spent': float(total_spent),
                'certificates_earned': certificates.count()
            },
            'recent_activity': {
                'course_progress': UserCourseProgressSerializer(recent_progress, many=True).data,
                'enrollments': CourseEnrollmentSerializer(recent_enrollments, many=True).data,
                'exam_attempts': UserExamAttemptSerializer(recent_attempts, many=True).data
            },
            'certificates': [
                {
                    'id': str(cert.id),
                    'exam_title': cert.exam.title,
                    'course_title': cert.exam.course.title,
                    'issued_at': cert.issued_at,
                    'certificate_number': cert.certificate_number,
                    'certificate_url': cert.certificate_url
                }
                for cert in certificates
            ]
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"User dashboard error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch dashboard data.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


# SEARCH AND RECOMMENDATIONS

@api_view(['GET'])
@permission_classes([AllowAny])
def search_courses(request):
    """
    Advanced course search
    GET /api/courses/search/
    """
    try:
        query = request.GET.get('q', '').strip()
        
        if not query or len(query) < 3:
            return Response(
                {'detail': 'Search query must be at least 3 characters long.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Search in courses
        courses = Course.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(category__icontains=query),
            is_active=True
        ).select_related('created_by')[:20]
        
        # Search in exam titles (if user is authenticated)
        exams_data = []
        if request.user.is_authenticated:
            # Get exams from courses user is enrolled in
            enrolled_courses = CourseEnrollment.objects.filter(
                user=request.user,
                is_active=True,
                payment_status='completed'
            ).values_list('course_id', flat=True)
            
            exams = CourseExam.objects.filter(
                Q(title__icontains=query) |
                Q(description__icontains=query),
                course_id__in=enrolled_courses,
                is_active=True,
                is_published=True
            ).select_related('course')[:10]
            
            exams_data = [
                {
                    'id': str(exam.id),
                    'title': exam.title,
                    'course_title': exam.course.title,
                    'exam_type': exam.exam_type,
                    'total_questions': exam.total_questions
                }
                for exam in exams
            ]
        
        return Response({
            'query': query,
            'courses': CourseSerializer(courses, many=True).data,
            'exams': exams_data,
            'total_results': courses.count() + len(exams_data)
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Search courses error: {str(e)}")
        return Response(
            {'detail': 'Search failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_recommendations(request):
    """
    Get personalized course recommendations
    GET /api/courses/recommendations/
    """
    try:
        user = request.user
        
        # Get user's enrolled courses
        enrolled_courses = CourseEnrollment.objects.filter(
            user=user,
            is_active=True
        ).values_list('course', flat=True)
        
        # Get user's completed courses
        completed_courses = UserCourseProgress.objects.filter(
            user=user,
            progress_percentage=100
        ).values_list('course', flat=True)
        
        # Get categories from user's courses
        user_categories = Course.objects.filter(
            id__in=enrolled_courses
        ).values_list('category', flat=True).distinct()
        
        recommendations = []
        
        # Recommend courses in similar categories
        if user_categories:
            similar_courses = Course.objects.filter(
                category__in=user_categories,
                is_active=True,
                is_featured=True
            ).exclude(id__in=enrolled_courses)[:5]
            
            recommendations.extend(similar_courses)
        
        # Recommend popular courses if not enough similar ones
        if len(recommendations) < 5:
            popular_courses = Course.objects.filter(
                is_active=True,
                is_featured=True
            ).exclude(id__in=enrolled_courses).annotate(
                enrollment_count=Count('enrollments')
            ).order_by('-enrollment_count')[:10]
            
            for course in popular_courses:
                if course not in recommendations and len(recommendations) < 8:
                    recommendations.append(course)
        
        return Response({
            'recommendations': CourseSerializer(recommendations, many=True).data,
            'reason': 'Based on your course preferences and popular courses'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Get recommendations error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch recommendations.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )