# /users/platform_admin_views.py
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from .models import User
from django.core.cache import cache
from utils.auth import (
    JWTTokenManager, EmailService, SecurityMonitor
)
import logging

logger = logging.getLogger(__name__)

# Create your views here.
@api_view(['POST'])
@permission_classes([IsAuthenticated])  # Admin only
def approve_emergency_2fa_disable(request):
    """Admin approves or rejects emergency 2FA disable"""
    if request.user.role != 'admin':
        return Response({'detail': 'Admin access required.'}, status=403)
    
    emergency_token = request.data.get('emergency_token')
    approve = request.data.get('approve', False)
    reason = request.data.get('reason', '')  # Optional reason for rejection
    
    if not emergency_token:
        return Response({'detail': 'Emergency token required.'}, status=400)
    
    # Get emergency request
    emergency_data = cache.get(f"emergency_2fa_disable_{emergency_token}")
    if not emergency_data:
        return Response({'detail': 'Emergency request not found or expired.'}, status=400)
    
    try:
        user = User.objects.get(id=emergency_data['user_id'])
    except User.DoesNotExist:
        return Response({'detail': 'User not found.'}, status=400)
    
    if approve:
        # Disable 2FA
        user.two_factor_enabled = False
        user.two_factor_secret = None
        user.backup_codes = []
        user.save()
        
        # Send confirmation email
        EmailService.send_2fa_emergency_disabled_email(user)
        
        # Log security event
        SecurityMonitor.log_security_event(
            event_type='EMERGENCY_2FA_DISABLED',
            user=user,
            details=f'2FA emergency disabled by admin {request.user.email}',
            severity='CRITICAL'
        )
        
        message = f'2FA emergency disabled for {user.email}'
        
        # Blacklist all user tokens for security
        JWTTokenManager.blacklist_all_user_tokens(user)
        
    else:
        # Send rejection email
        EmailService.send_2fa_emergency_rejected_email(user)
        
        # Log security event
        SecurityMonitor.log_security_event(
            event_type='EMERGENCY_2FA_DISABLE_REJECTED',
            user=user,
            details=f'2FA emergency disable rejected by admin {request.user.email}. Reason: {reason}',
            severity='INFO'
        )
        
        message = f'2FA emergency disable rejected for {user.email}'
    
    # Clean up cache
    cache.delete(f"emergency_2fa_disable_{emergency_token}")
    cache.delete(f"emergency_2fa_disable_{user.id}")
    
    return Response({
        'message': message,
        'approved': approve,
        'user_email': user.email,
        'processed_by': request.user.email,
        'processed_at': timezone.now().isoformat()
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])  # Admin only
def list_emergency_2fa_requests(request):
    """Admin can list all pending emergency 2FA disable requests"""
    if request.user.role != 'admin':
        return Response({'detail': 'Admin access required.'}, status=403)
    
    # Get all emergency requests from cache
    # This is a simplified approach - in production, consider using database
    cache_keys = cache.keys('emergency_2fa_disable_*')
    requests = []
    
    for key in cache_keys:
        if key.startswith('emergency_2fa_disable_') and not key.endswith('_user_id'):
            try:
                data = cache.get(key)
                if data and isinstance(data, dict):
                    token = key.replace('emergency_2fa_disable_', '')
                    requests.append({
                        'token': token,
                        'user_email': data.get('email'),
                        'requested_at': data.get('requested_at'),
                        'ip_address': data.get('ip_address'),
                        'expires_at': data.get('expires_at')
                    })
            except Exception:
                continue
    
    return Response({
        'pending_requests': requests,
        'total_count': len(requests)
    })