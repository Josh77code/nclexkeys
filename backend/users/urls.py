# urls.py
from django.urls import path
from . import views

app_name = 'auth'

urlpatterns = [
    # Authentication endpoints
    path('auth/register/', views.register, name='register'),
    path('auth/login/', views.login, name='login'),
    path('auth/logout/', views.logout, name='logout'),
    path('auth/logout-all/', views.logout_all, name='logout_all'),
    path('auth/refresh/', views.refresh_token, name='refresh_token'),

    # Two-factor authentication
    path('auth/2fa/enable/', views.enable_2fa, name='enable_2fa'),
    path('auth/2fa/confirm/', views.confirm_2fa, name='confirm_2fa'),
    path('auth/2fa/disable/', views.disable_2fa, name='disable_2fa'),
    path('auth/2fa/backup-codes/', views.generate_backup_codes, name='generate_backup_codes'),
    path('auth/2fa/status/', views.get_2fa_status, name='get_2fa_status'),
    path('auth/2fa/regenerate-backup-codes/', views.regenerate_backup_codes, name='regenerate_backup_codes'),
    path('auth/2fa/emergency-disable/', views.emergency_disable_2fa, name='emergency_disable_2fa'),
    path('auth/2fa/admin/approve-emergency/', views.approve_emergency_2fa_disable, name='approve_emergency_2fa'),
    path('auth/2fa/admin/list-emergency/', views.list_emergency_2fa_requests, name='list_emergency_2fa'),

    # Password management
    path('auth/forgot-password/', views.forgot_password, name='forgot_password'),
    path('auth/reset-password/confirm/', views.reset_password_confirm, name='reset_password_confirm'),
    path('auth/change-password/', views.change_password, name='change_password'),
    
    # Email verification
    path('auth/verify-email/', views.verify_email, name='verify_email'),
    path('auth/resend-verification/', views.resend_verification, name='resend_verification'),
    
    # User profile
    path('users/me/', views.user_profile, name='user_profile'),
    path('users/me/update/', views.update_profile, name='update_profile'),
    path('auth/sessions/', views.user_sessions, name='user_sessions'),

    # Account Deletion
    path('delete-account/', views.delete_account, name='delete_account'),
    path('cancel-deletion/', views.cancel_deletion, name='cancel_deletion'),
    path('delete-account-immediate/', views.delete_account_immediate, name='delete_account_immediate'),
]