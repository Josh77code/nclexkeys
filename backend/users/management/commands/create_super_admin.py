# users/management/commands/create_super_admin.py
from django.core.management.base import BaseCommand
from django.core.management import CommandError
from users.models import User
import getpass

class Command(BaseCommand):
    help = 'Create a super admin user with highest privileges'

    def add_arguments(self, parser):
        parser.add_argument('--email', type=str, help='Super admin email')
        parser.add_argument('--name', type=str, help='Super admin full name')
        parser.add_argument('--password', type=str, help='Super admin password')

    def handle(self, *args, **options):
        email = options.get('email')
        full_name = options.get('name')
        password = options.get('password')

        # Interactive input if not provided
        if not email:
            email = input('Email: ')
        
        if not full_name:
            full_name = input('Full name: ')
        
        if not password:
            password = getpass.getpass('Password: ')
            password_confirm = getpass.getpass('Password (again): ')
            if password != password_confirm:
                raise CommandError('Passwords do not match')

        # Check if user already exists
        if User.objects.filter(email=email).exists():
            raise CommandError(f'User with email {email} already exists')

        # Create super admin
        try:
            superuser = User.objects.create_superuser(
                email=email,
                password=password,
                full_name=full_name
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Super admin created successfully!\n'
                    f'Email: {superuser.email}\n'
                    f'Role: {superuser.role}\n'
                    f'Staff: {superuser.is_staff}\n'
                    f'Superuser: {superuser.is_superuser}'
                )
            )
            
        except Exception as e:
            raise CommandError(f'Error creating super admin: {str(e)}')