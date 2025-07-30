# common/authentication.py
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth.models import AnonymousUser
from users.models import User
from utils.auth import JWTTokenManager
import logging

logger = logging.getLogger(__name__)

class JWTAuthentication(BaseAuthentication):
    """
    JWT Authentication for Django REST Framework
    This replaces your middleware approach
    """
    
    def authenticate(self, request):
        """
        Authenticate the request and return a (user, token) tuple or None
        """
        # Skip JWT authentication for admin URLs and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return None
        
        # Get token from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            # No token provided - return None (anonymous)
            return None
        
        # Extract token
        token = auth_header.split(' ')[1]
        
        try:
            # Verify token using JWTTokenManager
            payload, error_info = JWTTokenManager.verify_access_token(token)
            
            if error_info:
                # Token verification failed
                raise AuthenticationFailed(error_info['message'])
            
            # Token is valid - get user from database
            try:
                user = User.objects.get(id=payload['user_id'])
            except User.DoesNotExist:
                raise AuthenticationFailed('User account not found. Please login again.')
            
            # Check if user is active
            if not user.is_active:
                raise AuthenticationFailed('Your account has been deactivated. Contact support.')
            
            # Check if account is locked (if method exists)
            if hasattr(user, 'is_account_locked') and user.is_account_locked():
                raise AuthenticationFailed('Your account is locked due to security reasons.')
            
            logger.info(f"User authenticated via JWT: {user.email} with role: {user.role}")
            
            # Return (user, token) tuple
            return (user, token)
            
        except Exception as e:
            logger.error(f"JWT authentication error: {str(e)}")
            raise AuthenticationFailed('Authentication failed. Please try again.')
    
    def authenticate_header(self, request):
        """
        Return the header for 401 responses
        """
        return 'Bearer'