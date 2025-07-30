# common/debug_middleware.py
from django.utils.deprecation import MiddlewareMixin
import traceback

class DebugUserMiddleware(MiddlewareMixin):
    """
    Enhanced middleware to debug which middleware is resetting request.user
    """
    
    def process_request(self, request):
        print(f"\n=== DEBUG MIDDLEWARE - PROCESS_REQUEST ===")
        print(f"User: {request.user}")
        print(f"User type: {type(request.user)}")
        print(f"Is authenticated: {getattr(request.user, 'is_authenticated', 'N/A')}")
        print(f"Has backend: {hasattr(request.user, 'backend')}")
        return None
    
    def process_response(self, request, response):
        print(f"\n=== DEBUG MIDDLEWARE - PROCESS_RESPONSE ===")
        print(f"User: {request.user}")
        print(f"User type: {type(request.user)}")
        print(f"Is authenticated: {getattr(request.user, 'is_authenticated', 'N/A')}")
        print(f"Response status: {response.status_code}")
        
        # If user changed to anonymous, show stack trace to find where
        if hasattr(request, '_original_user') and str(request.user) != str(request._original_user):
            print("🚨 USER WAS CHANGED! Stack trace:")
            traceback.print_stack()
        
        return response

class UserTrackingMiddleware(MiddlewareMixin):
    """
    Place this RIGHT after JWTAuthenticationMiddleware to track user changes
    """
    
    def process_request(self, request):
        # Store the original user for comparison
        request._original_user = getattr(request, 'user', None)
        print(f"\n🔍 USER TRACKING: Set original user to {request._original_user}")
        return None