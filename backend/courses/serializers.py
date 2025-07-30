# courses/serializers.py
from rest_framework import serializers
from django.utils import timezone
from cloudinary.utils import cloudinary_url
from .models import (
    Course, UserCourseProgress, CourseEnrollment, CourseCategory, CourseReview,
    CourseExam, ExamQuestion, ExamAnswer, UserExamAttempt, UserExamAnswer, ExamCertificate,
    CourseSection, CourseLesson, UserLessonProgress
)
from difflib import get_close_matches
from users.models import User


class CourseSerializer(serializers.ModelSerializer):
    """Serializer for Course model - used for listing and details"""
    completion_rate = serializers.SerializerMethodField()
    average_progress = serializers.SerializerMethodField()
    total_enrollments = serializers.SerializerMethodField()
    total_revenue = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    updated_by_name = serializers.CharField(source='updated_by.full_name', read_only=True)
    video_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    effective_price = serializers.SerializerMethodField()
    is_discount_active = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'description', 'video_source', 'video_url', 'thumbnail_url',
            'course_type', 'price', 'currency', 'effective_price',
            'has_discount', 'discount_percentage', 'is_discount_active',
            'duration_minutes', 'difficulty_level', 'category',
            'estimated_duration_hours', 'requirements', 'what_you_will_learn',
            'is_active', 'is_featured', 'created_at', 'updated_at', 
            'created_by_name', 'updated_by_name', 'completion_rate', 
            'average_progress', 'total_enrollments', 'total_revenue',
            'average_rating', 'review_count'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'completion_rate', 
            'average_progress', 'total_enrollments', 'total_revenue',
            'effective_price', 'is_discount_active', 'average_rating', 'review_count'
        ]
    
    def get_video_url(self, obj):
        """Get the appropriate video URL based on source"""
        try:
            if obj.video_source == 'url' and obj.video_url:
                return obj.video_url
            elif obj.video_source == 'upload' and obj.video_file:
                # Handle both CloudinaryField and string cases
                if hasattr(obj.video_file, 'url'):
                    return obj.video_file.url
                else:
                    return str(obj.video_file)
            return None
        except (AttributeError, ValueError):
            return None
    
    def get_thumbnail_url(self, obj):
        """Get thumbnail URL if exists"""
        try:
            if obj.thumbnail and hasattr(obj.thumbnail, 'url'):
                return obj.thumbnail.url
            elif obj.thumbnail:
                return str(obj.thumbnail)
            return None
        except (AttributeError, ValueError):
            return None
    
    def get_completion_rate(self, obj):
        return obj.get_completion_rate()
    
    def get_average_progress(self, obj):
        return obj.get_average_progress()
    
    def get_total_enrollments(self, obj):
        return obj.user_progress.count()
    
    def get_total_revenue(self, obj):
        return float(obj.get_total_revenue())
    
    def get_effective_price(self, obj):
        return obj.get_effective_price()
    
    def get_is_discount_active(self, obj):
        return obj.is_discount_active()
    
    def get_average_rating(self, obj):
        from django.db.models import Avg
        avg_rating = obj.reviews.filter(is_approved=True).aggregate(avg=Avg('rating'))['avg']
        return round(avg_rating, 1) if avg_rating else 0
    
    def get_review_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()


class CourseCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating courses (Admin only)"""

    category = serializers.SlugRelatedField(
        slug_field='slug',  # Accept category slug in JSON
        queryset=CourseCategory.objects.all()
    )
    
    class Meta:
        model = Course
        fields = [
            'title', 'description', 'video_source', 'video_url', 'video_file', 
            'thumbnail', 'course_type', 'price', 'currency',
            'has_discount', 'discount_percentage', 'discount_start_date', 'discount_end_date',
            'duration_minutes', 'difficulty_level', 'category',
            'estimated_duration_hours', 'requirements', 'what_you_will_learn',
            'is_active', 'is_featured', 'prerequisites'
        ]

    def validate_category(self, value):
        """Ensure category exists, default to 'all' if missing."""
        slug = self.initial_data.get('category')
    
        # If no category provided → default to 'all'
        if not slug:
            try:
                return CourseCategory.objects.get(slug="all")
            except CourseCategory.DoesNotExist:
                raise serializers.ValidationError(
                    "Default category 'all' does not exist. Please create it first."
                )
    
        # Try to get the provided category
        try:
            return CourseCategory.objects.get(slug=slug)
        except CourseCategory.DoesNotExist:
            # Suggest similar categories
            all_slugs = list(CourseCategory.objects.values_list('slug', flat=True))
            suggestions = get_close_matches(slug, all_slugs, n=3, cutoff=0.3)
            suggestion_msg = f" Did you mean: {', '.join(suggestions)}?" if suggestions else " No similar categories found."
    
            raise serializers.ValidationError(
                f"Category '{slug}' is not valid.{suggestion_msg}"
            )
    
    def validate_title(self, value):
        """Ensure course title is unique"""
        instance = getattr(self, 'instance', None)
        if Course.objects.filter(title=value).exclude(pk=instance.pk if instance else None).exists():
            raise serializers.ValidationError("A course with this title already exists.")
        return value

    def validate(self, data):
        """Custom validation for video sources and pricing with safe fallbacks"""

        # --- VIDEO ---
        video_source = data.get('video_source', getattr(self.instance, 'video_source', 'url'))
        video_url = data.get('video_url', getattr(self.instance, 'video_url', None))
        video_file = data.get('video_file', getattr(self.instance, 'video_file', None))

        if video_source == 'url':
            if not video_url:
                raise serializers.ValidationError({
                    'video_url': 'Video URL is required when video source is URL.'
                })

        elif video_source == 'upload':
            # Allow either a real file upload or a Cloudinary public_id string
            if not video_file:
                if not self.instance or not self.instance.video_file:
                    raise serializers.ValidationError({
                        'video_file': 'Video file or Cloudinary public_id is required when video source is upload.'
                    })
            else:
                # If it's a string, treat it as Cloudinary public_id
                if isinstance(video_file, str):
                    data['video_file'] = video_file

        if video_url:
            valid_domains = ['youtube.com', 'youtu.be', 'vimeo.com', 'wistia.com', 'cloudinary.com']
            if not any(domain in video_url.lower() for domain in valid_domains):
                pass  # Allow other domains

        # --- PRICING ---
        course_type = data.get('course_type', getattr(self.instance, 'course_type', 'free'))
        price = data.get('price', getattr(self.instance, 'price', 0.00))

        if course_type == 'free' and price > 0:
            raise serializers.ValidationError({
                'price': 'Free courses cannot have a price greater than 0.'
            })

        if course_type in ['paid', 'premium'] and price <= 0:
            raise serializers.ValidationError({
                'price': 'Paid courses must have a price greater than 0.'
            })

        # --- DISCOUNT ---
        has_discount = data.get('has_discount', getattr(self.instance, 'has_discount', False))
        discount_percentage = data.get('discount_percentage', getattr(self.instance, 'discount_percentage', 0))
        discount_start_date = data.get('discount_start_date', getattr(self.instance, 'discount_start_date', None))
        discount_end_date = data.get('discount_end_date', getattr(self.instance, 'discount_end_date', None))

        if has_discount:
            if discount_percentage <= 0 or discount_percentage > 100:
                raise serializers.ValidationError({
                    'discount_percentage': 'Discount percentage must be between 1 and 100.'
                })
            if discount_start_date and discount_end_date:
                if discount_start_date >= discount_end_date:
                    raise serializers.ValidationError({
                        'discount_end_date': 'Discount start date must be before end date.'
                    })

        return data

    
    def create(self, validated_data):
        # Set created_by from request user
        user = self.context['request'].user
        validated_data['created_by'] = user
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Set updated_by from request user
        user = self.context['request'].user
        validated_data['updated_by'] = user
        return super().update(instance, validated_data)
    

# ADDITIONAL SERIALIZERS FOR SECTIONS & LESSONS
class CourseSectionSerializer(serializers.ModelSerializer):
    """Serializer for course sections"""
    lessons_count = serializers.SerializerMethodField()
    total_duration_display = serializers.SerializerMethodField()
    completion_rate = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    
    class Meta:
        model = CourseSection
        fields = [
            'id', 'title', 'description', 'order', 'is_active', 'is_preview',
            'required_previous_completion', 'total_lessons', 'total_duration_seconds',
            'total_duration_display', 'lessons_count', 'completion_rate',
            'created_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_lessons', 'total_duration_seconds', 'created_at', 
            'updated_at', 'lessons_count', 'completion_rate', 'total_duration_display'
        ]
    
    def get_lessons_count(self, obj):
        return obj.lessons.filter(is_active=True).count()
    
    def get_total_duration_display(self, obj):
        if not obj.total_duration_seconds:
            return "0:00"
        
        hours = obj.total_duration_seconds // 3600
        minutes = (obj.total_duration_seconds % 3600) // 60
        seconds = obj.total_duration_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    def get_completion_rate(self, obj):
        # This would need user context to be meaningful
        # For admin views, we might want average completion rate
        try:
            if hasattr(obj, 'get_completion_rate'):
                return obj.get_completion_rate()
        except:
            pass
        return 0


class CourseSectionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating course sections"""
    
    class Meta:
        model = CourseSection
        fields = [
            'title', 'description', 'order', 'is_active', 'is_preview',
            'required_previous_completion'
        ]
    
    def validate_title(self, value):
        """Ensure section title is unique within course"""
        course = self.context.get('course') or (self.instance.course if self.instance else None)
        instance = getattr(self, 'instance', None)
        
        if course:
            queryset = CourseSection.objects.filter(course=course, title=value)
            if instance:
                queryset = queryset.exclude(pk=instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("A section with this title already exists in this course.")
        
        return value
    
    def validate_order(self, value):
        if value < 0:
            raise serializers.ValidationError("Order must be a positive number.")
        return value


class CourseLessonSerializer(serializers.ModelSerializer):
    """Serializer for course lessons"""
    section_title = serializers.CharField(source='section.title', read_only=True)
    video_url = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    is_accessible = serializers.SerializerMethodField()
    progress_stats = serializers.SerializerMethodField()
    next_lesson_id = serializers.SerializerMethodField()
    previous_lesson_id = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseLesson
        fields = [
            'id', 'section_title', 'title', 'description', 'lesson_type', 'order',
            'is_active', 'video_source', 'video_url', 'thumbnail_url', 'text_content',
            'attachments', 'duration_seconds', 'duration_display', 'is_preview',
            'is_downloadable', 'require_completion', 'minimum_watch_percentage',
            'auto_play_next', 'keywords', 'created_by_name', 'created_at', 'updated_at',
            'is_accessible', 'progress_stats', 'next_lesson_id', 'previous_lesson_id'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'section_title', 'video_url',
            'thumbnail_url', 'duration_display', 'is_accessible', 'progress_stats',
            'next_lesson_id', 'previous_lesson_id'
        ]
    
    def get_video_url(self, obj):
        """Get the appropriate video URL based on source"""
        return obj.get_video_url()
    
    def get_thumbnail_url(self, obj):
        """Get thumbnail URL if exists"""
        if obj.thumbnail:
            # Handle both CloudinaryField and plain URL string
            if hasattr(obj.thumbnail, 'url'):
                return obj.thumbnail.url
            elif isinstance(obj.thumbnail, str):
                return obj.thumbnail
        return None
    
    def get_duration_display(self, obj):
        """Get formatted duration"""
        return obj.get_duration_display()
    
    def get_is_accessible(self, obj):
        """Check if lesson is accessible (requires user context)"""
        user = self.context.get('user')
        if user:
            return obj.is_accessible_by_user(user)
        return obj.is_preview
    
    def get_progress_stats(self, obj):
        """Get lesson progress statistics"""
        total_views = obj.user_progress.count()
        completed_views = obj.user_progress.filter(is_completed=True).count()
        
        return {
            'total_views': total_views,
            'completed_views': completed_views,
            'completion_rate': round((completed_views / total_views * 100), 2) if total_views > 0 else 0
        }
    
    def get_next_lesson_id(self, obj):
        next_lesson = obj.get_next_lesson()
        return str(next_lesson.id) if next_lesson else None
    
    def get_previous_lesson_id(self, obj):
        previous_lesson = obj.get_previous_lesson()
        return str(previous_lesson.id) if previous_lesson else None


class CourseLessonCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating course lessons"""
    
    class Meta:
        model = CourseLesson
        fields = [
            'title', 'description', 'lesson_type', 'order', 'is_active',
            'video_source', 'video_url', 'video_file', 'video_streaming_url',
            'text_content', 'thumbnail', 'attachments', 'duration_seconds',
            'is_preview', 'is_downloadable', 'require_completion',
            'minimum_watch_percentage', 'auto_play_next', 'keywords',
            'notes_for_instructor'
        ]
    
    def validate_title(self, value):
        """Ensure lesson title is unique within section"""
        section = self.context.get('section') or (self.instance.section if self.instance else None)
        instance = getattr(self, 'instance', None)
        
        if section:
            queryset = CourseLesson.objects.filter(section=section, title=value)
            if instance:
                queryset = queryset.exclude(pk=instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("A lesson with this title already exists in this section.")
        
        return value
    
    def validate_minimum_watch_percentage(self, value):
        if value < 1 or value > 100:
            raise serializers.ValidationError("Minimum watch percentage must be between 1 and 100.")
        return value
    
    def validate_duration_seconds(self, value):
        if value is not None and value < 0:
            raise serializers.ValidationError("Duration cannot be negative.")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        lesson_type = data.get('lesson_type', 'video')
        
        # Video lesson validation
        if lesson_type == 'video':
            video_source = data.get('video_source', 'url')
            video_url = data.get('video_url')
            video_file = data.get('video_file')
            video_streaming_url = data.get('video_streaming_url')
            
            if video_source == 'url' and not video_url:
                raise serializers.ValidationError({
                    'video_url': 'Video URL is required when video source is URL.'
                })
            elif video_source == 'upload' and not video_file:
                # Check if we're updating and already have a video file
                instance = getattr(self, 'instance', None)
                if not instance or not instance.video_file:
                    raise serializers.ValidationError({
                        'video_file': 'Video file is required when video source is upload.'
                    })
            elif video_source == 'streaming' and not video_streaming_url:
                raise serializers.ValidationError({
                    'video_streaming_url': 'Streaming URL is required when video source is streaming.'
                })
        
        # Text lesson validation
        elif lesson_type == 'text':
            text_content = data.get('text_content', '').strip()
            if not text_content:
                raise serializers.ValidationError({
                    'text_content': 'Text content is required for text lessons.'
                })
            
            if len(text_content) < 50:
                raise serializers.ValidationError({
                    'text_content': 'Text content must be at least 50 characters long.'
                })
        
        return data


class UserLessonProgressSerializer(serializers.ModelSerializer):
    """Serializer for user lesson progress"""
    lesson_title = serializers.CharField(source='lesson.title', read_only=True)
    lesson_type = serializers.CharField(source='lesson.lesson_type', read_only=True)
    lesson_duration = serializers.IntegerField(source='lesson.duration_seconds', read_only=True)
    section_title = serializers.CharField(source='lesson.section.title', read_only=True)
    course_title = serializers.CharField(source='lesson.section.course.title', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    watch_percentage_display = serializers.SerializerMethodField()
    current_position_display = serializers.SerializerMethodField()
    watch_time_display = serializers.SerializerMethodField()
    
    class Meta:
        model = UserLessonProgress
        fields = [
            'id', 'user_name', 'user_email', 'lesson_title', 'lesson_type',
            'lesson_duration', 'section_title', 'course_title',
            'watch_time_seconds', 'watch_time_display', 'current_position_seconds',
            'current_position_display', 'watch_percentage', 'watch_percentage_display',
            'is_completed', 'completed_at', 'first_accessed', 'last_accessed',
            'access_count', 'bookmarks', 'notes', 'rating', 'feedback'
        ]
        read_only_fields = [
            'id', 'first_accessed', 'last_accessed', 'user_name', 'user_email',
            'lesson_title', 'lesson_type', 'lesson_duration', 'section_title',
            'course_title', 'watch_percentage_display', 'current_position_display',
            'watch_time_display'
        ]
    
    def get_watch_percentage_display(self, obj):
        return f"{obj.watch_percentage}%"
    
    def get_current_position_display(self, obj):
        return UserLessonProgress.format_time(obj.current_position_seconds)
    
    def get_watch_time_display(self, obj):
        return UserLessonProgress.format_time(obj.watch_time_seconds)


class UserLessonProgressUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user lesson progress"""
    
    class Meta:
        model = UserLessonProgress
        fields = [
            'watch_time_seconds', 'current_position_seconds', 'watch_percentage',
            'notes', 'rating', 'feedback', 'bookmarks'
        ]
    
    def validate_watch_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Watch percentage must be between 0 and 100.")
        return value
    
    def validate_current_position_seconds(self, value):
        if value < 0:
            raise serializers.ValidationError("Current position cannot be negative.")
        return value
    
    def validate_watch_time_seconds(self, value):
        if value < 0:
            raise serializers.ValidationError("Watch time cannot be negative.")
        return value
    
    def validate_rating(self, value):
        if value is not None and (value < 1 or value > 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value
    
    def validate_bookmarks(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Bookmarks must be a list.")
        
        for bookmark in value:
            if not isinstance(bookmark, dict):
                raise serializers.ValidationError("Each bookmark must be a dictionary.")
            
            required_fields = ['position_seconds', 'title']
            for field in required_fields:
                if field not in bookmark:
                    raise serializers.ValidationError(f"Bookmark missing required field: {field}")
            
            if not isinstance(bookmark['position_seconds'], (int, float)) or bookmark['position_seconds'] < 0:
                raise serializers.ValidationError("Bookmark position_seconds must be a non-negative number.")
        
        return value


class CourseProgressDetailSerializer(serializers.ModelSerializer):
    """Enhanced serializer for detailed course progress with sections and lessons"""
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_description = serializers.CharField(source='course.description', read_only=True)
    course_thumbnail_url = serializers.SerializerMethodField()
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    sections_progress = serializers.SerializerMethodField()
    current_lesson = serializers.SerializerMethodField()
    next_lesson_to_study = serializers.SerializerMethodField()
    time_spent_display = serializers.SerializerMethodField()
    completion_status = serializers.SerializerMethodField()
    
    class Meta:
        model = UserCourseProgress
        fields = [
            'id', 'user_name', 'user_email', 'course_title', 'course_description',
            'course_thumbnail_url', 'progress_percentage', 'started_at', 'completed_at',
            'last_accessed', 'sections_completed', 'current_section_id', 'current_lesson_id',
            'total_watch_time_seconds', 'time_spent_display', 'notes', 'rating',
            'feedback', 'sections_progress', 'current_lesson', 'next_lesson_to_study',
            'completion_status'
        ]
        read_only_fields = [
            'id', 'started_at', 'last_accessed', 'user_name', 'user_email',
            'course_title', 'course_description', 'course_thumbnail_url',
            'sections_progress', 'current_lesson', 'next_lesson_to_study',
            'time_spent_display', 'completion_status'
        ]
    
    def get_course_thumbnail_url(self, obj):
        if obj.course.thumbnail:
            return obj.course.thumbnail.url
        return None
    
    def get_sections_progress(self, obj):
        return obj.get_progress_by_section()
    
    def get_current_lesson(self, obj):
        lesson = obj.get_current_lesson()
        if lesson:
            return {
                'id': str(lesson.id),
                'title': lesson.title,
                'lesson_type': lesson.lesson_type,
                'section_title': lesson.section.title,
                'order': lesson.order
            }
        return None
    
    def get_next_lesson_to_study(self, obj):
        current_lesson = obj.get_current_lesson()
        if current_lesson:
            next_lesson = current_lesson.get_next_lesson()
            if next_lesson:
                return {
                    'id': str(next_lesson.id),
                    'title': next_lesson.title,
                    'lesson_type': next_lesson.lesson_type,
                    'section_title': next_lesson.section.title
                }
        return None
    
    def get_time_spent_display(self, obj):
        return UserLessonProgress.format_time(obj.total_watch_time_seconds)
    
    def get_completion_status(self, obj):
        if obj.progress_percentage == 100:
            return 'completed'
        elif obj.progress_percentage > 0:
            return 'in_progress'
        else:
            return 'not_started'


class LessonVideoUploadSerializer(serializers.Serializer):
    """Serializer for lesson video upload"""
    video_file = serializers.FileField()
    lesson_id = serializers.UUIDField(required=False)
    
    def validate_video_file(self, value):
        # Check file size (max 1GB)
        max_size = 1024 * 1024 * 1024  # 1GB
        if value.size > max_size:
            raise serializers.ValidationError("Video file size cannot exceed 1GB.")
        
        # Check file type
        allowed_types = [
            'video/mp4', 'video/avi', 'video/mov', 'video/wmv', 
            'video/flv', 'video/webm', 'video/mkv'
        ]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError(
                "Only video files (MP4, AVI, MOV, WMV, FLV, WebM, MKV) are allowed."
            )
        
        return value


class SectionReorderSerializer(serializers.Serializer):
    """Serializer for reordering sections"""
    section_orders = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        help_text="List of {'section_id': 'new_order'} dictionaries"
    )
    
    def validate_section_orders(self, value):
        if not value:
            raise serializers.ValidationError("Section orders list cannot be empty.")
        
        section_ids = []
        orders = []
        
        for item in value:
            if 'section_id' not in item or 'new_order' not in item:
                raise serializers.ValidationError(
                    "Each item must have 'section_id' and 'new_order' fields."
                )
            
            section_id = item['section_id']
            try:
                new_order = int(item['new_order'])
                if new_order < 1:
                    raise ValueError()
            except (ValueError, TypeError):
                raise serializers.ValidationError("new_order must be a positive integer.")
            
            if section_id in section_ids:
                raise serializers.ValidationError(f"Duplicate section_id: {section_id}")
            
            if new_order in orders:
                raise serializers.ValidationError(f"Duplicate order: {new_order}")
            
            section_ids.append(section_id)
            orders.append(new_order)
        
        return value


class LessonReorderSerializer(serializers.Serializer):
    """Serializer for reordering lessons within a section"""
    lesson_orders = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        help_text="List of {'lesson_id': 'new_order'} dictionaries"
    )
    
    def validate_lesson_orders(self, value):
        if not value:
            raise serializers.ValidationError("Lesson orders list cannot be empty.")
        
        lesson_ids = []
        orders = []
        
        for item in value:
            if 'lesson_id' not in item or 'new_order' not in item:
                raise serializers.ValidationError(
                    "Each item must have 'lesson_id' and 'new_order' fields."
                )
            
            lesson_id = item['lesson_id']
            try:
                new_order = int(item['new_order'])
                if new_order < 1:
                    raise ValueError()
            except (ValueError, TypeError):
                raise serializers.ValidationError("new_order must be a positive integer.")
            
            if lesson_id in lesson_ids:
                raise serializers.ValidationError(f"Duplicate lesson_id: {lesson_id}")
            
            if new_order in orders:
                raise serializers.ValidationError(f"Duplicate order: {new_order}")
            
            lesson_ids.append(lesson_id)
            orders.append(new_order)
        
        return value


class CourseStructureSerializer(serializers.ModelSerializer):
    """Serializer for complete course structure (sections + lessons)"""
    sections = CourseSectionSerializer(many=True, read_only=True)
    total_duration_display = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'title', 'description', 'total_sections', 'total_lessons',
            'total_duration_seconds', 'total_duration_display', 'sections'
        ]
        read_only_fields = ['id', 'total_sections', 'total_lessons', 'total_duration_seconds']
    
    def get_total_duration_display(self, obj):
        if not obj.total_duration_seconds:
            return "0:00:00"
        
        hours = obj.total_duration_seconds // 3600
        minutes = (obj.total_duration_seconds % 3600) // 60
        seconds = obj.total_duration_seconds % 60
        
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    
    def to_representation(self, instance):
        """Add lessons to each section"""
        data = super().to_representation(instance)
        
        # Add lessons to each section
        for section_data in data['sections']:
            section_id = section_data['id']
            try:
                section = CourseSection.objects.get(id=section_id)
                lessons = section.lessons.filter(is_active=True).order_by('order')
                section_data['lessons'] = CourseLessonSerializer(lessons, many=True).data
            except CourseSection.DoesNotExist:
                section_data['lessons'] = []
        
        return data


