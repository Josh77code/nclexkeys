# users/platform_admin_urls.py
from django.urls import path
from . import platform_admin_views

urlpatterns = [
    # Two-factor authentication
    path('2fa/super_admin/approve-emergency/', platform_admin_views.approve_emergency_2fa_disable, name='approve_emergency_2fa'),
    path('2fa/super_admin/list-emergency/', platform_admin_views.list_emergency_2fa_requests, name='list_emergency_2fa'),
]