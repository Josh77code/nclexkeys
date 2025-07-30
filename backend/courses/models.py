# courses/models.py
from django.db import models
from django.core.validators import URLValidator, MinValueValidator, MaxValueValidator
from django.utils import timezone
from users.models import User
from cloudinary.models import CloudinaryField
from django.contrib.postgres.fields import ArrayField
import uuid
import random
import string
from django.db.models import SET

def set_category_to_all():
    """Return 'all' category object for use in on_delete."""
    from .models import CourseCategory
    return CourseCategory.objects.get(slug="all")

# Create your models here.
class Course(models.Model):
    COURSE_TYPES = (
        ('free', 'Free'),
        ('paid', 'Paid'),
        ('premium', 'Premium'),
    )
    
    VIDEO_SOURCES = (
        ('url', 'Video URL'),
        ('upload', 'Uploaded Video'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    
    # Video handling - either URL or uploaded file
    video_source = models.CharField(
        max_length=10, 
        choices=VIDEO_SOURCES, 
        default='url',
        help_text="Choose between video URL or file upload"
    )
    video_url = models.URLField(
        validators=[URLValidator()], 
        blank=True, 
        null=True,
        help_text="YouTube, Vimeo, or other video URL"
    )
    video_file = CloudinaryField(
        'video', 
        blank=True, 
        null=True,
        resource_type='video',
        help_text="Upload MP4 or other video file"
    )

    # Course Structure Settings
    total_sections = models.PositiveIntegerField(default=0, help_text="Auto-calculated from sections")
    total_lessons = models.PositiveIntegerField(default=0, help_text="Auto-calculated from lessons")
    total_duration_seconds = models.PositiveIntegerField(default=0, help_text="Auto-calculated total duration")
    
    # Thumbnail/Cover image
    thumbnail = CloudinaryField(
        'image', 
        blank=True, 
        null=True,
        help_text="Course thumbnail image"
    )
    
    # Course pricing
    course_type = models.CharField(
        max_length=10,
        choices=COURSE_TYPES,
        default='free'
    )
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0.00,
        help_text="Course price (0.00 for free courses)"
    )
    currency = models.CharField(max_length=3, default='USD')

    # Moderation Field
    moderation_status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending Review'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('suspended', 'Suspended'),
        ],
        default='pending'
    )
    moderated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='moderated_courses'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_reason = models.TextField(blank=True)
    
    # Discount settings
    has_discount = models.BooleanField(default=False)
    discount_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Discount percentage (0-100)"
    )
    discount_start_date = models.DateTimeField(null=True, blank=True)
    discount_end_date = models.DateTimeField(null=True, blank=True)
    
    # Optional fields for enhanced functionality
    duration_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Course duration in minutes")
    # Estimated course length (hours)
    estimated_duration_hours = models.DecimalField(
        max_digits=5, decimal_places=2,
        null=True, blank=True,
        validators=[MinValueValidator(0)],
        help_text="Estimated total course duration in hours"
    )
    difficulty_level = models.CharField(
        max_length=20,
        choices=[
            ('beginner', 'Beginner'),
            ('intermediate', 'Intermediate'),
            ('advanced', 'Advanced')
        ],
        default='beginner'
    )

    category = models.ForeignKey(
        "CourseCategory",
        on_delete=SET(set_category_to_all),  # On delete, set to 'all'
        null=True,
        blank=True,
        related_name="courses"
    )

    # Requirements - list of strings
    requirements = ArrayField(
        models.CharField(max_length=255, blank=True),
        blank=True, default=list,
        help_text="List of requirements/prerequisites for this course"
    )

    # What students will learn - list of strings
    what_you_will_learn = ArrayField(
        models.CharField(max_length=255, blank=True),
        blank=True, default=list,
        help_text="List of learning objectives/outcomes"
    )

    
    # Status and visibility
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    
    # Prerequisites
    prerequisites = models.ManyToManyField(
        'self', 
        blank=True, 
        symmetrical=False,
        help_text="Courses that must be completed before this one"
    )
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Track who created/modified the course
    created_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='created_courses'
    )
    updated_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='updated_courses'
    )
    
    class Meta:
        db_table = 'courses'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['title']),
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_featured']),
            models.Index(fields=['course_type']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return self.title
    
    def get_video_url(self):
        """Get the appropriate video URL based on source"""
        if self.video_source == 'url' and self.video_url:
            return self.video_url
        elif self.video_source == 'upload' and self.video_file:
            try:
                # Handle both CloudinaryField and string cases
                if hasattr(self.video_file, 'url'):
                    return self.video_file.url
                else:
                    return str(self.video_file)
            except (AttributeError, ValueError):
                return None
        return None
    
    def get_effective_price(self):
        """Get the current effective price considering discounts"""
        if self.course_type == 'free':
            return 0.00
        
        base_price = float(self.price)
        
        if self.has_discount and self.is_discount_active():
            discount_amount = base_price * (self.discount_percentage / 100)
            return round(base_price - discount_amount, 2)
        
        return base_price
    
    def is_discount_active(self):
        """Check if discount is currently active"""
        if not self.has_discount:
            return False
        
        now = timezone.now()
        
        if self.discount_start_date and now < self.discount_start_date:
            return False
        
        if self.discount_end_date and now > self.discount_end_date:
            return False
        
        return True
    
    def is_free(self):
        """Check if course is free"""
        return self.course_type == 'free' or self.get_effective_price() == 0.00

    def update_course_totals(self):
        """Update course totals from sections and lessons"""
        sections = self.sections.filter(is_active=True)
        
        self.total_sections = sections.count()
        self.total_lessons = sum(section.lessons.filter(is_active=True).count() for section in sections)
        self.total_duration_seconds = sum(
            lesson.duration_seconds or 0 
            for section in sections 
            for lesson in section.lessons.filter(is_active=True)
        )
        
        # Convert to minutes for the existing duration_minutes field
        self.duration_minutes = self.total_duration_seconds // 60
        
        self.save(update_fields=['total_sections', 'total_lessons', 'total_duration_seconds', 'duration_minutes'])
        return {
            'sections': self.total_sections,
            'lessons': self.total_lessons,
            'duration_seconds': self.total_duration_seconds
        }
    
    def get_completion_rate(self):
        """Calculate overall completion rate for this course"""
        total_enrollments = self.user_progress.count()
        if total_enrollments == 0:
            return 0
        
        completed_enrollments = self.user_progress.filter(progress_percentage=100).count()
        return round((completed_enrollments / total_enrollments) * 100, 2)
    
    def get_average_progress(self):
        """Get average progress percentage for this course"""
        from django.db.models import Avg
        avg_progress = self.user_progress.aggregate(avg=Avg('progress_percentage'))['avg']
        return round(avg_progress, 2) if avg_progress else 0
    
    def get_total_revenue(self):
        """Get total revenue from this course"""
        from django.db.models import Sum
        total = self.enrollments.filter(
            is_active=True,
            payment_status='completed',
            amount_paid__isnull=False
        ).aggregate(total=Sum('amount_paid'))['total']
        return total or 0
    
    def get_average_rating(self):
        from django.db.models import Avg
        avg_rating = self.reviews.filter(is_approved=True).aggregate(avg=Avg('rating'))['avg']
        return round(avg_rating, 1) if avg_rating else 0

    def get_review_count(self):
        return self.reviews.filter(is_approved=True).count()


class CourseSection(models.Model):
    """Course sections to organize lessons (like Udemy sections)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    # Section settings
    is_preview = models.BooleanField(default=False, help_text="Allow free preview of this section")
    required_previous_completion = models.BooleanField(default=True, help_text="Must complete previous sections first")
    
    # Progress tracking
    total_lessons = models.PositiveIntegerField(default=0, help_text="Auto-calculated")
    total_duration_seconds = models.PositiveIntegerField(default=0, help_text="Auto-calculated")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'course_sections'
        ordering = ['course', 'order', 'created_at']
        unique_together = ['course', 'title']
        indexes = [
            models.Index(fields=['course', 'order']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def save(self, *args, **kwargs):
        # Auto-assign order if not set
        if not self.order:
            last_section = CourseSection.objects.filter(course=self.course).order_by('-order').first()
            self.order = (last_section.order + 1) if last_section else 1
        super().save(*args, **kwargs)
    
    def update_section_totals(self):
        """Update section totals from lessons"""
        lessons = self.lessons.filter(is_active=True)
        
        self.total_lessons = lessons.count()
        self.total_duration_seconds = sum(lesson.duration_seconds or 0 for lesson in lessons)
        
        self.save(update_fields=['total_lessons', 'total_duration_seconds'])
        
        # Update course totals
        self.course.update_course_totals()
        
        return {
            'lessons': self.total_lessons,
            'duration_seconds': self.total_duration_seconds
        }
    
    def get_completion_rate(self, user=None):
        """Get completion rate for this section"""
        if not user:
            return 0
        
        total_lessons = self.lessons.filter(is_active=True).count()
        if total_lessons == 0:
            return 100
        
        completed_lessons = UserLessonProgress.objects.filter(
            user=user,
            lesson__section=self,
            is_completed=True
        ).count()
        
        return round((completed_lessons / total_lessons) * 100, 2)
    
    def is_accessible_by_user(self, user):
        """Check if user can access this section"""
        if self.is_preview:
            return True
        
        # Check if user is enrolled
        if not UserCourseProgress.objects.filter(user=user, course=self.course).exists():
            return False
        
        # Check if previous sections are completed (if required)
        if self.required_previous_completion:
            previous_sections = CourseSection.objects.filter(
                course=self.course,
                order__lt=self.order,
                is_active=True
            )
            
            for prev_section in previous_sections:
                if prev_section.get_completion_rate(user) < 100:
                    return False
        
        return True

class CourseLesson(models.Model):
    """Individual lessons within course sections"""
    LESSON_TYPES = (
        ('video', 'Video Lesson'),
        ('text', 'Text/Article'),
        ('quiz', 'Quiz'),
        ('assignment', 'Assignment'),
        ('resource', 'Downloadable Resource'),
        ('live', 'Live Session'),
    )
    
    VIDEO_SOURCES = (
        ('url', 'Video URL'),
        ('upload', 'Uploaded Video'),
        ('streaming', 'Streaming URL'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    section = models.ForeignKey(CourseSection, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    lesson_type = models.CharField(max_length=20, choices=LESSON_TYPES, default='video')
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    # Video content (for video lessons)
    video_source = models.CharField(max_length=10, choices=VIDEO_SOURCES, default='url')
    video_url = models.URLField(blank=True, null=True, help_text="YouTube, Vimeo, or direct video URL")
    video_file = CloudinaryField('video', blank=True, null=True, resource_type='video')
    video_streaming_url = models.URLField(blank=True, null=True, help_text="HLS or DASH streaming URL")
    
    # Text content (for text lessons)
    text_content = models.TextField(blank=True, help_text="Rich text content for text lessons")
    
    # Media assets
    thumbnail = CloudinaryField('image', blank=True, null=True)
    attachments = models.JSONField(default=list, blank=True, help_text="List of attachment URLs/files")
    
    # Lesson settings
    duration_seconds = models.PositiveIntegerField(null=True, blank=True, help_text="Lesson duration in seconds")
    is_preview = models.BooleanField(default=False, help_text="Allow free preview")
    is_downloadable = models.BooleanField(default=False, help_text="Allow video download")
    require_completion = models.BooleanField(default=True, help_text="Must complete to progress")
    
    # Progress tracking settings
    minimum_watch_percentage = models.PositiveIntegerField(
        default=80, 
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Minimum percentage to mark as completed"
    )
    
    # Auto-play settings
    auto_play_next = models.BooleanField(default=False, help_text="Auto-play next lesson")
    
    # Additional metadata
    keywords = models.CharField(max_length=500, blank=True, help_text="Keywords for search")
    notes_for_instructor = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'course_lessons'
        ordering = ['section', 'order', 'created_at']
        unique_together = ['section', 'title']
        indexes = [
            models.Index(fields=['section', 'order']),
            models.Index(fields=['lesson_type']),
            models.Index(fields=['is_active']),
            models.Index(fields=['is_preview']),
        ]
    
    def __str__(self):
        return f"{self.section.title} - {self.title}"
    
    def save(self, *args, **kwargs):
        # Auto-assign order if not set
        if not self.order:
            last_lesson = CourseLesson.objects.filter(section=self.section).order_by('-order').first()
            self.order = (last_lesson.order + 1) if last_lesson else 1
        super().save(*args, **kwargs)
        
        # Update section and course totals
        self.section.update_section_totals()
    
    def get_video_url(self):
        """Get the appropriate video URL based on source"""
        if self.lesson_type != 'video':
            return None

        if self.video_source == 'url' and self.video_url:
            return self.video_url
        elif self.video_source == 'upload' and self.video_file:
            try:
                # Handle both CloudinaryField object and string public_id
                if hasattr(self.video_file, 'url'):
                    return self.video_file.url
                elif isinstance(self.video_file, str):
                    # Construct Cloudinary URL from public_id
                    from cloudinary.utils import cloudinary_url as build_cloudinary_url
                    url, _ = build_cloudinary_url(self.video_file, resource_type="video")
                    return url
                return None
            except (AttributeError, ValueError):
                return None
        elif self.video_source == 'streaming' and self.video_streaming_url:
            return self.video_streaming_url
    
        return None
    
    def get_duration_display(self):
        """Get formatted duration"""
        if not self.duration_seconds:
            return "N/A"
        
        hours = self.duration_seconds // 3600
        minutes = (self.duration_seconds % 3600) // 60
        seconds = self.duration_seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"
    
    def is_accessible_by_user(self, user):
        """Check if user can access this lesson"""
        # Check if lesson is preview
        if self.is_preview:
            return True
        
        # Check section accessibility
        if not self.section.is_accessible_by_user(user):
            return False
        
        # Check if previous lessons in this section are completed
        if self.require_completion:
            previous_lessons = CourseLesson.objects.filter(
                section=self.section,
                order__lt=self.order,
                is_active=True,
                require_completion=True
            )
            
            for prev_lesson in previous_lessons:
                try:
                    progress = UserLessonProgress.objects.get(user=user, lesson=prev_lesson)
                    if not progress.is_completed:
                        return False
                except UserLessonProgress.DoesNotExist:
                    return False
        
        return True
    
    def get_next_lesson(self):
        """Get the next lesson in sequence"""
        # Try next lesson in same section
        next_in_section = CourseLesson.objects.filter(
            section=self.section,
            order__gt=self.order,
            is_active=True
        ).first()
        
        if next_in_section:
            return next_in_section
        
        # Try first lesson in next section
        next_section = CourseSection.objects.filter(
            course=self.section.course,
            order__gt=self.section.order,
            is_active=True
        ).first()
        
        if next_section:
            return next_section.lessons.filter(is_active=True).first()
        
        return None
    
    def get_previous_lesson(self):
        """Get the previous lesson in sequence"""
        # Try previous lesson in same section
        prev_in_section = CourseLesson.objects.filter(
            section=self.section,
            order__lt=self.order,
            is_active=True
        ).order_by('-order').first()
        
        if prev_in_section:
            return prev_in_section
        
        # Try last lesson in previous section
        prev_section = CourseSection.objects.filter(
            course=self.section.course,
            order__lt=self.section.order,
            is_active=True
        ).order_by('-order').first()
        
        if prev_section:
            return prev_section.lessons.filter(is_active=True).order_by('-order').first()
        
        return None

class UserLessonProgress(models.Model):
    """Track user progress for individual lessons"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(CourseLesson, on_delete=models.CASCADE, related_name='user_progress')
    
    # Progress tracking
    watch_time_seconds = models.PositiveIntegerField(default=0, help_text="Total time watched")
    current_position_seconds = models.PositiveIntegerField(default=0, help_text="Current video position")
    watch_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Percentage of video watched"
    )
    
    # Completion
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Activity tracking
    first_accessed = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)
    access_count = models.PositiveIntegerField(default=1)
    
    # Notes and bookmarks
    bookmarks = models.JSONField(default=list, blank=True, help_text="List of bookmarked positions")
    notes = models.TextField(blank=True, help_text="User's personal notes for this lesson")
    
    # Lesson rating/feedback
    rating = models.PositiveIntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    feedback = models.TextField(blank=True)
    
    class Meta:
        db_table = 'user_lesson_progress'
        unique_together = ['user', 'lesson']
        ordering = ['-last_accessed']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['lesson']),
            models.Index(fields=['is_completed']),
            models.Index(fields=['last_accessed']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} - {self.lesson.title} ({self.watch_percentage}%)"
    
    def save(self, *args, **kwargs):
        # Auto-complete if watch percentage exceeds minimum
        min_percentage = self.lesson.minimum_watch_percentage
        if self.watch_percentage >= min_percentage and not self.is_completed:
            self.is_completed = True
            self.completed_at = timezone.now()
        elif self.watch_percentage < min_percentage and self.is_completed:
            self.is_completed = False
            self.completed_at = None
        
        super().save(*args, **kwargs)
        
        # Update course progress
        self.update_course_progress()
    
    def update_course_progress(self):
        """Update overall course progress for the user"""
        try:
            course_progress = UserCourseProgress.objects.get(
                user=self.user,
                course=self.lesson.section.course
            )
            
            # Calculate overall progress
            total_required_lessons = CourseLesson.objects.filter(
                section__course=course_progress.course,
                section__is_active=True,
                is_active=True,
                require_completion=True
            ).count()
            
            if total_required_lessons == 0:
                return
            
            completed_lessons = UserLessonProgress.objects.filter(
                user=self.user,
                lesson__section__course=course_progress.course,
                lesson__section__is_active=True,
                lesson__is_active=True,
                lesson__require_completion=True,
                is_completed=True
            ).count()
            
            new_progress = round((completed_lessons / total_required_lessons) * 100, 2)
            
            if new_progress != course_progress.progress_percentage:
                course_progress.progress_percentage = min(100, int(new_progress))
                
                # Update completed sections list
                completed_sections = []
                for section in course_progress.course.sections.filter(is_active=True):
                    if section.get_completion_rate(self.user) == 100:
                        completed_sections.append(str(section.id))
                
                course_progress.sections_completed = completed_sections
                course_progress.save()
        
        except UserCourseProgress.DoesNotExist:
            pass
    
    def add_bookmark(self, position_seconds, title="", description=""):
        """Add a bookmark at specific position"""
        bookmark = {
            'position_seconds': position_seconds,
            'title': title or f"Bookmark at {self.format_time(position_seconds)}",
            'description': description,
            'created_at': timezone.now().isoformat()
        }
        
        if not isinstance(self.bookmarks, list):
            self.bookmarks = []
        
        self.bookmarks.append(bookmark)
        self.save(update_fields=['bookmarks'])
        return bookmark
    
    def remove_bookmark(self, index):
        """Remove bookmark by index"""
        if isinstance(self.bookmarks, list) and 0 <= index < len(self.bookmarks):
            removed = self.bookmarks.pop(index)
            self.save(update_fields=['bookmarks'])
            return removed
        return None
    
    @staticmethod
    def format_time(seconds):
        """Format seconds to HH:MM:SS or MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
    

class UserCourseProgress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_progress')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='user_progress')
    
    # Progress tracking
    progress_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Progress percentage (0-100)"
    )
    
    # Timestamps
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    # Optional: Track specific section IDs or milestones
    sections_completed = models.JSONField(default=list, blank=True, help_text="List of completed section IDs")
    current_section_id = models.UUIDField(null=True, blank=True, help_text="Current section being studied")
    current_lesson_id = models.UUIDField(null=True, blank=True, help_text="Current lesson being studied")
    total_watch_time_seconds = models.PositiveIntegerField(default=0, help_text="Total time spent watching")
    notes = models.TextField(blank=True, help_text="User's personal notes for this course")
    
    # Rating and feedback (optional)
    rating = models.PositiveIntegerField(
        null=True, 
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="User rating (1-5 stars)"
    )
    feedback = models.TextField(blank=True, help_text="User feedback about the course")
    
    class Meta:
        db_table = 'user_course_progress'
        unique_together = ['user', 'course']
        ordering = ['-last_accessed']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['course']),
            models.Index(fields=['progress_percentage']),
            models.Index(fields=['completed_at']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} - {self.course.title} ({self.progress_percentage}%)"
    
    def save(self, *args, **kwargs):
        # Auto-set completed_at when progress reaches 100%
        if self.progress_percentage == 100 and not self.completed_at:
            self.completed_at = timezone.now()
        elif self.progress_percentage < 100:
            self.completed_at = None
        
        super().save(*args, **kwargs)
    
    def is_completed(self):
        """Check if course is completed"""
        return self.progress_percentage == 100
    
    def mark_complete(self):
        """Mark course as complete"""
        self.progress_percentage = 100
        self.completed_at = timezone.now()
        self.save(update_fields=['progress_percentage', 'completed_at'])
    
    def mark_incomplete(self):
        """Mark course as incomplete"""
        self.progress_percentage = 0
        self.completed_at = None
        self.save(update_fields=['progress_percentage', 'completed_at'])

    def get_current_lesson(self):
        """Get the current lesson user should study next"""
        if self.current_lesson_id:
            try:
                return CourseLesson.objects.get(id=self.current_lesson_id)
            except CourseLesson.DoesNotExist:
                pass
        
        # Find first incomplete lesson
        for section in self.course.sections.filter(is_active=True).order_by('order'):
            for lesson in section.lessons.filter(is_active=True, require_completion=True).order_by('order'):
                try:
                    lesson_progress = UserLessonProgress.objects.get(user=self.user, lesson=lesson)
                    if not lesson_progress.is_completed:
                        return lesson
                except UserLessonProgress.DoesNotExist:
                    return lesson
        
        return None
    
    def get_progress_by_section(self):
        """Get progress breakdown by section"""
        sections_progress = []
        
        for section in self.course.sections.filter(is_active=True).order_by('order'):
            section_progress = {
                'section_id': str(section.id),
                'section_title': section.title,
                'section_order': section.order,
                'total_lessons': section.lessons.filter(is_active=True, require_completion=True).count(),
                'completed_lessons': 0,
                'completion_percentage': 0,
                'is_completed': str(section.id) in self.sections_completed,
                'lessons': []
            }
            
            for lesson in section.lessons.filter(is_active=True).order_by('order'):
                lesson_data = {
                    'lesson_id': str(lesson.id),
                    'lesson_title': lesson.title,
                    'lesson_type': lesson.lesson_type,
                    'lesson_order': lesson.order,
                    'duration_seconds': lesson.duration_seconds,
                    'is_completed': False,
                    'watch_percentage': 0,
                    'current_position': 0
                }
                
                try:
                    lesson_progress = UserLessonProgress.objects.get(user=self.user, lesson=lesson)
                    lesson_data.update({
                        'is_completed': lesson_progress.is_completed,
                        'watch_percentage': lesson_progress.watch_percentage,
                        'current_position': lesson_progress.current_position_seconds,
                        'last_accessed': lesson_progress.last_accessed
                    })
                    
                    if lesson_progress.is_completed and lesson.require_completion:
                        section_progress['completed_lessons'] += 1
                        
                except UserLessonProgress.DoesNotExist:
                    pass
                
                section_progress['lessons'].append(lesson_data)
            
            # Calculate section completion percentage
            if section_progress['total_lessons'] > 0:
                section_progress['completion_percentage'] = round(
                    (section_progress['completed_lessons'] / section_progress['total_lessons']) * 100, 2
                )
            
            sections_progress.append(section_progress)
        
        return sections_progress


class CourseEnrollment(models.Model):
    """Track course enrollments and payments"""
    PAYMENT_STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    
    # Enrollment details
    enrolled_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="For time-limited access")
    
    # Payment tracking
    payment_status = models.CharField(
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default='pending'
    )
    payment_id = models.CharField(max_length=100, null=True, blank=True)
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')
    
    # Discount applied
    discount_applied = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Refund tracking
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refund_reason = models.TextField(blank=True)
    refunded_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'course_enrollments'
        unique_together = ['user', 'course']
        ordering = ['-enrolled_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['course']),
            models.Index(fields=['is_active']),
            models.Index(fields=['payment_status']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} enrolled in {self.course.title}"
    
    def is_expired(self):
        """Check if enrollment is expired"""
        if self.expires_at:
            return timezone.now() > self.expires_at
        return False
    
    def is_paid(self):
        """Check if enrollment is paid"""
        return self.payment_status == 'completed'


class CourseCategory(models.Model):
    """Optional: Separate model for dynamic categories"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    
    # Display order
    order = models.PositiveIntegerField(default=0)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'course_categories'
        ordering = ['order', 'name']
        verbose_name_plural = 'Course Categories'
    
    def __str__(self):
        return self.name
    
    def get_courses_count(self):
        """Get count of active courses in this category"""
        return Course.objects.filter(category=self, is_active=True).count()


