# utils.py
import jwt
import secrets
import hashlib
import logging
import pyotp
import qrcode
from io import BytesIO
import base64
import pytz
from django.utils import timezone
from datetime import datetime, timedelta
from django.conf import settings
from django.utils import timezone
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.contrib.gis.geoip2 import GeoIP2, GeoIP2Exception
from .models import (
    User, EmailVerificationToken, PasswordResetToken, 
    RefreshToken, LoginAttempt, UserSession, EmailLog
)
from django.db.models import Q

logger = logging.getLogger(__name__)

def format_seconds_to_human(seconds):
    minutes = seconds // 60
    remaining_seconds = seconds % 60

    parts = []
    if minutes > 0:
        parts.append(f"{int(minutes)} minute{'s' if minutes != 1 else ''}")
    if remaining_seconds > 0:
        parts.append(f"{int(remaining_seconds)} second{'s' if remaining_seconds != 1 else ''}")

    return ', '.join(parts) if parts else 'less than a second'


class JWTTokenManager:
    """Handle JWT token generation and validation"""
    
    @staticmethod
    def generate_access_token(user):
        """Generate JWT access token"""
        payload = {
            'user_id': str(user.id),
            'email': user.email,
            'role': user.role,
            'exp': timezone.now() + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME),
            'iat': timezone.now(),
            'type': 'access'
        }
        
        return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
    
    @staticmethod
    def generate_refresh_token(user, request):
        """Generate refresh token and store in database"""
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(days=settings.JWT_REFRESH_TOKEN_LIFETIME)
        
        # Get client info
        ip_address = SecurityUtils.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        device_fingerprint = SecurityUtils.generate_device_fingerprint(request)
        
        # Create refresh token record
        refresh_token = RefreshToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint
        )
        
        return token
    
    @staticmethod
    def verify_access_token(token):
        """Validate JWT access token"""
        try:
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])

            if payload.get('type') != 'access':
                return None

            # Return payload instead of user object
            return payload

        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
            return None
        
    @staticmethod
    def refresh_access_token(refresh_token_str):
        """Generate new access token using refresh token"""
        try:
            refresh_token = RefreshToken.objects.get(token=refresh_token_str)
            if not refresh_token.is_valid():
                return None
            
            # Generate new access token
            access_token = JWTTokenManager.generate_access_token(refresh_token.user)
            return access_token
        except RefreshToken.DoesNotExist:
            return None
    
    @staticmethod
    def blacklist_refresh_token(token):
        """Blacklist a refresh token"""
        try:
            refresh_token = RefreshToken.objects.get(token=token)
            refresh_token.blacklist()
        except RefreshToken.DoesNotExist:
            pass
    
    @staticmethod
    def blacklist_all_user_tokens(user):
        """Blacklist all refresh tokens for a user"""
        RefreshToken.objects.filter(user=user).update(is_blacklisted=True)

    @staticmethod
    def rotate_refresh_token(old_token):
        """Rotate refresh token for better security"""
        try:
            old_refresh_token = RefreshToken.objects.get(token=old_token)
            if not old_refresh_token.is_valid():
                return None

            # Create new token
            new_token = secrets.token_urlsafe(32)
            old_refresh_token.token = new_token
            old_refresh_token.created_at = timezone.now()  # Reset creation time
            old_refresh_token.save()

            return new_token
        except RefreshToken.DoesNotExist:
            return None
        

class TwoFactorManager:
    @staticmethod
    def generate_secret():
        """Generate TOTP secret"""
        return pyotp.random_base32()
    
    @staticmethod
    def get_qr_code(user, secret):
        """Generate QR code for 2FA setup"""
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            user.email,
            issuer_name="NCLEX Virtual School"
        )
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode()
    
    @staticmethod
    def verify_token(secret, token):
        """Verify TOTP token"""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)
    
    @staticmethod
    def verify_backup_code(user, code):
        """Verify and consume backup code"""
        if not user.backup_codes:
            return False

        code_hash = hashlib.sha256(code.encode()).hexdigest()

        if code_hash in user.backup_codes:
            # Remove used backup code
            user.backup_codes.remove(code_hash)
            user.save()
            return True

        return False


