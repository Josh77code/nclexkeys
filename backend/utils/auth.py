# users/utils.py
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
from users.models import (
    User, EmailVerificationToken, PasswordResetToken, 
    RefreshToken, LoginAttempt, UserSession, EmailLog
)
from courses.models import Course
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
        # Convert Django timezone-aware datetime to Unix timestamps
        now = timezone.now()
        iat = int(now.timestamp())
        exp = int((now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_LIFETIME)).timestamp())
        
        payload = {
            'user_id': str(user.id),
            'email': user.email,
            'role': user.role,
            'exp': exp,  # Unix timestamp (integer)
            'iat': iat,  # Unix timestamp (integer)
            'type': 'access'
        }
        
        # Debug logging
        print(f"Generating token with payload: {payload}")
        print(f"Token expires at: {timezone.datetime.fromtimestamp(exp, tz=timezone.get_current_timezone())}")
        
        token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm='HS256')
        print(f"Generated token: {token[:50]}...")
        
        return token
    
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
        """Verify JWT access token and return (payload, error_info)"""
        try:
            # Decode JWT token
            payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
            
            # Check if it's an access token
            if payload.get('type') != 'access':
                return None, {
                    'error_code': 'INVALID_TOKEN_TYPE',
                    'message': 'Invalid token type. Access token required.'
                }
            
            logger.info("Token verification successful")
            return payload, None
            
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None, {
                'error_code': 'TOKEN_EXPIRED',
                'message': 'Your session has expired. Please login again.'
            }
            
        except jwt.InvalidTokenError:
            logger.warning("Invalid token")
            return None, {
                'error_code': 'TOKEN_INVALID',
                'message': 'Invalid authentication token. Please login again.'
            }
            
        except Exception as e:
            logger.error(f"Token verification error: {str(e)}")
            return None, {
                'error_code': 'AUTH_ERROR',
                'message': 'Authentication failed. Please try again.'
            }
        
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
        html_message = render_to_string('emails/student/verification.html', context)
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
        html_message = render_to_string('emails/student/password_reset.html', context)
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
        html_message = render_to_string('emails/student/login_alert.html', context)
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
        html_message = render_to_string('emails/student/new_device.html', context)
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
        html_message = render_to_string('emails/student/password_changed.html', context)
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
        html_message = render_to_string('emails/student/account_locked.html', context)
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
        html_message = render_to_string("emails/student/account_deletion_requested.html", context)
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
        html_message = render_to_string("emails/student/account_deletion_cancelled.html", context)
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
        html_message = render_to_string("emails/student/account_deleted.html", context)
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
        html_message = render_to_string('emails/student/emergency_2fa_disable.html', context)
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
        html_message = render_to_string('emails/platform_admin/2fa_emergency_disabled.html', context)
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
        html_message = render_to_string('emails/platform_admin/2fa_emergency_rejected.html', context)
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
        html_message = render_to_string('emails/student/deletion_reminder.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='deletion_reminder',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_enrollment_confirmation(user, course, enrollment):
        """Send course enrollment confirmation email"""
        user_timezone = getattr(user, 'timezone', 'UTC')

        context = {
            'user': user,
            'course': course,
            'enrollment': enrollment,
            'course_url': f"{settings.SITE_URL}/courses/{course.id}",
            'dashboard_url': f"{settings.SITE_URL}/dashboard",
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.SITE_URL
        }

        subject = f"Enrollment Confirmation - {course.title}"
        html_message = render_to_string('emails/student/enrollment_confirmation.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='enrollment_confirmation',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_refund_request_confirmation(user, refund):
        '''Send refund request confirmation to user'''
        try:
            context = {
                'user': user,
                'refund': refund,
                'course': refund.payment.course,
                'amount': refund.amount,
                'currency': refund.payment.currency,
                'reference': refund.payment.reference,
            }

            subject = f"Refund Request Confirmation - {refund.payment.course.title}"
            html_message = render_to_string('emails/student/refund_request_confirmation.html', context)
            plain_message = strip_tags(html_message)

            EmailService._send_email(
                user=user,
                email_type='refund_request',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            
        except Exception as e:
            logger.error(f"Failed to send refund confirmation email: {str(e)}")

    @staticmethod
    def send_refund_completed_notification(user, refund):
        '''Send refund completion notification to user'''
        try:
            context = {
                'user': user,
                'refund': refund,
                'course': refund.payment.course,
                'amount': refund.amount,
                'currency': refund.payment.currency,
            }

            subject = f"Refund Completed - {refund.payment.course.title}"
            html_message = render_to_string('emails/student/refund_completed_notification.html', context)
            plain_message = strip_tags(html_message)
            
            EmailService._send_email(
                user=user,
                email_type='refund_completed',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            
        except Exception as e:
            logger.error(f"Failed to send refund completion email: {str(e)}")
    
    @staticmethod
    def send_refund_review_notification(refund):
        '''Send refund review notification to super admins'''
        try:
            super_admin_users = User.objects.filter(
                role='super_admin',
                is_active=True
            )
            
            if not super_admin_users:
                return
            
            context = {
                'refund': refund,
                'user': refund.user,
                'course': refund.payment.course,
                'payment': refund.payment,
            }

            subject = f"Refund Review Required - {refund.amount} {refund.payment.currency}"
            html_message = render_to_string('emails/platform_admin/refund_review_required.html', context)
            plain_message = strip_tags(html_message)

            for admin_user in super_admin_users:
                EmailService._send_email(
                    user=admin_user,
                    email_type='refund_review',
                    subject=subject,
                    html_message=html_message,
                    plain_message=plain_message
                )

                
        except Exception as e:
            logger.error(f"Failed to send refund review notification: {str(e)}")

    @staticmethod
    def send_course_completion_notification(user, course):
        """Send course completion notification"""
        user_timezone = getattr(user, 'timezone', 'UTC')

        context = {
            'user': user,
            'course': course,
            'completion_date': EmailService._convert_to_user_timezone(timezone.now(), user_timezone),
            'certificate_url': f"{settings.SITE_URL}/courses/{course.id}/certificate",
            'dashboard_url': f"{settings.SITE_URL}/dashboard",
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.SITE_URL
        }

        subject = f"🎉 Course Completed - {course.title}"
        html_message = render_to_string('emails/student/course_completion.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='course_completion',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_new_review_notification(review):
        """Send notification to super admins about new course review"""
        admin_emails = User.objects.filter(
            role="super_admin",
            is_active=True
        ).values_list('email', flat=True)

        if not admin_emails:
            return

        context = {
            'review': review,
            'course': review.course,
            'user': review.user,
            'admin_url': f"{settings.SITE_URL}/admin/courses/coursereview/{review.id}/change/",
            'course_url': f"{settings.SITE_URL}/courses/{review.course.id}",
            'site_url': settings.SITE_URL
        }

        subject = f"New Course Review - {review.course.title}"
        html_message = render_to_string('emails/platform_admin/new_review_notification.html', context)
        plain_message = strip_tags(html_message)

        for admin_email in admin_emails:
            try:
                send_mail(
                    subject=subject,
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[admin_email],
                    html_message=html_message,
                    fail_silently=False
                )
            except Exception as e:
                logger.error(f"Failed to send review notification to {admin_email}: {str(e)}")

    @staticmethod
    def send_review_approved_notification(user, review):
        """Send review approval notification email"""
        context = {
            'user': user,
            'review': review,
            'course': review.course,
            'course_url': f"{settings.SITE_URL}/courses/{review.course.id}",
            'dashboard_url': f"{settings.SITE_URL}/dashboard",
            'reviews_url': f"{settings.SITE_URL}/courses/{review.course.id}#reviews",
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.SITE_URL
        }

        subject = f"Your Review Has Been Approved - {review.course.title}"
        html_message = render_to_string('emails/student/review_approved.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='review_approved',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_review_rejected_notification(user, review, rejection_reason=''):
        """Send review rejection notification email"""
        context = {
            'user': user,
            'review': review,
            'course': review.course,
            'rejection_reason': rejection_reason,
            'course_url': f"{settings.FRONTEND_URL}/courses/{review.course.id}",
            'dashboard_url': f"{settings.FRONTEND_URL}/dashboard",
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.FRONTEND_URL,
            'review_guidelines_url': f"{settings.FRONTEND_URL}/review-guidelines",
            'resubmit_url': f"{settings.FRONTEND_URL}/courses/{review.course.id}/review"
        }

        subject = f"Review Update Required - {review.course.title}"
        html_message = render_to_string('emails/student/review_approved.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='review_approved',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )


    @staticmethod
    def send_exam_started_notification(user, exam, attempt):
        """Send exam started notification"""
        user_timezone = getattr(user, 'timezone', 'UTC')

        context = {
            'user': user,
            'exam': exam,
            'attempt': attempt,
            'course': exam.course,
            'exam_url': f"{settings.SITE_URL}/exams/{exam.id}/attempt/{attempt.id}",
            'time_limit': exam.time_limit_minutes,
            'started_at': EmailService._convert_to_user_timezone(attempt.started_at, user_timezone),
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.SITE_URL
        }

        subject = f"Exam Started - {exam.title}"
        html_message = render_to_string('emails/student/exam_started.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='exam_started',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_exam_completed_notification(user, attempt):
        """Send exam completion notification"""
        user_timezone = getattr(user, 'timezone', 'UTC')

        context = {
            'user': user,
            'attempt': attempt,
            'exam': attempt.exam,
            'course': attempt.exam.course,
            'score': attempt.percentage_score,
            'passed': attempt.passed,
            'completed_at': EmailService._convert_to_user_timezone(attempt.completed_at, user_timezone),
            'time_taken': attempt.time_taken_minutes,
            'results_url': f"{settings.SITE_URL}/exams/{attempt.exam.id}/results/{attempt.id}",
            'course_url': f"{settings.SITE_URL}/courses/{attempt.exam.course.id}",
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.SITE_URL
        }

        subject = f"Exam {'Passed' if attempt.passed else 'Completed'} - {attempt.exam.title}"
        html_message = render_to_string('emails/student/exam_completed.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='exam_completed',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_certificate_awarded_notification(user, certificate):
        """Send certificate awarded notification"""
        user_timezone = getattr(user, 'timezone', 'UTC')

        context = {
            'user': user,
            'certificate': certificate,
            'exam': certificate.exam,
            'course': certificate.exam.course,
            'issued_at': EmailService._convert_to_user_timezone(certificate.issued_at, user_timezone),
            'certificate_url': certificate.certificate_url,
            'download_url': f"{settings.SITE_URL}/certificates/{certificate.id}/download",
            'verify_url': f"{settings.SITE_URL}/certificates/{certificate.certificate_number}/verify",
            'support_email': 'support@nclexvirtualschool.com',
            'site_url': settings.SITE_URL
        }

        subject = f"🏆 Certificate Awarded - {certificate.exam.title}"
        html_message = render_to_string('emails/student/certificate_awarded.html', context)
        plain_message = strip_tags(html_message)

        EmailService._send_email(
            user=user,
            email_type='certificate_awarded',
            subject=subject,
            html_message=html_message,
            plain_message=plain_message
        )

    @staticmethod
    def send_course_moderation_notification(course, action, reason):
        """Notify instructor about course moderation status"""
        try:
            instructor = course.created_by
        
            context = {
                'instructor': instructor,
                'course': course,
                'action': action,
                'reason': reason,
                'dashboard_url': f"{settings.FRONTEND_URL}/admin/dashboard",
                'course_url': f"{settings.FRONTEND_URL}/admin/courses/{course.id}"
            }
            
            subject = f"Course {action.capitalize()} Notification: {course.title}"
            html_message = render_to_string('emails/instructor/course_moderation.html', context)
            plain_message = strip_tags(html_message)
            
            EmailService._send_email(
                user=instructor,
                email_type='course_moderation',
                subject=subject,
                html_message=html_message,
                plain_message=f"Your course '{course.title}' has been {action}d. Reason: {reason}"
            )
            
        except Exception as e:
            logger.error(f"Failed to send course moderation notification: {str(e)}")

    # @staticmethod
    # def send_instructor_status_notification(instructor, action, reason):
    #     """Notify instructor about their account status change"""
    #     try:
            
    #         context = {
    #             'instructor': instructor,
    #             'action': action,
    #             'reason': reason,
    #             'dashboard_url': f"{settings.FRONTEND_URL}/admin/dashboard",
    #             'support_url': f"{settings.FRONTEND_URL}/support"
    #         }

    #         subject = f"Your Account Status: {action.capitalize()}"
    #         html_message = render_to_string('emails/instructor/instructor_status.html', context)
    #         plain_message = strip_tags(html_message)
            
    #         EmailService._send_email(
    #             user=instructor,
    #             email_type='instructor_status',
    #             subject=subject,
    #             html_message=html_message,
    #             plain_message=f"Your instructor account has been {action}d. Reason: {reason}"
    #         )
            
    #     except Exception as e:
    #         logger.error(f"Failed to send instructor status notification: {str(e)}")

    
    @staticmethod
    def send_instructor_status_notification(instructor, action, reason, additional_context=None):
        """Send notification when instructor status changes"""
        action_messages = {
            'activate': {
                'subject': 'Your Instructor Account Has Been Activated - Welcome Back!',
                'template': 'emails/instructor/instructor_activated.html',
                'message': 'Your instructor account has been activated. You can now create and manage courses.'
            },
            'deactivate': {
                'subject': 'Your Instructor Account Has Been Temporarily Deactivated',
                'template': 'emails/instructor/instructor_deactivated.html',
                'message': 'Your instructor account has been temporarily deactivated. Your courses are temporarily unavailable.'
            },
            'suspend': {
                'subject': 'URGENT: Your Instructor Account Has Been Suspended',
                'template': 'emails/instructor/instructor_suspended.html',
                'message': 'Your instructor account has been suspended. Please contact support immediately.'
            }
        }
        
        notification = action_messages.get(action)
        if not notification:
            return
        
        # Build context with additional info for activation emails
        context = {
            'instructor_name': instructor.full_name,
            'action': action,
            'reason': reason,
            'message': notification['message'],
            'support_email': settings.SUPPORT_EMAIL,
            'platform_name': settings.PLATFORM_NAME,
            'dashboard_url': f"{settings.FRONTEND_URL}/instructor/dashboard"
        }
        
        # Add additional context if provided (like course counts for activation)
        if additional_context:
            context.update(additional_context)
    
        subject = notification['subject']
        html_message = render_to_string(notification['template'], context)
        plain_message = strip_tags(html_message)
        
        try:
            EmailService._send_email(
                user=instructor,
                email_type=f'instructor_{action}',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            logger.info(f"Instructor {action} notification sent to {instructor.email}")
        except Exception as e:
            logger.error(f"Failed to send instructor {action} notification: {str(e)}")
            raise
        
    @staticmethod
    def send_bulk_course_reactivation_notification(instructor, courses, reason):
        """Send notification when courses are bulk reactivated due to instructor activation"""
        course_list = []
        for course in courses[:10]:  # Limit to 10 for email display
            course_list.append({
                'title': course.title, 
                'id': str(course.id)
            })
        
        # Check if instructor has any suspended courses
        suspended_courses_exist = Course.objects.filter(
            created_by=instructor,
            moderation_status='suspended'
        ).exists()
        
        context = {
            'instructor_name': instructor.full_name,
            'courses': course_list,
            'total_courses': courses.count(),
            'reason': reason,
            'platform_name': settings.PLATFORM_NAME,
            'dashboard_url': f"{settings.FRONTEND_URL}/instructor/dashboard",
            'support_email': settings.SUPPORT_EMAIL,
            'suspended_courses_exist': suspended_courses_exist
        }
    
        subject = f'Your {courses.count()} Courses Have Been Reactivated - {settings.PLATFORM_NAME}'
        html_message = render_to_string('emails/instructor/courses_reactivated.html', context)
        plain_message = strip_tags(html_message)
        
        try:
            EmailService._send_email(
                user=instructor,
                email_type='courses_reactivated',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            logger.info(f"Course reactivation notification sent to {instructor.email}")
        except Exception as e:
            logger.error(f"Failed to send course reactivation notification: {str(e)}")
            raise


    @staticmethod
    def send_weekly_moderation_summary(admin, stats):
        """Send weekly moderation summary to super admin"""
        context = {
            'admin_name': admin.full_name,
            'stats': stats,
            'platform_name': settings.PLATFORM_NAME,
            'admin_dashboard_url': f"{settings.FRONTEND_URL}/super-admin/dashboard",
            'week_ending': timezone.now().strftime('%B %d, %Y')
        }

        subject = f'Weekly Moderation Summary - {settings.PLATFORM_NAME}'
        html_message = render_to_string('emails/platform_admin/weekly_moderation_summary.html', context)
        plain_message = strip_tags(html_message)

        try:
            EmailService._send_email(
                user=admin,
                email_type='weekly_moderation_summary',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            logger.info(f"Weekly moderation summary sent to {admin.email}")
        except Exception as e:
            logger.error(f"Failed to send weekly summary: {str(e)}")
            raise

    @staticmethod
    def send_course_appeal_notification(appeal):
        """Notify super admins when new course appeal is submitted"""
        super_admins = User.objects.filter(role='super_admin', is_active=True)

        context = {
            'appeal': appeal,
            'course_title': appeal.course.title,
            'instructor_name': appeal.instructor.full_name,
            'instructor_email': appeal.instructor.email,
            'appeal_reason': appeal.appeal_reason,
            'platform_name': settings.PLATFORM_NAME,
            'review_url': f"{settings.FRONTEND_URL}/super-admin/appeals/{appeal.id}",
            'appeals_dashboard_url': f"{settings.FRONTEND_URL}/super-admin/appeals"
        }

        subject = f'New Course Appeal: {appeal.course.title}'
        html_message = render_to_string('emails/platform_admin/new_course_appeal.html', context)
        plain_message = strip_tags(html_message)

        for admin in super_admins:
            try:
                EmailService._send_email(
                    user=admin,
                    email_type='new_course_appeal',
                    subject=subject,
                    html_message=html_message,
                    plain_message=plain_message
                )
            except Exception as e:
                logger.error(f"Failed to send appeal notification to {admin.email}: {str(e)}")

    @staticmethod
    def send_appeal_confirmation_to_instructor(appeal):
        """Send confirmation to instructor when appeal is submitted"""
        context = {
            'instructor_name': appeal.instructor.full_name,
            'course_title': appeal.course.title,
            'appeal_reason': appeal.appeal_reason,
            'appeal_id': str(appeal.id),
            'submitted_at': appeal.created_at,
            'platform_name': settings.PLATFORM_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'appeals_url': f"{settings.FRONTEND_URL}/instructor/appeals"
        }

        subject = f'Appeal Submitted: {appeal.course.title}'
        html_message = render_to_string('emails/instructor/appeal_confirmation.html', context)
        plain_message = strip_tags(html_message)

        try:
            EmailService._send_email(
                user=appeal.instructor,
                email_type='appeal_confirmation',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            logger.info(f"Appeal confirmation sent to {appeal.instructor.email}")
        except Exception as e:
            logger.error(f"Failed to send appeal confirmation: {str(e)}")
            raise

    @staticmethod
    def send_appeal_decision_notification(appeal, decision):
        """Notify instructor of appeal decision"""
        context = {
            'instructor_name': appeal.instructor.full_name,
            'course_title': appeal.course.title,
            'decision': decision,
            'review_notes': appeal.review_notes,
            'reviewed_by': appeal.reviewed_by.full_name,
            'reviewed_at': appeal.reviewed_at,
            'platform_name': settings.PLATFORM_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'course_url': f"{settings.FRONTEND_URL}/instructor/courses/{appeal.course.id}" if decision == 'approved' else None
        }

        subject = f'Appeal {decision.title()}: {appeal.course.title}'
        template = f'emails/instructor/appeal_{decision}.html'
        html_message = render_to_string(template, context)
        plain_message = strip_tags(html_message)

        try:
            EmailService._send_email(
                user=appeal.instructor,
                email_type=f'appeal_{decision}',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            logger.info(f"Appeal {decision} notification sent to {appeal.instructor.email}")
        except Exception as e:
            logger.error(f"Failed to send appeal {decision} notification: {str(e)}")
            raise

    @staticmethod
    def send_course_status_notification(course, action, reason):
        """Notify instructor when course status changes (bulk actions)"""
        context = {
            'instructor_name': course.created_by.full_name,
            'course_title': course.title,
            'action': action,
            'reason': reason,
            'new_status': course.moderation_status,
            'platform_name': settings.PLATFORM_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'course_url': f"{settings.FRONTEND_URL}/instructor/courses/{course.id}" if action == 'approve' else None
        }

        subject = f'Course {action.title()}d: {course.title}'
        template = f'emails/instructor/course_{action}d.html'
        html_message = render_to_string(template, context)
        plain_message = strip_tags(html_message)

        try:
            EmailService._send_email(
                user=course.created_by,
                email_type=f'course_{action}d',
                subject=subject,
                html_message=html_message,
                plain_message=plain_message
            )
            logger.info(f"Course {action} notification sent to {course.created_by.email}")
        except Exception as e:
            logger.error(f"Failed to send course {action} notification: {str(e)}")
            raise

    @staticmethod
    def send_course_reactivation_to_students(course):
        """Notify enrolled students when their course is reactivated"""
        # Get active enrollments for the course
        active_enrollments = course.enrollments.filter(
            is_active=True,
            payment_status='completed'
        ).select_related('user')

        if not active_enrollments.exists():
            return

        context = {
            'course_title': course.title,
            'course_type': course.course_type,
            'instructor_name': course.created_by.full_name,
            'platform_name': settings.PLATFORM_NAME,
            'course_url': f"{settings.FRONTEND_URL}/courses/{course.id}",
            'continue_learning_url': f"{settings.FRONTEND_URL}/my-courses/{course.id}"
        }

        subject = f'Good News! Your Course "{course.title}" is Available Again'
        html_message = render_to_string('emails/student/course_reactivated.html', context)
        plain_message = strip_tags(html_message)

        # Send to each enrolled student
        for enrollment in active_enrollments:
            try:
                student_context = context.copy()
                student_context['student_name'] = enrollment.user.full_name

                # Re-render with student-specific context
                html_message = render_to_string('emails/student/course_reactivated.html', student_context)
                plain_message = strip_tags(html_message)

                EmailService._send_email(
                    user=enrollment.user,
                    email_type='course_reactivated',
                    subject=subject,
                    html_message=html_message,
                    plain_message=plain_message
                )
            except Exception as e:
                logger.error(f"Failed to send reactivation notification to student {enrollment.user.email}: {str(e)}")

        logger.info(f"Course reactivation notifications sent to {active_enrollments.count()} students for course: {course.title}")

    @staticmethod
    def send_course_suspension_to_students(course, reason):
        """Notify enrolled students when their course is suspended"""
        active_enrollments = course.enrollments.filter(
            is_active=True,
            payment_status='completed'
        ).select_related('user')

        if not active_enrollments.exists():
            return

        context = {
            'course_title': course.title,
            'instructor_name': course.created_by.full_name,
            'suspension_reason': reason,
            'platform_name': settings.PLATFORM_NAME,
            'support_email': settings.SUPPORT_EMAIL,
            'my_courses_url': f"{settings.FRONTEND_URL}/my-courses",
            'browse_courses_url': f"{settings.FRONTEND_URL}/courses",
            'suspended_at': course.moderated_at or timezone.now(),
        }

        subject = f'Important Update: Course "{course.title}" Temporarily Unavailable'

        for enrollment in active_enrollments:
            try:
                student_context = context.copy()
                student_context['student_name'] = enrollment.user.full_name

                html_message = render_to_string('emails/student/course_suspend.html', student_context)
                plain_message = strip_tags(html_message)

                EmailService._send_email(
                    user=enrollment.user,
                    email_type='course_suspended',
                    subject=subject,
                    html_message=html_message,
                    plain_message=plain_message
                )
            except Exception as e:
                logger.error(f"Failed to send suspension notification to student {enrollment.user.email}: {str(e)}")

        logger.info(f"Course suspension notifications sent to {active_enrollments.count()} students for course: {course.title}")

    @staticmethod
    def send_instructor_status_change_to_students(instructor, action, affected_courses):
        """Notify students when their instructor's status changes affecting their courses"""
        if not affected_courses:
            return

        # Get all students enrolled in affected courses
        student_enrollments = {}
        for course in affected_courses:
            enrollments = course.enrollments.filter(
                is_active=True,
                payment_status='completed'
            ).select_related('user')

            for enrollment in enrollments:
                if enrollment.user.id not in student_enrollments:
                    student_enrollments[enrollment.user.id] = {
                        'user': enrollment.user,
                        'courses': []
                    }
                student_enrollments[enrollment.user.id]['courses'].append(course)

        if not student_enrollments:
            return

        # Email context based on action
        action_contexts = {
            'activate': {
                'subject': f'Great News! Your Instructor {instructor.full_name} is Back',
                'template': 'emails/student/instructor_reactivated.html',
                'message': 'has returned and your courses are now available again'
            },
            'deactivate': {
                'subject': f'Temporary Update: Courses by {instructor.full_name}',
                'template': 'emails/student/instructor_deactivated.html',
                'message': 'is temporarily unavailable, affecting some of your courses'
            },
            'suspend': {
                'subject': f'Important: Courses by {instructor.full_name} Temporarily Unavailable', 
                'template': 'emails/student/instructor_suspended.html',
                'message': 'is temporarily unavailable, affecting your enrolled courses'
            }
        }

        action_context = action_contexts.get(action)
        if not action_context:
            return

        # Send personalized emails to each student
        for student_data in student_enrollments.values():
            try:
                context = {
                    'student_name': student_data['user'].full_name,
                    'instructor_name': instructor.full_name,
                    'action': action,
                    'message': action_context['message'],
                    'affected_courses': [
                        {
                            'title': course.title,
                            'id': str(course.id),
                            'course_type': course.course_type
                        } for course in student_data['courses']
                    ],
                    'courses_count': len(student_data['courses']),
                    'platform_name': settings.PLATFORM_NAME,
                    'support_email': settings.SUPPORT_EMAIL,
                    'my_courses_url': f"{settings.FRONTEND_URL}/my-courses",
                    'browse_courses_url': f"{settings.FRONTEND_URL}/courses"
                }

                html_message = render_to_string(action_context['template'], context)
                plain_message = strip_tags(html_message)

                EmailService._send_email(
                    user=student_data['user'],
                    email_type=f'instructor_{action}_student_notification',
                    subject=action_context['subject'],
                    html_message=html_message,
                    plain_message=plain_message
                )
            except Exception as e:
                logger.error(f"Failed to send instructor {action} notification to student {student_data['user'].email}: {str(e)}")

        logger.info(f"Instructor {action} notifications sent to {len(student_enrollments)} students")

    
    @staticmethod
    def send_instructor_sale_notification(instructor, payment):
        """Notify instructor about a new course sale"""
        try:
            course = payment.course
            student = payment.user
            
            # Calculate instructor earnings (70%)
            instructor_earning = float(payment.amount) * 0.70
            platform_fee = float(payment.amount) * 0.30
            
            context = {
                'instructor': instructor,
                'course': course,
                'student': student,
                'payment': payment,
                'instructor_earning': instructor_earning,
                'platform_fee': platform_fee,
                'payment_date': payment.paid_at,
                'dashboard_url': f"{settings.FRONTEND_URL}/admin/dashboard",
                'course_url': f"{settings.FRONTEND_URL}/admin/courses/{course.id}",
                'earnings_url': f"{settings.FRONTEND_URL}/admin/earnings",
                'student_count': course.enrollments.filter(payment_status='completed').count()
            }

            subject = f"🎉 New Sale: {course.title} - ₦{payment.amount:,.2f}"
            html_message = render_to_string('emails/instructor/sale_notification.html', context)
            plain_message = strip_tags(html_message)
            
            EmailService._send_email(
                user=instructor,
                email_type='instructor_sale',
                subject=subject,
                html_message=html_message,
                plain_message=f"Great news! {student.full_name} just purchased your course '{course.title}' for ₦{payment.amount}. You'll earn ₦{instructor_earning:.2f} from this sale."
            )
            
        except Exception as e:
            logger.error(f"Failed to send instructor sale notification: {str(e)}")
    
    @staticmethod
    def send_payout_completed_notification(payout):
        """Notify instructor about completed payout"""
        try:
            instructor = payout.instructor
            
            context = {
                'instructor': instructor,
                'payout': payout,
                'period_start': payout.period_start,
                'period_end': payout.period_end,
                'total_revenue': payout.total_revenue,
                'instructor_share': payout.instructor_share,
                'platform_fee': payout.platform_fee,
                'net_payout': payout.net_payout,
                'dashboard_url': f"{settings.FRONTEND_URL}/admin/dashboard",
                'earnings_url': f"{settings.FRONTEND_URL}/admin/earnings"
            }

            subject = f"💰 Payout Completed - ₦{payout.net_payout:,.2f}"
            html_message = render_to_string('emails/instructor/payout_completed.html', context)
            plain_message = strip_tags(html_message)
            
            EmailService._send_email(
                user=instructor,
                email_type='payout_completed',
                subject=subject,
                html_message=html_message,
                plain_message=f"Your payout of ₦{payout.net_payout} for the period {payout.period_start} to {payout.period_end} has been completed."
            )
            
        except Exception as e:
            logger.error(f"Failed to send payout completed notification: {str(e)}")
    
    @staticmethod
    def send_monthly_earnings_summary(instructor, earnings_data):
        """Send monthly earnings summary to instructor"""
        try:
            
            context = {
                'instructor': instructor,
                'month_year': earnings_data['month_year'],
                'total_sales': earnings_data['total_sales'],
                'total_revenue': earnings_data['total_revenue'],
                'instructor_earnings': earnings_data['instructor_earnings'],
                'platform_fee': earnings_data['platform_fee'],
                'top_courses': earnings_data['top_courses'],
                'new_students': earnings_data['new_students'],
                'dashboard_url': f"{settings.FRONTEND_URL}/admin/dashboard",
                'earnings_url': f"{settings.FRONTEND_URL}/admin/earnings"
            }

            subject = f"📊 Monthly Earnings Summary - {earnings_data['month_year']}"
            html_message = render_to_string('emails/instructor/monthly_earnings_summary.html', context)
            plain_message = strip_tags(html_message)
            
            EmailService._send_email(
                user=instructor,
                email_type='monthly_earnings_summary',
                subject=subject,
                html_message=html_message,
                plain_message=f"Your earnings summary for {earnings_data['month_year']}: ₦{earnings_data['instructor_earnings']} from {earnings_data['total_sales']} sales."
            )
            
        except Exception as e:
            logger.error(f"Failed to send monthly earnings summary: {str(e)}")
    
    @staticmethod
    def send_refund_deduction_notification(instructor, refund, payout_impact):
        """Notify instructor about refund impact on payouts"""
        try:
            
            context = {
                'instructor': instructor,
                'refund': refund,
                'course': refund.payment.course,
                'refund_amount': refund.amount,
                'impact_amount': payout_impact['deduction'],
                'next_payout_date': payout_impact['next_payout_date'],
                'dashboard_url': f"{settings.FRONTEND_URL}/admin/dashboard",
                'earnings_url': f"{settings.FRONTEND_URL}/admin/earnings"
            }

            subject = f"⚠️ Refund Processed - Payout Adjustment"
            html_message = render_to_string('emails/instructor/refund_deduction.html', context)
            plain_message = strip_tags(html_message)
            
            EmailService._send_email(
                user=instructor,
                email_type='refund_deduction',
                subject=subject,
                html_message=html_message,
                plain_message=f"A refund of ₦{refund.amount} has been processed for your course. This will be deducted from your next payout."
            )
            
        except Exception as e:
            logger.error(f"Failed to send refund deduction notification: {str(e)}")


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