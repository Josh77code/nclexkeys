# common/middleware.py
from django.contrib.auth.models import AnonymousUser
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from users.models import User, UserSession
from utils.auth import JWTTokenManager, SecurityUtils, SecurityMonitor
from django.utils import timezone
import logging
from django.core.cache import cache
import json

logger = logging.getLogger(__name__)

class JWTAuthenticationMiddleware(MiddlewareMixin):
    """
    JWT Authentication Middleware
    Processes JWT tokens and sets request.user
    Must run AFTER Django's AuthenticationMiddleware
    """
    
    def process_request(self, request):
        # Skip JWT authentication for admin URLs and static files
        if request.path.startswith('/admin/') or request.path.startswith('/static/'):
            return None
        
        # Get token from Authorization header
        auth_header = request.META.get('HTTP_AUTHORIZATION')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            # No token provided - set anonymous user
            request.user = AnonymousUser()
            return None
        
        # Extract token
        token = auth_header.split(' ')[1]
        
        try:
            # Verify token using JWTTokenManager
            payload, error_info = JWTTokenManager.verify_access_token(token)
            
            if error_info:
                # Token verification failed - return specific error
                return JsonResponse({
                    'detail': error_info['message'],
                    'error_code': error_info['error_code']
                }, status=401)
            
            # Token is valid - get user from database
            user = User.objects.get(id=payload['user_id'])
            
            # Check if user is active
            if not user.is_active:
                return JsonResponse({
                    'detail': 'Your account has been deactivated. Contact support.',
                    'error_code': 'ACCOUNT_INACTIVE'
                }, status=401)
            
            # Check if account is locked (if method exists)
            if hasattr(user, 'is_account_locked') and user.is_account_locked():
                return JsonResponse({
                    'detail': 'Your account is locked due to security reasons.',
                    'error_code': 'ACCOUNT_LOCKED'
                }, status=401)
            
            # Set authenticated user
            request.user = user
            request.user.backend = 'django.contrib.auth.backends.ModelBackend'
            
            logger.info(f"User authenticated: {user.email} with role: {user.role}")
            return None
            
        except User.DoesNotExist:
            return JsonResponse({
                'detail': 'User account not found. Please login again.',
                'error_code': 'USER_NOT_FOUND'
            }, status=401)
            
        except Exception as e:
            logger.error(f"JWT authentication error: {str(e)}")
            return JsonResponse({
                'detail': 'Authentication failed. Please try again.',
                'error_code': 'AUTH_ERROR'
            }, status=401)


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to responses
    """
    
    def process_response(self, request, response):
        # Add security headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Content-Security-Policy'] = "default-src 'self'"
        
        # Add HSTS header for HTTPS
        if request.is_secure():
            response['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains; preload'
        
        return response


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Log API requests for security monitoring
    """
    
    def process_request(self, request):
        # Log authentication attempts
        auth_paths = [
            '/api/auth/login/', 
            '/api/auth/register/', 
            '/api/auth/forgot-password/',
            '/api/auth/reset-password/confirm/',
            '/api/auth/verify-email/',
            '/api/auth/refresh/'
        ]
        
        if request.path in auth_paths:
            ip_address = SecurityUtils.get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')
            
            logger.info(f"Auth request: {request.method} {request.path} from {ip_address} - {user_agent}")
        
        return None
    
    