class EmailTokenManager:
    """Handle email verification and password reset tokens"""
    
    @staticmethod
    def generate_verification_token(user):
        """Generate email verification token"""
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=24)
        
        # Invalidate existing tokens
        EmailVerificationToken.objects.filter(user=user).update(is_used=True)
        
        verification_token = EmailVerificationToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
        
        return verification_token
    
    @staticmethod
    def generate_password_reset_token(user):
        """Generate password reset token"""
        token = secrets.token_urlsafe(32)
        expires_at = timezone.now() + timedelta(hours=1)
        
        # Invalidate existing tokens
        PasswordResetToken.objects.filter(user=user).update(is_used=True)
        
        reset_token = PasswordResetToken.objects.create(
            user=user,
            token=token,
            expires_at=expires_at
        )
        
        return reset_token


class SecurityMonitor:
    @staticmethod
    def log_security_event(event_type, user, details, severity='INFO'):
        """Log security events"""
        logger.info(f"SECURITY_EVENT: {event_type} | User: {user.email if user else 'Anonymous'} | {details}")
        
        # You can extend this to send to external monitoring services
        if severity == 'CRITICAL':
            SecurityMonitor.send_alert(event_type, user, details)
    
    @staticmethod
    def send_alert(event_type, user, details):
        """Send security alerts"""
        # Send to admin email, Slack, etc.
        subject = f"SECURITY ALERT: {event_type}"
        message = f"User: {user.email if user else 'Anonymous'}\nDetails: {details}"
        
        # Send email to admins
        admin_emails = ['admin@example.com']  # Configure this
        EmailService._send_mail(
            user=admin_emails, 
            subject=subject, 
            plain_message=message
        )