class CourseReview(models.Model):
    """Course reviews and ratings"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_reviews')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='reviews')
    
    rating = models.PositiveIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Rating (1-5 stars)"
    )
    review_text = models.TextField(blank=True)
    
    # Moderation
    is_approved = models.BooleanField(default=True)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='approved_reviews'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)
    is_featured = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'course_reviews'
        unique_together = ['user', 'course']
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.user.full_name} - {self.course.title} ({self.rating}★)"


class CourseAppeal(models.Model):
    """Model to track course suspension appeals"""
    APPEAL_STATUS_CHOICES = [
        ('pending', 'Pending Review'),
        ('under_review', 'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='appeals')
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_appeals')
    appeal_reason = models.TextField()
    supporting_documents = models.JSONField(default=list, blank=True)  # URLs to uploaded docs
    status = models.CharField(max_length=20, choices=APPEAL_STATUS_CHOICES, default='pending')
    
    # Review fields
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_appeals')
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'course_appeals'
        ordering = ['-created_at']
        # Prevent multiple pending appeals for same course
        unique_together = ['course', 'status']
    
    def __str__(self):
        return f"Appeal for {self.course.title} by {self.instructor.full_name}"
    

class CourseExam(models.Model):
    """Exams/Quizzes for courses (like Udemy assessments)"""
    EXAM_TYPES = (
        ('quiz', 'Quiz'),
        ('midterm', 'Midterm Exam'),
        ('final', 'Final Exam'),
        ('practice', 'Practice Test'),
        ('assignment', 'Assignment'),
    )
    
    DIFFICULTY_LEVELS = (
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
        ('expert', 'Expert'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='exams')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True, help_text="Instructions for students")
    
    exam_type = models.CharField(max_length=20, choices=EXAM_TYPES, default='quiz')
    difficulty_level = models.CharField(max_length=10, choices=DIFFICULTY_LEVELS, default='medium')
    
    # Exam settings
    total_questions = models.PositiveIntegerField(default=0)  # Auto-calculated
    time_limit_minutes = models.PositiveIntegerField(null=True, blank=True, help_text="Time limit in minutes (optional)")
    passing_score = models.PositiveIntegerField(default=70, help_text="Minimum score to pass (percentage)")
    max_attempts = models.PositiveIntegerField(default=3, help_text="Maximum attempts allowed")
    
    # Behavior settings
    shuffle_questions = models.BooleanField(default=True)
    shuffle_answers = models.BooleanField(default=True)
    show_results_immediately = models.BooleanField(default=True)
    show_correct_answers = models.BooleanField(default=True)
    allow_review = models.BooleanField(default=True)
    
    # Prerequisites
    required_course_progress = models.PositiveIntegerField(
        default=0, 
        help_text="Minimum course progress percentage to access this exam"
    )
    prerequisite_exams = models.ManyToManyField(
        'self', 
        blank=True, 
        symmetrical=False,
        help_text="Exams that must be passed before this one"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    is_published = models.BooleanField(default=False)
    
    # Scheduling
    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_exams')
    
    class Meta:
        db_table = 'course_exams'
        ordering = ['course', 'exam_type', 'title']
        indexes = [
            models.Index(fields=['course']),
            models.Index(fields=['is_active', 'is_published']),
            models.Index(fields=['exam_type']),
        ]
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"
    
    def is_available(self):
        """Check if exam is currently available"""
        now = timezone.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return self.is_active and self.is_published
    
    def get_duration_display(self):
        """Get formatted duration"""
        if self.time_limit_minutes:
            hours = self.time_limit_minutes // 60
            minutes = self.time_limit_minutes % 60
            if hours > 0:
                return f"{hours}h {minutes}m"
            return f"{minutes}m"
        return "Unlimited"
    
    def calculate_total_questions(self):
        """Calculate and update total questions"""
        self.total_questions = self.questions.filter(is_active=True).count()
        self.save(update_fields=['total_questions'])
        return self.total_questions
    
    def get_pass_rate(self):
        """Calculate pass rate for this exam"""
        completed_attempts = self.attempts.filter(status='completed').count()
        if completed_attempts == 0:
            return 0
        passed_attempts = self.attempts.filter(status='completed', passed=True).count()
        return round((passed_attempts / completed_attempts) * 100, 2)
    
    def get_average_score(self):
        """Get average score for this exam"""
        from django.db.models import Avg
        avg_score = self.attempts.filter(status='completed').aggregate(avg=Avg('percentage_score'))['avg']
        return round(avg_score, 2) if avg_score else 0


class ExamQuestion(models.Model):
    """Questions for exams"""
    QUESTION_TYPES = (
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('fill_blank', 'Fill in the Blank'),
        ('essay', 'Essay'),
        ('matching', 'Matching'),
        ('ordering', 'Ordering'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(CourseExam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='multiple_choice')
    
    # Question settings
    points = models.PositiveIntegerField(default=1)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    # Additional content
    explanation = models.TextField(blank=True, help_text="Explanation shown after answering")
    image = CloudinaryField('image', blank=True, null=True, help_text="Optional question image")
    
    # Question metadata
    difficulty_level = models.CharField(
        max_length=10, 
        choices=CourseExam.DIFFICULTY_LEVELS, 
        default='medium'
    )
    tags = models.JSONField(default=list, blank=True, help_text="Tags for categorization")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'exam_questions'
        ordering = ['exam', 'order', 'created_at']
        indexes = [
            models.Index(fields=['exam']),
            models.Index(fields=['question_type']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return f"Q{self.order}: {self.question_text[:50]}..."
    
    def save(self, *args, **kwargs):
        # Auto-assign order if not set
        if not self.order:
            last_question = ExamQuestion.objects.filter(exam=self.exam).order_by('-order').first()
            self.order = (last_question.order + 1) if last_question else 1
        super().save(*args, **kwargs)
    
    def get_correct_answers(self):
        """Get all correct answers for this question"""
        return self.answers.filter(is_correct=True)
    
    def validate_answer(self, user_answers):
        """Validate user's answer(s) against correct answers"""
        if self.question_type == 'multiple_choice':
            correct_answers = set(str(answer.id) for answer in self.get_correct_answers())
            user_answer_ids = set(str(answer) for answer in (user_answers if isinstance(user_answers, list) else [user_answers]))
            return correct_answers == user_answer_ids
        
        elif self.question_type == 'true_false':
            correct_answer = self.get_correct_answers().first()
            if correct_answer:
                return str(user_answers).lower().strip() == str(correct_answer.answer_text).lower().strip()
            return False
        
        elif self.question_type == 'fill_blank':
            correct_answers = self.get_correct_answers().values_list('answer_text', flat=True)
            user_answer = str(user_answers).lower().strip()
            return any(answer.lower().strip() == user_answer for answer in correct_answers)
        
        # Add more validation logic for other question types as needed
        return False


