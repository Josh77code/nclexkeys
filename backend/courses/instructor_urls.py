# courses/instructor_urls.py
from django.urls import path
from . import instructor_views

urlpatterns = [
    
    # Course Management
    path('courses/', instructor_views.list_all_courses, name='admin_list_courses'),
    path('courses/create/', instructor_views.create_course, name='admin_create_course'),
    path('courses/<uuid:course_id>/', instructor_views.get_course_details, name='admin_course_details'),
    path('courses/<uuid:course_id>/update/', instructor_views.update_course, name='admin_update_course'),
    path('courses/<uuid:course_id>/delete/', instructor_views.delete_course, name='admin_delete_course'),
    path('courses/<uuid:course_id>/pricing/', instructor_views.update_course_pricing, name='admin_update_course_pricing'),
    path('courses/revenue-report/', instructor_views.course_revenue_report, name='admin_course_revenue_report'),

    # Course Sections Management
    path('courses/<uuid:course_id>/sections/', instructor_views.course_sections, name='admin_course_sections'),
    path('courses/<uuid:course_id>/sections/<uuid:section_id>/', instructor_views.section_detail, name='admin_section_detail'),
    path('courses/<uuid:course_id>/sections/<uuid:section_id>/reorder/', instructor_views.reorder_sections, name='admin_reorder_sections'),
    
    # Course Lessons Management  
    path('courses/<uuid:course_id>/sections/<uuid:section_id>/lessons/', instructor_views.section_lessons, name='admin_section_lessons'),
    path('courses/<uuid:course_id>/sections/<uuid:section_id>/lessons/<uuid:lesson_id>/', instructor_views.lesson_detail, name='admin_lesson_detail'),
    path('courses/<uuid:course_id>/sections/<uuid:section_id>/lessons/bulk-actions/', instructor_views.bulk_lesson_actions, name='admin_bulk_lesson_actions'),
    path('courses/<uuid:course_id>/sections/<uuid:section_id>/lessons/<uuid:lesson_id>/analytics/', instructor_views.lesson_progress_analytics, name='admin_lesson_analytics'),
    
    # Video Management
    path('videos/upload/', instructor_views.upload_video, name='admin_upload_video'),
    path('lessons/upload-video/', instructor_views.upload_lesson_video, name='admin_upload_lesson_video'),

    # Course Analytics & Stats
    path('courses/statistics/', instructor_views.course_statistics, name='admin_course_statistics'),
    path('courses/<uuid:course_id>/enrollments/', instructor_views.course_enrollments, name='admin_course_enrollments'),
    path('users/<uuid:user_id>/courses/<uuid:course_id>/progress/', instructor_views.user_course_progress_detail, name='admin_user_course_progress'),
    
    # Bulk Operations
    path('courses/bulk-actions/', instructor_views.bulk_course_actions, name='admin_bulk_course_actions'),

    # Suspended Course Appeals
    path('courses/suspended/', instructor_views.get_suspended_courses, name='admin_get_suspended_courses'),
    path('courses/<uuid:course_id>/appeal/', instructor_views.submit_course_appeal, name='admin_submit_course_appeal'),
    path('appeals/', instructor_views.get_my_appeals, name='admin_get_my_appeals'),
    
    # Enrollment Management
    path('users/<uuid:user_id>/courses/<uuid:course_id>/progress/', instructor_views.user_course_progress_detail, name='admin_user_progress'),
    
    # Category Management
    path('course-categories/', instructor_views.course_categories, name='admin_course_categories'),
    path('course-categories/create/', instructor_views.create_category, name='admin_create_category'),
    path('course-categories/<uuid:category_id>/update/', instructor_views.update_category, name='admin_update_category'),
    path('course-categories/<uuid:category_id>/delete/', instructor_views.delete_category, name='admin_delete_category'),

    # Payment & Enrollment
    path('enrollments/manual/', instructor_views.process_manual_enrollment, name='admin_manual_enrollment'),
    path('payments/analytics/', instructor_views.payment_analytics, name='admin_payment_analytics'),
    
    # Exam Management
    path('courses/<uuid:course_id>/exams/', instructor_views.list_course_exams, name='admin_list_course_exams'),
    path('courses/<uuid:course_id>/exams/create/', instructor_views.create_course_exam, name='admin_create_course_exam'),
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/', instructor_views.get_exam_details, name='admin_exam_details'),
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/update/', instructor_views.update_exam, name='admin_update_exam'),
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/delete/', instructor_views.delete_exam, name='admin_delete_exam'),
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/attempts/', instructor_views.exam_attempts, name='admin_exam_attempts'),
    
    # Exam Question Management
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/questions/', instructor_views.exam_questions, name='admin_exam_questions'),
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/questions/<uuid:question_id>/', instructor_views.exam_question_detail, name='admin_exam_question_detail'),
    
    # Exam Statistics
    path('exams/statistics/', instructor_views.exam_statistics, name='admin_exam_statistics'),

    # Exam Question Analytics
    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/questions/analytics/', 
    instructor_views.exam_question_analytics, name='admin_exam-question-analytics'),

    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/questions/<uuid:question_id>/analytics/',instructor_views.question_detail_analytics, name='admin_question-detail-analytics'),

    path('courses/<uuid:course_id>/exams/<uuid:exam_id>/performance-trends/', 
    instructor_views.exam_performance_trends, name='admin_exam-performance-trends'),
    
    # Course structure only (sections, lessons, exams - no statistics)
    path('courses/<uuid:course_id>/structure/', instructor_views.get_course_structure_only,name='admin-course-structure'),  
]