# payments/refund_urls.py
from django.urls import path
from . import refund_views

urlpatterns = [
    # Student refund operations
    path('<uuid:payment_id>/refund/', refund_views.request_refund, name='request_refund'),
    path('my-refunds/', refund_views.my_refunds, name='my_refunds'),
    
    # Platform manager refund operations
    path('admin/refunds/pending/', refund_views.pending_refunds, name='pending_refunds'),
    path('admin/refunds/<uuid:refund_id>/process/', refund_views.process_refund, name='process_refund'),
]