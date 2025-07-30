# users/auth_urls.py
from django.urls import path
from . import auth_views

urlpatterns = [
    # Authentication endpoints
    path('register/', auth_views.register, name='register'),
    path('login/', auth_views.login, name='login'),
    path('logout/', auth_views.logout, name='logout'),
    path('logout-all/', auth_views.logout_all, name='logout_all'),
    path('refresh/', auth_views.refresh_token, name='refresh_token'),

    # Two-factor authentication
    path('2fa/enable/', auth_views.enable_2fa, name='enable_2fa'),
    path('2fa/confirm/', auth_views.confirm_2fa, name='confirm_2fa'),
    path('2fa/disable/', auth_views.disable_2fa, name='disable_2fa'),
    path('2fa/backup-codes/', auth_views.generate_backup_codes, name='generate_backup_codes'),
    path('2fa/status/', auth_views.get_2fa_status, name='get_2fa_status'),
    path('2fa/regenerate-backup-codes/', auth_views.regenerate_backup_codes, name='regenerate_backup_codes'),
    path('2fa/emergency-disable/', auth_views.emergency_disable_2fa, name='emergency_disable_2fa'),

    # Password management
    path('forgot-password/', auth_views.forgot_password, name='forgot_password'),
    path('reset-password/confirm/', auth_views.reset_password_confirm, name='reset_password_confirm'),
    path('change-password/', auth_views.change_password, name='change_password'),
    
    # Email verification
    path('verify-email/', auth_views.verify_email, name='verify_email'),
    path('resend-verification/', auth_views.resend_verification, name='resend_verification'),
    
    # User profile
    path('users/me/', auth_views.user_profile, name='user_profile'),
    path('users/me/update/', auth_views.update_profile, name='update_profile'),
    path('sessions/', auth_views.user_sessions, name='user_sessions'),

    # Account Deletion
    path('delete-account/', auth_views.delete_account, name='delete_account'),
    path('cancel-deletion/', auth_views.cancel_deletion, name='cancel_deletion'),
    path('delete-account-immediate/', auth_views.delete_account_immediate, name='delete_account_immediate'),
]