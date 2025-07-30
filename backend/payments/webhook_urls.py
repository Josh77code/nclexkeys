# payments/webhook_urls.py
from django.urls import path
from . import webhook_views
from . import webhook_debug_views

urlpatterns = [
    path('paystack/', webhook_views.paystack_webhook, name='paystack_webhook'),
    path('flutterwave/', webhook_views.flutterwave_webhook, name='flutterwave_webhook'),
    path('test/', webhook_debug_views.webhook_test_endpoint, name='webhook_test'),
    path('status/', webhook_debug_views.webhook_status, name='webhook_status'),
    path('simulate/', webhook_debug_views.simulate_webhook, name='simulate_webhook'),
]