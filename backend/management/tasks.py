# tasks.py
from celery import shared_task
from django.core.management import call_command
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3)
def cleanup_old_records(self):
    """
    Celery task to clean up old records
    Run this daily via celery beat
    """
    try:
        call_command('cleanup_records', '--force')
        logger.info('Scheduled cleanup task completed successfully')
    except Exception as e:
        logger.error(f'Scheduled cleanup task failed: {str(e)}')
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60 * (2 ** self.request.retries), exc=e)
        raise

@shared_task(bind=True, max_retries=2)
def cleanup_expired_tokens(self):
    """
    Celery task to clean up expired tokens only
    Run this more frequently (every 6 hours)
    """
    from ..users.models import EmailVerificationToken, PasswordResetToken, RefreshToken
    
    try:
        now = timezone.now()
        cleanup_count = 0
        
        with transaction.atomic():
            # Clean expired verification tokens
            verification_count = EmailVerificationToken.objects.filter(
                expires_at__lt=now
            ).count()
            EmailVerificationToken.objects.filter(expires_at__lt=now).delete()
            
            # Clean expired reset tokens
            reset_count = PasswordResetToken.objects.filter(
                expires_at__lt=now
            ).count()
            PasswordResetToken.objects.filter(expires_at__lt=now).delete()
            
            # Clean expired refresh tokens
            refresh_count = RefreshToken.objects.filter(
                expires_at__lt=now
            ).count()
            RefreshToken.objects.filter(expires_at__lt=now).delete()
            
            cleanup_count = verification_count + reset_count + refresh_count
        
        logger.info(f'Token cleanup completed - removed {cleanup_count} expired tokens')
        
    except Exception as e:
        logger.error(f'Token cleanup failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=30 * (2 ** self.request.retries), exc=e)
        raise

@shared_task(bind=True, max_retries=3)
def process_scheduled_deletions(self):
    """
    Process users scheduled for deletion
    Run this daily - This is important for user privacy compliance
    """
    from ..users.models import User
    
    try:
        now = timezone.now()
        users_to_delete = User.objects.filter(
            is_deletion_pending=True,
            deletion_scheduled_for__lt=now
        )
        
        count = 0
        for user in users_to_delete:
            try:
                with transaction.atomic():
                    logger.info(f'Processing scheduled deletion for user: {user.email}')
                    # Send final deletion notification before deleting
                    try:
                        from ..users.utils import EmailService
                        EmailService.send_account_deleted_email(user)
                    except Exception as email_error:
                        logger.warning(f'Failed to send deletion notification to {user.email}: {email_error}')
                    
                    user.delete()
                    count += 1
            except Exception as delete_error:
                logger.error(f'Failed to delete user {user.email}: {delete_error}')
                continue
        
        logger.info(f'Processed {count} scheduled account deletions')
        
    except Exception as e:
        logger.error(f'Scheduled deletion processing failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=120 * (2 ** self.request.retries), exc=e)
        raise

@shared_task(bind=True, max_retries=2)
def cleanup_inactive_sessions(self):
    """
    Clean up inactive user sessions
    Run this every 12 hours
    """
    from ..users.models import UserSession
    
    try:
        now = timezone.now()
        cutoff_date = now - timedelta(days=30)  # Sessions inactive for 30 days
        
        inactive_sessions = UserSession.objects.filter(
            last_activity__lt=cutoff_date,
            is_active=False
        )
        
        count = inactive_sessions.count()
        inactive_sessions.delete()
        
        logger.info(f'Cleaned up {count} inactive sessions')
        
    except Exception as e:
        logger.error(f'Session cleanup failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        raise

@shared_task(bind=True, max_retries=2)
def cleanup_old_login_attempts(self):
    """
    Clean up old login attempts
    Run this weekly
    """
    from ..users.models import LoginAttempt
    
    try:
        now = timezone.now()
        cutoff_date = now - timedelta(days=90)  # Keep 90 days of login attempts
        
        old_attempts = LoginAttempt.objects.filter(
            created_at__lt=cutoff_date
        )
        
        count = old_attempts.count()
        old_attempts.delete()
        
        logger.info(f'Cleaned up {count} old login attempts')
        
    except Exception as e:
        logger.error(f'Login attempts cleanup failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        raise

@shared_task(bind=True, max_retries=2)
def cleanup_old_email_logs(self):
    """
    Clean up old email logs (keep for audit purposes but not indefinitely)
    Run this monthly
    """
    from ..users.models import EmailLog
    
    try:
        now = timezone.now()
        cutoff_date = now - timedelta(days=180)  # Keep 6 months of email logs
        
        old_logs = EmailLog.objects.filter(
            sent_at__lt=cutoff_date
        )
        
        count = old_logs.count()
        old_logs.delete()
        
        logger.info(f'Cleaned up {count} old email logs')
        
    except Exception as e:
        logger.error(f'Email logs cleanup failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        raise
    

@shared_task(bind=True, max_retries=2)
def send_deletion_reminders(self):
    """
    Send reminders to users about pending account deletions
    Run this daily
    """
    from ..users.models import User
    
    try:
        now = timezone.now()
        
        # Users with deletion in 7 days
        reminder_date_7 = now + timedelta(days=7)
        users_7_days = User.objects.filter(
            is_deletion_pending=True,
            deletion_scheduled_for__date=reminder_date_7.date()
        )
        
        # Users with deletion in 1 day
        reminder_date_1 = now + timedelta(days=1)
        users_1_day = User.objects.filter(
            is_deletion_pending=True,
            deletion_scheduled_for__date=reminder_date_1.date()
        )
        
        try:
            from ..users.utils import EmailService
            
            for user in users_7_days:
                EmailService.send_deletion_reminder(user, days_remaining=7)
            
            for user in users_1_day:
                EmailService.send_deletion_reminder(user, days_remaining=1)
                
        except Exception as email_error:
            logger.error(f'Failed to send deletion reminders: {email_error}')
        
        total_reminders = users_7_days.count() + users_1_day.count()
        logger.info(f'Sent {total_reminders} deletion reminder emails')
        
    except Exception as e:
        logger.error(f'Deletion reminder task failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=60, exc=e)
        raise

@shared_task(bind=True, max_retries=1)
def database_health_check(self):
    """
    Perform database health checks and report anomalies
    Run this daily
    """
    from ..users.models import User, LoginAttempt, EmailLog
    from django.db import connection
    
    try:
        health_report = {}
        
        # Check for unusually high failed login attempts
        recent_failures = LoginAttempt.objects.filter(
            created_at__gte=timezone.now() - timedelta(hours=24),
            success=False
        ).count()
        
        if recent_failures > 1000:  # Threshold for concern
            health_report['high_failed_logins'] = recent_failures
        
        # Check for users with many failed attempts
        problematic_users = User.objects.filter(
            failed_login_attempts__gte=3
        ).count()
        
        if problematic_users > 100:  # Threshold for concern
            health_report['users_with_failed_attempts'] = problematic_users
        
        # Check email sending failures
        failed_emails = EmailLog.objects.filter(
            sent_at__gte=timezone.now() - timedelta(hours=24),
            success=False
        ).count()
        
        if failed_emails > 50:  # Threshold for concern
            health_report['failed_emails'] = failed_emails
        
        # Check database size (PostgreSQL specific)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT pg_size_pretty(pg_database_size(current_database()));
            """)
            db_size = cursor.fetchone()[0]
            health_report['database_size'] = db_size
        
        if health_report:
            logger.warning(f'Database health check found issues: {health_report}')
        else:
            logger.info('Database health check passed')
        
    except Exception as e:
        logger.error(f'Database health check failed: {str(e)}')
        if self.request.retries < self.max_retries:
            raise self.retry(countdown=300, exc=e)
        # Don't raise on final failure for health checks