class ExamAnswer(models.Model):
    """Answer choices for exam questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    
    # Optional answer image
    image = CloudinaryField('image', blank=True, null=True)
    
    class Meta:
        db_table = 'exam_answers'
        ordering = ['question', 'order']
        indexes = [
            models.Index(fields=['question']),
            models.Index(fields=['is_correct']),
        ]
    
    def __str__(self):
        return f"{self.question.question_text[:30]}... - {self.answer_text[:30]}..."
    
    def save(self, *args, **kwargs):
        # Auto-assign order if not set
        if not self.order:
            last_answer = ExamAnswer.objects.filter(question=self.question).order_by('-order').first()
            self.order = (last_answer.order + 1) if last_answer else 1
        super().save(*args, **kwargs)


class UserExamAttempt(models.Model):
    """Track user exam attempts"""
    STATUS_CHOICES = (
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('abandoned', 'Abandoned'),
        ('timed_out', 'Timed Out'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='exam_attempts')
    exam = models.ForeignKey(CourseExam, on_delete=models.CASCADE, related_name='attempts')
    
    # Attempt details
    attempt_number = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='in_progress')
    
    # Scoring
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    total_points = models.PositiveIntegerField(default=0)
    earned_points = models.PositiveIntegerField(default=0)
    percentage_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    time_taken_minutes = models.PositiveIntegerField(null=True, blank=True)
    
    # Results
    passed = models.BooleanField(default=False)
    
    # Exam state (for resuming)
    current_question_index = models.PositiveIntegerField(default=0)
    exam_data = models.JSONField(default=dict, blank=True)  # Store shuffled questions, etc.
    
    class Meta:
        db_table = 'user_exam_attempts'
        ordering = ['-started_at']
        unique_together = ['user', 'exam', 'attempt_number']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['exam']),
            models.Index(fields=['status']),
            models.Index(fields=['passed']),
        ]
    
    def __str__(self):
        return f"{self.user.full_name} - {self.exam.title} (Attempt {self.attempt_number})"
    
    def save(self, *args, **kwargs):
        # Auto-assign attempt number if not set
        if not self.attempt_number:
            last_attempt = UserExamAttempt.objects.filter(user=self.user, exam=self.exam).order_by('-attempt_number').first()
            self.attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
        super().save(*args, **kwargs)
    
    def calculate_score(self):
        """Calculate and update the score"""
        user_answers = self.user_answers.all()
        
        total_questions = user_answers.count()
        correct_count = 0
        total_points = 0
        earned_points = 0
        
        for user_answer in user_answers:
            total_points += user_answer.question.points
            if user_answer.is_correct:
                correct_count += 1
                earned_points += user_answer.question.points
        
        self.total_questions = total_questions
        self.correct_answers = correct_count
        self.total_points = total_points
        self.earned_points = earned_points
        self.percentage_score = (earned_points / total_points * 100) if total_points > 0 else 0
        self.passed = self.percentage_score >= self.exam.passing_score
        
        self.save(update_fields=[
            'total_questions', 'correct_answers', 'total_points', 
            'earned_points', 'percentage_score', 'passed'
        ])
        
        return self.percentage_score
    
    def complete_attempt(self):
        """Mark attempt as completed"""
        if self.status == 'in_progress':
            self.status = 'completed'
            self.completed_at = timezone.now()
            
            if self.started_at:
                time_diff = self.completed_at - self.started_at
                self.time_taken_minutes = int(time_diff.total_seconds() / 60)
            
            self.calculate_score()
            self.save()
    
    def can_review(self):
        """Check if user can review this attempt"""
        return self.status == 'completed' and self.exam.allow_review
    
    def time_remaining(self):
        """Get time remaining for this attempt (in minutes)"""
        if not self.exam.time_limit_minutes or self.status != 'in_progress':
            return None
        
        elapsed = timezone.now() - self.started_at
        elapsed_minutes = int(elapsed.total_seconds() / 60)
        remaining = self.exam.time_limit_minutes - elapsed_minutes
        
        return max(0, remaining)


class UserExamAnswer(models.Model):
    """User's answers to exam questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(UserExamAttempt, on_delete=models.CASCADE, related_name='user_answers')
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE)
    
    # Answer data
    selected_answers = models.ManyToManyField(ExamAnswer, blank=True)  # For multiple choice
    text_answer = models.TextField(blank=True)  # For text-based answers
    answer_data = models.JSONField(default=dict, blank=True)  # For complex answer types
    
    # Scoring
    is_correct = models.BooleanField(default=False)
    points_earned = models.PositiveIntegerField(default=0)
    
    # Timing
    answered_at = models.DateTimeField(auto_now_add=True)
    time_taken_seconds = models.PositiveIntegerField(default=0)
    
    class Meta:
        db_table = 'user_exam_answers'
        unique_together = ['attempt', 'question']
        indexes = [
            models.Index(fields=['attempt']),
            models.Index(fields=['question']),
            models.Index(fields=['is_correct']),
        ]
    
    def __str__(self):
        return f"{self.attempt.user.full_name} - Q{self.question.order}"
    
    def validate_and_score(self):
        """Validate answer and assign score"""
        if self.question.question_type == 'multiple_choice':
            selected_ids = list(self.selected_answers.values_list('id', flat=True))
            self.is_correct = self.question.validate_answer(selected_ids)
        else:
            answer_to_check = self.text_answer or self.answer_data
            self.is_correct = self.question.validate_answer(answer_to_check)
        
        # Assign points
        self.points_earned = self.question.points if self.is_correct else 0
        self.save(update_fields=['is_correct', 'points_earned'])
        
        return self.is_correct


