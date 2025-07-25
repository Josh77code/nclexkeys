# cleanup_records
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from ..users.models import (
    EmailVerificationToken, PasswordResetToken, RefreshToken, 
    LoginAttempt, UserSession, EmailLog, User
)
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Clean up old records to prevent database bloat'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force deletion without confirmation',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        if not force and not dry_run:
            confirm = input('This will permanently delete old records. Continue? (y/N): ')
            if confirm.lower() != 'y':
                self.stdout.write('Operation cancelled.')
                return

        now = timezone.now()
        
        # Define retention periods
        retention_periods = {
            'expired_tokens': timedelta(days=7),   
            'login_attempts': timedelta(days=90),    
            'inactive_sessions': timedelta(days=30), 
            'email_logs': timedelta(days=180),       
            'blacklisted_tokens': timedelta(days=30), 
            'deleted_users': timedelta(days=30),  
        }

        cleanup_stats = {}

        try:
            with transaction.atomic():
                # 1. Clean up expired email verification tokens
                cutoff_date = now - retention_periods['expired_tokens']
                expired_verification_tokens = EmailVerificationToken.objects.filter(
                    expires_at__lt=cutoff_date
                )
                count = expired_verification_tokens.count()
                if not dry_run:
                    expired_verification_tokens.delete()
                cleanup_stats['expired_verification_tokens'] = count

                # 2. Clean up expired password reset tokens
                expired_reset_tokens = PasswordResetToken.objects.filter(
                    expires_at__lt=cutoff_date
                )
                count = expired_reset_tokens.count()
                if not dry_run:
                    expired_reset_tokens.delete()
                cleanup_stats['expired_reset_tokens'] = count

                # 3. Clean up old login attempts
                cutoff_date = now - retention_periods['login_attempts']
                old_login_attempts = LoginAttempt.objects.filter(
                    created_at__lt=cutoff_date
                )
                count = old_login_attempts.count()
                if not dry_run:
                    old_login_attempts.delete()
                cleanup_stats['old_login_attempts'] = count

                # 4. Clean up inactive user sessions
                cutoff_date = now - retention_periods['inactive_sessions']
                inactive_sessions = UserSession.objects.filter(
                    last_activity__lt=cutoff_date,
                    is_active=False
                )
                count = inactive_sessions.count()
                if not dry_run:
                    inactive_sessions.delete()
                cleanup_stats['inactive_sessions'] = count

                # 5. Clean up old email logs (keep recent ones for audit)
                cutoff_date = now - retention_periods['email_logs']
                old_email_logs = EmailLog.objects.filter(
                    sent_at__lt=cutoff_date
                )
                count = old_email_logs.count()
                if not dry_run:
                    old_email_logs.delete()
                cleanup_stats['old_email_logs'] = count

                # 6. Clean up old blacklisted refresh tokens
                cutoff_date = now - retention_periods['blacklisted_tokens']
                old_blacklisted_tokens = RefreshToken.objects.filter(
                    is_blacklisted=True,
                    created_at__lt=cutoff_date
                )
                count = old_blacklisted_tokens.count()
                if not dry_run:
                    old_blacklisted_tokens.delete()
                cleanup_stats['old_blacklisted_tokens'] = count

                # 7. Clean up expired refresh tokens
                expired_refresh_tokens = RefreshToken.objects.filter(
                    expires_at__lt=now
                )
                count = expired_refresh_tokens.count()
                if not dry_run:
                    expired_refresh_tokens.delete()
                cleanup_stats['expired_refresh_tokens'] = count

                # 8. Process scheduled account deletions
                users_to_delete = User.objects.filter(
                    is_deletion_pending=True,
                    deletion_scheduled_for__lt=now
                )
                count = users_to_delete.count()
                if not dry_run:
                    for user in users_to_delete:
                        self.stdout.write(f'Deleting user: {user.email}')
                        user.delete()
                cleanup_stats['deleted_users'] = count

                # 9. Clean up old user records that were soft-deleted
                cutoff_date = now - retention_periods['deleted_users']
                old_deleted_users = User.objects.filter(
                    is_active=False,
                    is_deletion_pending=False,
                    updated_at__lt=cutoff_date
                )
                count = old_deleted_users.count()
                if not dry_run:
                    old_deleted_users.delete()
                cleanup_stats['old_deleted_users'] = count

        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")
            self.stdout.write(
                self.style.ERROR(f'Error during cleanup: {str(e)}')
            )
            return

        # Display results
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No records were actually deleted'))
        else:
            self.stdout.write(self.style.SUCCESS('Cleanup completed successfully'))

        self.stdout.write('\nCleanup Summary:')
        for category, count in cleanup_stats.items():
            if count > 0:
                action = 'Would delete' if dry_run else 'Deleted'
                self.stdout.write(f'  {action} {count} {category}')

        total_cleaned = sum(cleanup_stats.values())
        action = 'Would clean' if dry_run else 'Cleaned'
        self.stdout.write(f'\nTotal: {action} {total_cleaned} records')

        # Log the cleanup operation
        if not dry_run:
            logger.info(f'Database cleanup completed. Cleaned {total_cleaned} records: {cleanup_stats}')