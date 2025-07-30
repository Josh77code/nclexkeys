# payments/payout_urls.py
from django.urls import path, include
from . import payout_views

urlpatterns = [
    path('earning-summary/', payout_views.instructor_earnings, name='earning-summary'),
]