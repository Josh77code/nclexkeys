# courses/urls.py
from django.urls import path, include

app_name = 'courses'

urlpatterns = [
    # User-facing course URLs
    path('api/courses/', include('courses.student_urls')),
    
    # Admin course management URLs
    path('api/admin/', include('courses.instructor_urls')),

    # Super Admin URLs for platform management and revenue sharing
    path('api/super-admin/', include('courses.platform_admin_urls')),
]