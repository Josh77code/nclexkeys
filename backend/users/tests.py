from django.test import TestCase

# Create your tests here.
# Create a management command to test emails
# Create file: management/commands/test_email.py

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from backend.utils.auth import EmailService, EmailTokenManager

User = get_user_model()

class Command(BaseCommand):
    help = 'Test email system'

    def handle(self, *args, **options):
        # Test with an existing user or create a test user
        try:
            user = User.objects.get(email='test@example.com')
        except User.DoesNotExist:
            user = User.objects.create_user(
                email='test@example.com',
                password='testpass123',
                full_name='Test User'
            )
        
        # Test verification email
        token = EmailTokenManager.generate_verification_token(user)
        EmailService.send_verification_email(user, token)
        
        self.stdout.write(
            self.style.SUCCESS('Test email sent successfully!')
        )

# Run with: python manage.py test_email