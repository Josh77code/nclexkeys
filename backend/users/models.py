# users/models.py
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.core.validators import EmailValidator
import uuid
from datetime import timedelta

# Create your models here.
class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'super_admin')
        extra_fields.setdefault('is_email_verified', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    ROLE_CHOICES = [
        ('user', 'User'),
        ('admin', 'Course Creator/Instructor'),
        ('super_admin', 'Platform Administrator'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True, validators=[EmailValidator()])
    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='user')
    
    # Authentication fields
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    last_activity = models.DateTimeField(null=True, blank=True)
    
    # Security fields
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_at = models.DateTimeField(null=True, blank=True)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(auto_now_add=True)

    # Account deletion fields
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    deletion_scheduled_for = models.DateTimeField(null=True, blank=True)
    is_deletion_pending = models.BooleanField(default=False)

    # Two Factor Authentication
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=32, blank=True, null=True)
    backup_codes = models.JSONField(default=list, blank=True)

    # Handling TimeZone
    timezone = models.CharField(max_length=50, default='UTC')
    
    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    # Track moderation to the course
    moderation_status = models.CharField(
        max_length=20, 
        choices=[
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('suspended', 'Suspended')
        ], 
        default='pending'
    )
    moderated_by = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='moderated_users'
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'users'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['role']),
            models.Index(fields=['is_active']),
        ]
    
    def __str__(self):
        return self.email
    
    def is_account_locked(self):
        if self.account_locked_until:
            return timezone.now() < self.account_locked_until
        return False
    
    def lock_account(self, duration_minutes=30):
        self.account_locked_at = timezone.now()
        self.account_locked_until = timezone.now() + timedelta(minutes=duration_minutes)
        self.save(update_fields=['account_locked_at', 'account_locked_until'])
    
    def unlock_account(self):
        self.failed_login_attempts = 0
        self.account_locked_until = None
        self.save(update_fields=['failed_login_attempts', 'account_locked_until'])
    
    def increment_failed_attempts(self):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:  # Lock after 5 failed attempts
            self.lock_account()
            # To avoid circular import
            from ..utils.auth import EmailService
            EmailService.send_account_locked_email(self)
        self.save(update_fields=['failed_login_attempts'])
    
    def reset_failed_attempts(self):
        self.failed_login_attempts = 0
        self.save(update_fields=['failed_login_attempts'])

    def request_deletion(self, days=14):
        """Request account deletion with grace period"""
        from datetime import timedelta
        self.deletion_requested_at = timezone.now()
        self.deletion_scheduled_for = timezone.now() + timedelta(days=days)
        self.is_deletion_pending = True
        self.save(update_fields=['deletion_requested_at', 'deletion_scheduled_for', 'is_deletion_pending'])
    
    def cancel_deletion(self):
        """Cancel pending deletion"""
        self.deletion_requested_at = None
        self.deletion_scheduled_for = None
        self.is_deletion_pending = False
        self.is_active = True
        self.save(update_fields=['deletion_requested_at', 'deletion_scheduled_for', 'is_deletion_pending', 'is_active'])


class EmailVerificationToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_tokens')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'email_verification_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user']),
        ]
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='password_reset_tokens')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'password_reset_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user']),
        ]
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()


class RefreshToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='refresh_tokens')
    token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_blacklisted = models.BooleanField(default=False)
    
    # Track device/session info
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    device_fingerprint = models.CharField(max_length=255, null=True, blank=True)
    
    class Meta:
        db_table = 'refresh_tokens'
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['user']),
            models.Index(fields=['is_blacklisted']),
        ]
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_blacklisted and not self.is_expired()
    
    def blacklist(self):
        self.is_blacklisted = True
        self.save(update_fields=['is_blacklisted'])


class LoginAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True) # Keep login attempts for audit
    email = models.EmailField()  # Store email even if user doesn't exist
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    success = models.BooleanField()
    failure_reason = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'login_attempts'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['ip_address']),
            models.Index(fields=['created_at']),
        ]


class UserSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sessions')
    session_token = models.CharField(max_length=255, unique=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()
    device_fingerprint = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)  # City, Country
    is_new_device = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        db_table = 'user_sessions'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['session_token']),
            models.Index(fields=['is_active']),
        ]


class EmailLog(models.Model):
    EMAIL_TYPES = [
        ('verification', 'Email Verification'),
        ('password_reset', 'Password Reset'),
        ('login_alert', 'Login Alert'),
        ('new_device', 'New Device Login'),
        ('password_changed', 'Password Changed'),
        ('account_locked', 'Account Locked'),
        ('account_deletion_requested', 'Account Deletion Requested'), 
        ('deletion_cancelled', 'Deletion Cancelled'), 
        ('account_deleted', 'Account Deleted'), 
        ('new_course_pending_review', 'New Course Pending Review'),
        ('course_approved', 'Course Approved'),
        ('course_rejected', 'Course Rejected'),
        ('course_suspended', 'Course Suspended'),
        ('instructor_suspended', 'Instructor Suspended'),
        ('instructor_payout', 'Instructor Payout'),
        ('high_revenue_alert', 'High Revenue Alert'),
        ('course_created_confirmation', 'Course Created Confirmation'),
        ('course_approved', 'Course Approved'),
        ('course_rejected', 'Course Rejected'),
        ('course_suspended', 'Course Suspended'),
        ('high_value_sale_notification', 'High Value Sale Notification'),
        ('new_course_pending_approval', 'New Course Pending Approval'),
        ('course_updated_review_required', 'Course Updated - Review Required'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True) # Keep email logs for audit
    email_type = models.CharField(max_length=40, choices=EMAIL_TYPES)
    recipient_email = models.EmailField()
    subject = models.CharField(max_length=255)
    sent_at = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=True)
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        db_table = 'email_logs'
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['email_type']),
            models.Index(fields=['sent_at']),
        ]