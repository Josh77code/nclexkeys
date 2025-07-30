# course_middleware.py - Add payment security
from django.http import JsonResponse
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class PaymentSecurityMiddleware:
    """Middleware to prevent payment abuse"""
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Check for payment spam
        if request.path.startswith('/api/courses/') and request.method == 'POST':
            if 'enroll' in request.path and request.user.is_authenticated:
                # Limit enrollment attempts per user per hour
                recent_payments = getattr(request.user, '_recent_payments', 0)
                if recent_payments > 5:  # Max 5 payment attempts per hour
                    return JsonResponse({
                        'detail': 'Too many payment attempts. Please try again later.'
                    }, status=429)
        
        response = self.get_response(request)
        return response