class UserCourseProgressSerializer(serializers.ModelSerializer):
    """Serializer for user course progress"""
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_description = serializers.CharField(source='course.description', read_only=True)
    course_video_url = serializers.SerializerMethodField()
    course_thumbnail_url = serializers.SerializerMethodField()
    course_category = serializers.CharField(source='course.category', read_only=True)
    course_difficulty = serializers.CharField(source='course.difficulty_level', read_only=True)
    course_price = serializers.SerializerMethodField()
    is_completed = serializers.SerializerMethodField()
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = UserCourseProgress
        fields = [
            'id', 'user_id', 'user_name', 'user_email', 'course_id', 
            'course_title', 'course_description', 'course_video_url', 'course_thumbnail_url',
            'course_category', 'course_difficulty', 'course_price',
            'progress_percentage', 'started_at', 'completed_at', 'last_accessed',
            'sections_completed', 'notes', 'rating', 'feedback', 'is_completed'
        ]
        read_only_fields = ['id', 'user_id', 'started_at', 'last_accessed']
    
    def get_course_video_url(self, obj):
        """Get course video URL using the model method"""
        try:
            if obj.course.video_source == 'url' and obj.course.video_url:
                return obj.course.video_url
            elif obj.course.video_source == 'upload' and obj.course.video_file:
                # Handle both CloudinaryField and string cases
                if hasattr(obj.course.video_file, 'url'):
                    return obj.course.video_file.url
                else:
                    return str(obj.course.video_file)
            return None
        except (AttributeError, ValueError):
            return None
    
    def get_course_thumbnail_url(self, obj):
        """Get course thumbnail URL"""
        try:
            if obj.course.thumbnail and hasattr(obj.course.thumbnail, 'url'):
                return obj.course.thumbnail.url
            elif obj.course.thumbnail:
                return str(obj.course.thumbnail)
            return None
        except (AttributeError, ValueError):
            return None
    
    def get_course_price(self, obj):
        return obj.course.get_effective_price()
    
    def get_is_completed(self, obj):
        return obj.is_completed()


class UserCourseProgressUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user course progress"""
    
    class Meta:
        model = UserCourseProgress
        fields = ['progress_percentage', 'sections_completed', 'notes', 'rating', 'feedback']
    
    def validate_progress_percentage(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Progress percentage must be between 0 and 100.")
        return value
    
    def validate_rating(self, value):
        if value is not None and (value < 1 or value > 5):
            raise serializers.ValidationError("Rating must be between 1 and 5.")
        return value


class CourseEnrollmentSerializer(serializers.ModelSerializer):
    """Serializer for course enrollments"""
    course = CourseSerializer(read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    is_expired = serializers.SerializerMethodField()
    is_paid = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseEnrollment
        fields = [
            'id', 'user_name', 'user_email', 'course', 'enrolled_at',
            'is_active', 'expires_at', 'payment_status', 'payment_id', 
            'payment_method', 'amount_paid', 'currency', 'discount_applied',
            'is_expired', 'is_paid'
        ]
        read_only_fields = ['id', 'enrolled_at']
    
    def get_is_expired(self, obj):
        return obj.is_expired()
    
    def get_is_paid(self, obj):
        return obj.is_paid()


class CourseCategorySerializer(serializers.ModelSerializer):
    """Serializer for course categories"""
    courses_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseCategory
        fields = ['id', 'name', 'description', 'slug', 'is_active', 'order', 'courses_count']
        read_only_fields = ['id', 'slug']  # slug is now auto-generated
    
    def get_courses_count(self, obj):
        try:
            if hasattr(obj, 'get_courses_count'):
                return obj.get_courses_count()
            # Fallback
            return obj.courses.filter(is_active=True).count()
        except AttributeError:
            return 0


class CourseReviewSerializer(serializers.ModelSerializer):
    """Serializer for course reviews"""
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    
    class Meta:
        model = CourseReview
        fields = [
            'id', 'user_name', 'course_title', 'rating', 'review_text',
            'is_approved', 'is_featured', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class CourseStatsSerializer(serializers.Serializer):
    """Serializer for course statistics (Admin dashboard)"""
    total_courses = serializers.IntegerField()
    active_courses = serializers.IntegerField()
    free_courses = serializers.IntegerField()
    paid_courses = serializers.IntegerField()
    total_enrollments = serializers.IntegerField()
    paid_enrollments = serializers.IntegerField()
    completed_courses = serializers.IntegerField()
    total_revenue = serializers.FloatField()
    average_completion_rate = serializers.FloatField()
    courses_by_category = serializers.DictField()
    recent_enrollments = serializers.IntegerField()


class UserProgressSummarySerializer(serializers.Serializer):
    """Serializer for user progress summary"""
    total_courses = serializers.IntegerField()
    completed_courses = serializers.IntegerField()
    in_progress_courses = serializers.IntegerField()
    not_started_courses = serializers.IntegerField()
    completion_percentage = serializers.FloatField()
    total_spent = serializers.FloatField()
    recent_activity = serializers.ListField()


class VideoUploadSerializer(serializers.Serializer):
    """Serializer for video upload"""
    video_file = serializers.FileField()
    
    def validate_video_file(self, value):
        # Check file size (max 500MB)
        max_size = 500 * 1024 * 1024  # 500MB
        if value.size > max_size:
            raise serializers.ValidationError("Video file size cannot exceed 500MB.")
        
        # Check file type
        allowed_types = ['video/mp4', 'video/avi', 'video/mov', 'video/wmv', 'video/flv']
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only video files (MP4, AVI, MOV, WMV, FLV) are allowed.")
        
        return value


class CourseExamSerializer(serializers.ModelSerializer):
    """Serializer for course exams"""
    course_title = serializers.CharField(source='course.title', read_only=True)
    created_by_name = serializers.CharField(source='created_by.full_name', read_only=True)
    questions_count = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()
    is_available = serializers.SerializerMethodField()
    pass_rate = serializers.SerializerMethodField()
    average_score = serializers.SerializerMethodField()
    attempts_count = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseExam
        fields = [
            'id', 'course_title', 'title', 'description', 'instructions',
            'exam_type', 'difficulty_level', 'total_questions', 'questions_count',
            'time_limit_minutes', 'duration_display', 'passing_score', 'max_attempts',
            'shuffle_questions', 'shuffle_answers', 'show_results_immediately',
            'show_correct_answers', 'allow_review', 'required_course_progress',
            'is_active', 'is_published', 'is_available', 'available_from', 'available_until',
            'pass_rate', 'average_score', 'attempts_count', 'created_by_name', 
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'total_questions', 'questions_count', 'duration_display', 
            'is_available', 'pass_rate', 'average_score', 'attempts_count',
            'created_at', 'updated_at', 'course_title', 'created_by_name'
        ]
    
    def get_questions_count(self, obj):
        return obj.questions.filter(is_active=True).count()
    
    def get_duration_display(self, obj):
        return obj.get_duration_display()
    
    def get_is_available(self, obj):
        return obj.is_available()
    
    def get_pass_rate(self, obj):
        return obj.get_pass_rate()
    
    def get_average_score(self, obj):
        return obj.get_average_score()
    
    def get_attempts_count(self, obj):
        return obj.attempts.count()
    
class CourseMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'title']  # You can add more if needed


class UserMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'full_name', 'email']  # You can adjust fields
    

class CourseExamCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating course exams"""

    course = CourseMinimalSerializer(read_only=True)
    created_by = UserMinimalSerializer(read_only=True)
    
    class Meta:
        model = CourseExam
        fields = [
            'id', 'course', 'created_by', 'title', 
            'description', 'instructions', 'exam_type', 'difficulty_level',
            'time_limit_minutes', 'passing_score', 'max_attempts', 'shuffle_questions',
            'shuffle_answers', 'show_results_immediately', 'show_correct_answers',
            'allow_review', 'required_course_progress', 'prerequisite_exams',
            'is_active', 'is_published', 'available_from', 'available_until'
        ]
    
    def validate_title(self, value):
        course = self.context.get('course')
        instance = getattr(self, 'instance', None)
        
        if course:
            queryset = CourseExam.objects.filter(course=course, title=value)
            if instance:
                queryset = queryset.exclude(pk=instance.pk)
            
            if queryset.exists():
                raise serializers.ValidationError("An exam with this title already exists in this course.")
        
        return value
    
    def validate_passing_score(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Passing score must be between 0 and 100.")
        return value
    
    def validate_max_attempts(self, value):
        if value < 1:
            raise serializers.ValidationError("Maximum attempts must be at least 1.")
        return value
    
    def validate_required_course_progress(self, value):
        if value < 0 or value > 100:
            raise serializers.ValidationError("Required course progress must be between 0 and 100.")
        return value
    
    def validate_time_limit_minutes(self, value):
        if value is not None and value <= 0:
            raise serializers.ValidationError("Time limit must be greater than 0 minutes.")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        available_from = data.get('available_from')
        available_until = data.get('available_until')
        
        # Validate availability dates
        if available_from and available_until:
            if available_from >= available_until:
                raise serializers.ValidationError(
                    "Available from date must be before available until date."
                )
        
        # Validate prerequisite exams belong to the same course
        prerequisite_exams = data.get('prerequisite_exams', [])
        course = self.context.get('course')
        
        if course and prerequisite_exams:
            invalid_prerequisites = [
                exam for exam in prerequisite_exams 
                if exam.course != course
            ]
            if invalid_prerequisites:
                raise serializers.ValidationError(
                    "Prerequisite exams must belong to the same course."
                )
        
        # Validate exam type specific rules
        exam_type = data.get('exam_type')
        if exam_type == 'final' and data.get('required_course_progress', 0) < 90:
            raise serializers.ValidationError(
                "Final exams should require at least 90% course progress completion."
            )
        
        return data
    
    def create(self, validated_data):
        prerequisite_exams = validated_data.pop('prerequisite_exams', [])
        course = self.context['course']
        created_by = self.context['request'].user
        
        exam = CourseExam.objects.create(
            course=course,
            created_by=created_by,
            **validated_data
        )
        
        # Set prerequisite exams
        if prerequisite_exams:
            exam.prerequisite_exams.set(prerequisite_exams)
        
        return exam
    
    def update(self, instance, validated_data):
        prerequisite_exams = validated_data.pop('prerequisite_exams', None)
        
        # Update exam fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update prerequisite exams if provided
        if prerequisite_exams is not None:
            instance.prerequisite_exams.set(prerequisite_exams)
        
        return instance
    

class ExamAnswerSerializer(serializers.ModelSerializer):
    """Serializer for exam answer choices"""
    image_url = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamAnswer
        fields = [
            'id', 'answer_text', 'is_correct', 'order', 'image_url'
        ]
    
    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None


class ExamAnswerCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating exam answers"""
    
    class Meta:
        model = ExamAnswer
        fields = ['answer_text', 'is_correct', 'order', 'image']
    
    def validate(self, data):
        # Ensure at least one correct answer for multiple choice questions
        question = self.context.get('question')
        if question and question.question_type == 'multiple_choice':
            is_correct = data.get('is_correct', False)
            existing_correct = question.answers.filter(is_correct=True).exists()
            
            if not is_correct and not existing_correct:
                # This would be the first answer, should have at least one correct
                pass  # Allow it, admin can fix later
        
        return data


class ExamQuestionSerializer(serializers.ModelSerializer):
    """Serializer for exam questions with answers"""
    answers = ExamAnswerSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    correct_answers_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ExamQuestion
        fields = [
            'id', 'question_text', 'question_type', 'points', 'order', 
            'is_active', 'explanation', 'image_url', 'difficulty_level', 
            'tags', 'answers', 'correct_answers_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_image_url(self, obj):
        if obj.image:
            return obj.image.url
        return None
    
    def get_correct_answers_count(self, obj):
        return obj.answers.filter(is_correct=True).count()


class ExamQuestionCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating exam questions"""
    answers = ExamAnswerCreateSerializer(many=True, required=False)
    
    class Meta:
        model = ExamQuestion
        fields = [
            'question_text', 'question_type', 'points', 'order', 
            'is_active', 'explanation', 'image', 'difficulty_level', 
            'tags', 'answers'
        ]
    
    def validate_question_text(self, value):
        if len(value.strip()) < 10:
            raise serializers.ValidationError("Question text must be at least 10 characters long.")
        return value
    
    def validate_points(self, value):
        if value <= 0:
            raise serializers.ValidationError("Points must be greater than 0.")
        return value
    
    def validate(self, data):
        question_type = data.get('question_type', 'multiple_choice')
        answers_data = data.get('answers', [])
        
        # Validate based on question type
        if question_type in ['multiple_choice', 'true_false']:
            if len(answers_data) < 2:
                raise serializers.ValidationError("Multiple choice and true/false questions must have at least 2 answers.")
            
            correct_answers = [ans for ans in answers_data if ans.get('is_correct')]
            if not correct_answers:
                raise serializers.ValidationError("At least one answer must be marked as correct.")
            
            if question_type == 'true_false' and len(answers_data) != 2:
                raise serializers.ValidationError("True/false questions must have exactly 2 answers.")
        
        elif question_type == 'fill_blank':
            if not answers_data:
                raise serializers.ValidationError("Fill in the blank questions must have at least one correct answer.")
        
        return data
    
    def create(self, validated_data):
        answers_data = validated_data.pop('answers', [])
        exam = self.context['exam']
        
        question = ExamQuestion.objects.create(exam=exam, **validated_data)
        
        # Create answers
        for answer_data in answers_data:
            ExamAnswer.objects.create(question=question, **answer_data)
        
        # Update exam's total questions count
        exam.calculate_total_questions()
        
        return question
    
    def update(self, instance, validated_data):
        answers_data = validated_data.pop('answers', [])
        
        # Update question
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update answers if provided
        if answers_data:
            # Delete existing answers
            instance.answers.all().delete()
            
            # Create new answers
            for answer_data in answers_data:
                ExamAnswer.objects.create(question=instance, **answer_data)
        
        return instance


class UserExamAttemptSerializer(serializers.ModelSerializer):
    """Serializer for user exam attempts"""
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    duration_display = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    time_remaining_minutes = serializers.SerializerMethodField()
    
    class Meta:
        model = UserExamAttempt
        fields = [
            'id', 'user_name', 'user_email', 'exam_title', 'attempt_number',
            'status', 'status_display', 'total_questions', 'correct_answers',
            'total_points', 'earned_points', 'percentage_score', 'passed',
            'started_at', 'completed_at', 'time_taken_minutes', 'duration_display',
            'time_remaining_minutes'
        ]
        read_only_fields = ['id', 'started_at']
    
    def get_duration_display(self, obj):
        if obj.time_taken_minutes:
            hours = obj.time_taken_minutes // 60
            minutes = obj.time_taken_minutes % 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        return "N/A"
    
    def get_time_remaining_minutes(self, obj):
        return obj.time_remaining() if obj.status == 'in_progress' else None
    
    def get_status_display(self, obj):
        return obj.get_status_display()


class ExamStatsSerializer(serializers.Serializer):
    """Serializer for exam statistics"""
    total_exams = serializers.IntegerField()
    published_exams = serializers.IntegerField()
    active_exams = serializers.IntegerField()
    total_attempts = serializers.IntegerField()
    completed_attempts = serializers.IntegerField()
    passed_attempts = serializers.IntegerField()
    overall_pass_rate = serializers.FloatField()
    average_score = serializers.FloatField()
    exams_by_type = serializers.DictField()
    recent_attempts = serializers.IntegerField()
    top_performing_exams = serializers.ListField()


class ExamQuestionStatsSerializer(serializers.Serializer):
    """Serializer for question-level statistics"""
    question_id = serializers.UUIDField()
    question_text = serializers.CharField()
    question_type = serializers.CharField()
    total_attempts = serializers.IntegerField()
    correct_attempts = serializers.IntegerField()
    success_rate = serializers.FloatField()
    difficulty_level = serializers.CharField()
    average_time_spent = serializers.FloatField()