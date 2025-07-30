# users/urls.py
from django.urls import path, include

app_name = 'users'

urlpatterns = [
    # User-facing auth URLs
    path('api/auth/', include('users.auth_urls')),
    
    # Admin auth management URLs
    path('api/', include('users.platform_admin_urls')),
]