class SessionValidationMiddleware(MiddlewareMixin):
    """
    Validate active sessions and update activity
    """
    
    def process_request(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            session_token = request.META.get('HTTP_X_SESSION_TOKEN')
            
            # If no session token provided, skip session validation for JWT-only auth
            if not session_token:
                return None
                
            try:
                session = UserSession.objects.get(
                    user=request.user,
                    session_token=session_token,
                    is_active=True
                )
                
                # Check if session is expired (24 hours of inactivity)
                if session.last_activity and (timezone.now() - session.last_activity).total_seconds() > 86400:
                    session.is_active = False
                    session.save()
                    request.user = AnonymousUser()
                    return None
                
                # Update last activity
                session.last_activity = timezone.now()
                session.save(update_fields=['last_activity'])
                
            except UserSession.DoesNotExist:
                # For JWT-only authentication, don't reset user if no session token provided
                # Only reset if session token was explicitly provided but is invalid
                pass  # Don't reset user - let JWT authentication work
        
        return None
    

class RateLimitMiddleware(MiddlewareMixin):
    """
    Enhanced Redis-based rate limiting middleware
    """
    
    def process_request(self, request):
        # Define rate limits for different endpoints
        rate_limits = {
            '/api/auth/login/': {'limit': 3, 'window': 900, 'message': 'Too many login attempts'},
            '/api/auth/register/': {'limit': 3, 'window': 3600, 'message': 'Too many registration attempts'},
            '/api/auth/forgot-password/': {'limit': 3, 'window': 3600, 'message': 'Too many password reset requests'},
            '/api/auth/reset-password/confirm/': {'limit': 3, 'window': 3600, 'message': 'Too many password reset attempts'},
            '/api/auth/verify-email/': {'limit': 3, 'window': 3600, 'message': 'Too many email verification attempts'},
            '/api/auth/refresh/': {'limit': 10, 'window': 300, 'message': 'Too many token refresh attempts'},
            '/api/auth/resend-verification/': {'limit': 3, 'window': 3600, 'message': 'Too many verification email requests'},
            '/api/auth/2fa/emergency-disable/': {'limit': 3, 'window': 3600, 'message': 'Too many emergency 2FA disable requests'},
            '/api/auth/change-password/': {'limit': 3, 'window': 3600, 'message': 'Too many password change attempts'},
            '/api/auth/account-status/': {'limit': 30, 'window': 300, 'message': 'Too many account status checks'},
            '/api/auth/2fa/admin/approve-emergency/': {'limit': 10, 'window': 300, 'message': 'Too many admin 2FA approvals'},
        }
        
        if request.path in rate_limits:
            # Get email from request first
            email = self._get_email_from_request(request)

            # Check if account is locked before rate limiting
            if email:
                try:
                    user = User.objects.get(email=email)
                    if user.is_account_locked():
                        # Skip rate limiting - let it go to login view to show proper "account locked" message
                        return None
                except User.DoesNotExist:
                    pass
                
            # Now do normal rate limiting
            ip_address = SecurityUtils.get_client_ip(request)
            config = rate_limits[request.path]
            
            # Create cache keys for IP and email (if in request)
            ip_cache_key = f"rate_limit_{request.path}_{ip_address}"
            
            # Check IP-based limit
            ip_count = cache.get(ip_cache_key, 0)
            
            if ip_count >= config['limit']:
                # Calculate remaining time
                ttl = cache.ttl(ip_cache_key)
                if ttl is None:
                    ttl = config['window']
                
                return JsonResponse({
                    'detail': config['message'],
                    'retry_after': ttl,
                    'retry_after_human': self._format_time(ttl)
                }, status=429)
            
            # Email-based rate limiting for relevant endpoints
            if request.path in ['/api/auth/login/', '/api/auth/forgot-password/', '/api/auth/register/']:
                email = self._get_email_from_request(request)
                if email:
                    email_cache_key = f"rate_limit_{request.path}_email_{email}"
                    email_count = cache.get(email_cache_key, 0)
                    
                    if email_count >= config['limit']:
                        ttl = cache.ttl(email_cache_key)
                        if ttl is None:
                            ttl = config['window']
                        
                        return JsonResponse({
                            'detail': config['message'],
                            'retry_after': ttl,
                            'retry_after_human': self._format_time(ttl)
                        }, status=429)
                    
                    # Increment email counter
                    cache.set(email_cache_key, email_count + 1, config['window'])
            
            # Increment IP counter
            cache.set(ip_cache_key, ip_count + 1, config['window'])
        
        return None
    
    def _get_email_from_request(self, request):
        """Extract email from request body"""
        try:
            if request.content_type == 'application/json':
                body = json.loads(request.body.decode('utf-8'))
                return body.get('email')
        except:
            pass
        return None
    
    def _format_time(self, seconds):
        """Format seconds to human readable time"""
        if seconds < 60:
            return f"{int(seconds)} second{'s' if seconds != 1 else ''}"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        else:
            hours = int(seconds // 3600)
            return f"{hours} hour{'s' if hours != 1 else ''}"


class UserActivityMiddleware(MiddlewareMixin):
    """
    Track user activity and update last seen
    """
    
    def process_request(self, request):
        if hasattr(request, 'user') and request.user.is_authenticated:
            # Update user's last activity
            request.user.last_activity = timezone.now()
            request.user.save(update_fields=['last_activity'])
            
            # Cache user activity for real-time features
            cache.set(f"user_activity_{request.user.id}", timezone.now(), 300)  # 5 minutes
        
        return None


class SuspiciousActivityMiddleware(MiddlewareMixin):
    """
    Detect and log suspicious activity
    """
    
    def process_request(self, request):
        ip_address = SecurityUtils.get_client_ip(request)
        
        # Check for rapid requests from same IP (separate from rate limiting)
        cache_key = f"request_count_{ip_address}"
        request_count = cache.get(cache_key, 0)
        
        if request_count > 100:  # More than 100 requests per minute
            logger.warning(f"Suspicious activity detected: {request_count} requests from {ip_address}")

            SecurityMonitor.log_security_event(
                'SUSPICIOUS_ACTIVITY',
                request.user if hasattr(request, 'user') and request.user.is_authenticated else None,
                f"Excessive requests from IP: {ip_address}",
                'CRITICAL'
            )
            
            # Optional: Block or throttle
            return JsonResponse({
                'detail': 'Too many requests detected. Please slow down.',
            }, status=429)
        
        cache.set(cache_key, request_count + 1, 60)  # 1 minute window
        
        return None


class ErrorHandlingMiddleware(MiddlewareMixin):
    """
    Handle authentication errors gracefully
    """
    
    def process_exception(self, request, exception):
        # Log authentication related errors
        auth_paths = ['/api/auth/', '/api/users/']
        
        if any(path in request.path for path in auth_paths):
            logger.error(f"Authentication error on {request.path}: {str(exception)}")
        
        return None
    
    def process_response(self, request, response):
        # Log failed authentication attempts
        if response.status_code == 401 and '/api/auth/' in request.path:
            ip_address = SecurityUtils.get_client_ip(request)
            logger.warning(f"Authentication failed from {ip_address} on {request.path}")
        
        return response