class SecurityUtils:
    """Security utilities for authentication"""
    
    @staticmethod
    def get_client_ip(request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def generate_device_fingerprint(request):
        """Generate device fingerprint"""
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        accept_encoding = request.META.get('HTTP_ACCEPT_ENCODING', '')
        
        fingerprint_data = f"{user_agent}{accept_language}{accept_encoding}"
        return hashlib.sha256(fingerprint_data.encode()).hexdigest()
    
    @staticmethod
    def is_new_device(user, device_fingerprint):
        """Check if this is a new device for the user"""
        existing_sessions = UserSession.objects.filter(
            user=user,
            device_fingerprint=device_fingerprint
        ).exists()
        
        return not existing_sessions
    
    @staticmethod
    def create_user_session(user, request, is_new_device=False):
        """Create user session record"""
        session_token = secrets.token_urlsafe(32)
        ip_address = SecurityUtils.get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        device_fingerprint = SecurityUtils.generate_device_fingerprint(request)
        location = SecurityUtils.get_location_from_ip(ip_address)
        
        session = UserSession.objects.create(
            user=user,
            session_token=session_token,
            ip_address=ip_address,
            user_agent=user_agent,
            device_fingerprint=device_fingerprint,
            location=location,
            is_new_device=is_new_device
        )
        
        return session
    
    @staticmethod
    def get_location_from_ip(ip_address):
        """Get location from IP address"""
        try:
            g = GeoIP2()
            location = g.city(ip_address)
            return f"{location['city']}, {location['country_name']}"
        except (GeoIP2Exception, Exception):
            return "Unknown"

    @staticmethod
    def log_login_attempt(user, email, ip_address, user_agent, success, failure_reason=None):
        """Log login attempt - WITHOUT incrementing failed attempts (handled by User model)"""
        LoginAttempt.objects.create(
            user=user,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            failure_reason=failure_reason
        )
        
        # Only increment failed attempts on actual login failure (not rate limiting)
        if not success and user and failure_reason != 'rate_limited':
            user.increment_failed_attempts()


class EmailService:
    """Email service for sending notifications"""
    
    @staticmethod
    def _convert_to_user_timezone(dt, user_timezone='UTC'):
        """Convert datetime to user's timezone"""
        if not dt:
            return dt
        
        try:
            tz = pytz.timezone(user_timezone)
            return dt.astimezone(tz)
        except:
            # Fallback to UTC if timezone conversion fails
            return dt
    
    @staticmethod
    def send_verification_email(user, verification_token):
        """Send email verification email"""
        verification_url = f"{settings.FRONTEND_URL}/verify-email?token={verification_token.token}"
        
        # Convert timestamps to user timezone
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'verification_url': verification_url,
            'verification_token': verification_token
        }
        
        subject = 'Verify Your Email Address - NCLEX Virtual School'
        html_message = render_to_string('emails/verification.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='verification',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )
    
    @staticmethod
    def send_password_reset_email(user, reset_token):
        """Send password reset email"""
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token.token}"
        
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'reset_url': reset_url,
            'reset_token': reset_token
        }
        
        subject = 'Reset Your Password - NCLEX Virtual School'
        html_message = render_to_string('emails/password_reset.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='password_reset',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )
    
    @staticmethod
    def send_login_alert_email(user, session):
        """Send login alert email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        # Convert session timestamps
        session_copy = session
        if hasattr(session, 'created_at'):
            session_copy.created_at = EmailService._convert_to_user_timezone(session.created_at, user_timezone)
        if hasattr(session, 'last_activity'):
            session_copy.last_activity = EmailService._convert_to_user_timezone(session.last_activity, user_timezone)
        
        context = {
            'user': user,
            'session': session_copy
        }
        
        subject = 'Login Alert - NCLEX Virtual School'
        html_message = render_to_string('emails/login_alert.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='login_alert',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )
    
    @staticmethod
    def send_new_device_email(user, session):
        """Send new device login email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        # Convert session timestamps
        session_copy = session
        if hasattr(session, 'created_at'):
            session_copy.created_at = EmailService._convert_to_user_timezone(session.created_at, user_timezone)
        if hasattr(session, 'last_activity'):
            session_copy.last_activity = EmailService._convert_to_user_timezone(session.last_activity, user_timezone)
        
        context = {
            'user': user,
            'session': session_copy
        }
        
        subject = 'New Device Login Detected - NCLEX Virtual School'
        html_message = render_to_string('emails/new_device.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='new_device',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )
    
    @staticmethod
    def send_password_changed_email(user):
        """Send password changed email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'timestamp': EmailService._convert_to_user_timezone(timezone.now(), user_timezone)
        }
        
        subject = 'Password Changed Successfully - NCLEX Virtual School'
        html_message = render_to_string('emails/password_changed.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='password_changed',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_account_locked_email(user):
        """Send account locked notification email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        # Convert user lock timestamps
        user_copy = user
        user_copy.account_locked_at = EmailService._convert_to_user_timezone(user.account_locked_at, user_timezone)
        user_copy.account_locked_until = EmailService._convert_to_user_timezone(user.account_locked_until, user_timezone)
        
        context = {
            'user': user_copy
        }

        subject = "Account Temporarily Locked - NCLEX Virtual School"
        html_message = render_to_string('emails/account_locked.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='account_locked',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_account_deletion_email(user):
        """Send account deletion request confirmation email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        deletion_scheduled_local = EmailService._convert_to_user_timezone(user.deletion_scheduled_for, user_timezone)
        days_remaining = (deletion_scheduled_local - EmailService._convert_to_user_timezone(timezone.now(), user_timezone)).days
        
        context = {
            'user': user,
            'days_remaining': days_remaining,
            'login_url': f'{settings.FRONTEND_URL}/login',
            'deletion_scheduled_for': deletion_scheduled_local
        }
        
        subject = "Account Deletion Requested - NCLEX Virtual School"
        html_message = render_to_string("emails/account_deletion_requested.html", context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='account_deletion_requested',
            subject=subject, 
            html_message=html_message, 
            plain_message=plain_message
        )

    @staticmethod
    def send_deletion_cancelled_email(user):
        """Send deletion cancellation confirmation email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'now': EmailService._convert_to_user_timezone(timezone.now(), user_timezone),
            'dashboard_url': settings.FRONTEND_URL
        }
        
        subject = "Account Deletion Cancelled - NCLEX Virtual School"
        html_message = render_to_string("emails/account_deletion_cancelled.html", context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='deletion_cancelled',
            subject=subject, 
            html_message=html_message, 
            plain_message=plain_message
        )
    
    @staticmethod
    def send_account_deleted_email(user):
        """Send final account deletion confirmation email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'now': EmailService._convert_to_user_timezone(timezone.now(), user_timezone)
        }
        
        subject = "Account Deleted - NCLEX Virtual School"
        html_message = render_to_string("emails/account_deleted.html", context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='account_deleted',
            subject=subject, 
            html_message=html_message, 
            plain_message=plain_message
        )

    @staticmethod
    def send_emergency_2fa_disable_email(user, request, emergency_token):
        """Send emergency 2FA disable request email"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'emergency_token': emergency_token,
            'request_time': EmailService._convert_to_user_timezone(timezone.now(), user_timezone),
            'ip_address': SecurityUtils.get_client_ip(request) if 'request' in locals() else 'Unknown'
        }
        
        subject = "Emergency 2FA Disable Request - NCLEX Virtual School"
        html_message = render_to_string('emails/emergency_2fa_disable.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='emergency_2fa_disable',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_2fa_emergency_disabled_email(user):
        """Send confirmation email when 2FA is emergency disabled"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'disabled_at': EmailService._convert_to_user_timezone(timezone.now(), user_timezone),
            'login_url': f'{settings.FRONTEND_URL}/login',
            'security_url': f'{settings.FRONTEND_URL}/security'
        }
        
        subject = "2FA Emergency Disabled - NCLEX Virtual School"
        html_message = render_to_string('emails/2fa_emergency_disabled.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='2fa_emergency_disabled',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_2fa_emergency_rejected_email(user):
        """Send email when emergency 2FA disable is rejected"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'rejected_at': EmailService._convert_to_user_timezone(timezone.now(), user_timezone),
            'support_email': 'support@nclexvirtualschool.com'
        }
        
        subject = "2FA Emergency Disable Request Rejected - NCLEX Virtual School"
        html_message = render_to_string('emails/2fa_emergency_rejected.html', context)
        plain_message = strip_tags(html_message)
        
        EmailService._send_email(
            user=user,
            email_type='2fa_emergency_rejected',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_deletion_reminder(user, days_remaining):
        """Send email reminder about pending account deletion"""
        user_timezone = getattr(user, 'timezone', 'UTC')
        
        context = {
            'user': user,
            'days_remaining': days_remaining,
            'deletion_date': EmailService._convert_to_user_timezone(user.deletion_scheduled_for, user_timezone),
            'support_email': 'support@nclexvirtualschool.com',
            'login_url': f"{settings.SITE_URL}/login"
        }

        subject = f"Account Deletion Reminder - {days_remaining} day{'s' if days_remaining != 1 else ''} remaining"
        html_message = render_to_string('emails/deletion_reminder.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='deletion_reminder',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def _send_email(user, email_type, subject, html_message, plain_message):
        """Internal method to send email and log"""
        try:
            send_mail(
                subject=subject,
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                html_message=html_message,
                fail_silently=False
            )
            
            # Log successful email
            EmailLog.objects.create(
                user=user,
                email_type=email_type,
                recipient_email=user.email,
                subject=subject,
                success=True
            )
            
        except Exception as e:
            logger.error(f"Failed to send {email_type} email to {user.email}: {str(e)}")
            
            # Log failed email
            EmailLog.objects.create(
                user=user,
                email_type=email_type,
                recipient_email=user.email,
                subject=subject,
                success=False,
                error_message=str(e)
            )