class ExamCertificate(models.Model):
    """Certificates awarded for passing exams"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    exam = models.ForeignKey(CourseExam, on_delete=models.CASCADE, related_name='certificates')
    attempt = models.ForeignKey(UserExamAttempt, on_delete=models.CASCADE)
    
    # Certificate details
    certificate_number = models.CharField(max_length=50, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    
    # Certificate file
    certificate_file = CloudinaryField('raw', blank=True, null=True)
    certificate_url = models.URLField(blank=True)
    
    # Verification
    verification_code = models.CharField(max_length=50, unique=True)
    is_valid = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'exam_certificates'
        ordering = ['-issued_at']
        unique_together = ['user', 'exam']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['exam']),
            models.Index(fields=['certificate_number']),
            models.Index(fields=['verification_code']),
        ]
    
    def __str__(self):
        return f"Certificate: {self.user.full_name} - {self.exam.title}"
    
    def save(self, *args, **kwargs):
        if not self.certificate_number:
            self.certificate_number = self.generate_certificate_number()
        if not self.verification_code:
            self.verification_code = self.generate_verification_code()
        super().save(*args, **kwargs)
    
    def generate_certificate_number(self):
        """Generate unique certificate number"""
        while True:
            number = f"NCLEX-{timezone.now().year}-{''.join(random.choices(string.ascii_uppercase + string.digits, k=8))}"
            if not ExamCertificate.objects.filter(certificate_number=number).exists():
                return number
    
    def generate_verification_code(self):
        """Generate unique verification code"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
            if not ExamCertificate.objects.filter(verification_code=code).exists():
                return code
    
    def is_expired(self):
        """Check if certificate is expired"""
        if self.valid_until:
            return timezone.now() > self.valid_until
        return False