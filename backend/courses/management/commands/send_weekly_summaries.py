# management/commands/send_weekly_summaries.py
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from courses.models import Course, CourseAppeal
from utils.auth import EmailService
from django.db import models

User = get_user_model()

class Command(BaseCommand):
    help = 'Send weekly summaries to super admins about pending suspended courses and appeals'
    
    def handle(self, *args, **options):
        try:
            # Get all super admins
            super_admins = User.objects.filter(role='super_admin', is_active=True)
            
            if not super_admins.exists():
                self.stdout.write('No active super admins found.')
                return
            
            # Get statistics
            one_week_ago = timezone.now() - timedelta(days=7)
            
            # Suspended courses statistics
            total_suspended_courses = Course.objects.filter(
                moderation_status='suspended',
                is_active=False
            ).count()
            
            recently_suspended = Course.objects.filter(
                moderation_status='suspended',
                moderated_at__gte=one_week_ago
            ).count()
            
            # Appeals statistics
            pending_appeals = CourseAppeal.objects.filter(status='pending').count()
            recent_appeals = CourseAppeal.objects.filter(
                created_at__gte=one_week_ago,
                status='pending'
            ).count()
            
            overdue_appeals = CourseAppeal.objects.filter(
                status='pending',
                created_at__lt=timezone.now() - timedelta(days=7)
            ).count()
            
            # Get top instructors with suspended courses
            suspended_course_instructors = Course.objects.filter(
                moderation_status='suspended'
            ).values(
                'created_by__full_name',
                'created_by__email'
            ).annotate(
                suspended_count=models.Count('id')
            ).order_by('-suspended_count')[:5]
            
            # Send weekly summary to each super admin
            for admin in super_admins:
                try:
                    EmailService.send_weekly_moderation_summary(
                        admin=admin,
                        stats={
                            'total_suspended_courses': total_suspended_courses,
                            'recently_suspended': recently_suspended,
                            'pending_appeals': pending_appeals,
                            'recent_appeals': recent_appeals,
                            'overdue_appeals': overdue_appeals,
                            'top_suspended_instructors': list(suspended_course_instructors)
                        }
                    )
                    self.stdout.write(f'Weekly summary sent to {admin.email}')
                except Exception as e:
                    self.stdout.write(f'Failed to send summary to {admin.email}: {str(e)}')
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Weekly summaries sent to {super_admins.count()} super admins'
                )
            )
            
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to send weekly summaries: {str(e)}')
            )