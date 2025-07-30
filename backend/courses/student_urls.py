# courses/student_urls.py
from django.urls import path
from . import student_views

urlpatterns = [
    # Course Discovery
    path('', student_views.list_courses, name='list_courses'),
    path('featured/', student_views.get_featured_courses, name='featured_courses'),
    path('categories/', student_views.get_course_categories, name='course_categories'),
    path('search/', student_views.search_courses, name='search_courses'),
    path('recommendations/', student_views.get_recommendations, name='course_recommendations'),
    path('<uuid:course_id>/', student_views.get_course_detail, name='course_detail'),
    
    # Course Enrollment & Payment
    path('<uuid:course_id>/enroll/', student_views.enroll_course, name='enroll_course'),
    path('verify-payment/', student_views.verify_payment, name='verify_payment'),
    
    # Payment Status
    path('payment-status/<str:reference>/', student_views.check_payment_status, name='check_payment_status'),
    
    # User Course Management
    path('my-courses/', student_views.my_courses, name='my_courses'),
    path('<uuid:course_id>/progress/', student_views.course_progress, name='course_progress'),

    # Course Content Structure
    path('<uuid:course_id>/content/', student_views.get_course_content, name='course_content'),
    
    # Student Lesson Access
    path('<uuid:course_id>/sections/<uuid:section_id>/lessons/<uuid:lesson_id>/', 
         student_views.lesson_detail, name='lesson_detail'),
    path('<uuid:course_id>/sections/<uuid:section_id>/lessons/<uuid:lesson_id>/progress/', 
         student_views.update_lesson_progress, name='update_lesson_progress'),
    
    # Student Bookmarks & Notes
    path('lessons/<uuid:lesson_id>/bookmarks/', student_views.manage_bookmarks, name='manage_bookmarks'),
    path('lessons/<uuid:lesson_id>/notes/', student_views.manage_notes, name='manage_notes'),
    
    # Student Progress Overview
    path('progress/', student_views.my_progress, name='my_progress'),
    
    # Course Reviews
    path('<uuid:course_id>/reviews/', student_views.course_reviews, name='course_reviews'),
    
    # Course Exams
    path('<uuid:course_id>/exams/', student_views.get_course_exams, name='course_exams'),
    
    # Exam Taking
    path('exams/<uuid:exam_id>/start/', student_views.start_exam, name='start_exam'),
    path('exam-attempts/<uuid:attempt_id>/questions/', student_views.get_exam_questions, name='exam_questions'),
    path('exam-attempts/<uuid:attempt_id>/submit-answer/', student_views.submit_exam_answer, name='submit_exam_answer'),
    path('exam-attempts/<uuid:attempt_id>/complete/', student_views.complete_exam, name='complete_exam'),
    path('exam-attempts/<uuid:attempt_id>/results/', student_views.get_exam_results, name='exam_results'),
    
    # User Dashboard
    path('dashboard/', student_views.user_dashboard, name='user_dashboard'),
]