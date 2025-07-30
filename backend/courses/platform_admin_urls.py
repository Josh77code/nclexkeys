# courses/platform_admin_urls.py
from django.urls import path
from . import platform_admin_views

urlpatterns = [
    # Platform Overview
    path('overview/', platform_admin_views.platform_overview, name='platform_overview'),
    
    # Instructor Management
    path('instructors/', platform_admin_views.manage_instructors, name='manage_instructors'),
    path('instructors/<uuid:instructor_id>/manage/', platform_admin_views.manage_instructor_status, name='manage_instructor_status'),
    path('instructors/<uuid:instructor_id>/course-impact/', platform_admin_views.instructor_course_impact_preview, name='instructor_course_impact_preview'),
    path('instructors/bulk-actions/', platform_admin_views.bulk_instructor_actions, name='bulk_instructor_actions'),

    # Course and Appeal Management
    path('appeals/pending/', platform_admin_views.get_pending_appeals, name='get_pending_appeals'),
    path('appeals/<uuid:appeal_id>/review/', platform_admin_views.review_course_appeal, name='review_course_appeal'),
    path('courses/bulk-status-update/', platform_admin_views.bulk_course_status_update, name='bulk_course_status_update'),
    
    # Course Moderation
    path('courses/pending/', platform_admin_views.pending_courses, name='pending_courses'),
    path('courses/', platform_admin_views.all_courses, name='all_courses'),
    path('courses/<uuid:course_id>/', platform_admin_views.course_detail_for_review, name='course_detail_review'),
    path('courses/<uuid:course_id>/moderate/', platform_admin_views.moderate_course, name='moderate_course'),
    path('courses/bulk-actions/', platform_admin_views.bulk_course_actions, name='bulk_course_actions'),
    path('courses/moderation-stats/', platform_admin_views.course_moderation_stats, name='course_moderation_stats'),

    # Complete course details (with all related data and statistics)
    path('courses/<uuid:course_id>/complete/', platform_admin_views.get_complete_course_details,name='admin-course-complete-details'),
    
    # Review Management
    path('reviews/', platform_admin_views.all_reviews, name='all_reviews'),
    path('reviews/pending/', platform_admin_views.pending_reviews, name='pending_reviews'),
    path('reviews/<uuid:review_id>/approve/', platform_admin_views.approve_review, name='approve_review'),
    
    # Analytics
    path('revenue-analytics/', platform_admin_views.revenue_analytics, name='revenue_analytics'),
]