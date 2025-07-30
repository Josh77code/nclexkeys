# payments/payment_urls.py
from django.urls import path
from . import payment_views

urlpatterns = [
    # Student payment operations
    path('transactions/', payment_views.payment_history, name='payment_history'),
    path('transactions/<uuid:payment_id>/', payment_views.payment_detail, name='payment_detail'),
    
    # Platform manager payment operations
    path('admin/overview/', payment_views.admin_payment_overview, name='admin_payment_overview'),
]