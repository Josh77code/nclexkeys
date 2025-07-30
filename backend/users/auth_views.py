# /users/auth_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.core.cache import cache
from .models import User, PasswordResetToken, RefreshToken
from .serializers import (
    UserRegistrationSerializer, UserLoginSerializer, ForgotPasswordSerializer,
    PasswordResetConfirmSerializer, EmailVerificationSerializer, ResendVerificationSerializer,
    UserProfileSerializer, UserProfileUpdateSerializer, RefreshTokenSerializer,
    ChangePasswordSerializer, CancelDeletionSerializer, DeleteAccountSerializer
)
from utils.auth import (
    JWTTokenManager, EmailTokenManager, SecurityUtils, EmailService, TwoFactorManager, SecurityMonitor
)
import logging, secrets, hashlib


logger = logging.getLogger(__name__)


# Create your views here.
@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    """
    User Registration
    POST /api/auth/register/
    """
    serializer = UserRegistrationSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    ip_address = SecurityUtils.get_client_ip(request)
    email = serializer.validated_data['email']

    
    try:
        with transaction.atomic():
            # Create user
            user = serializer.save()
            
            # Generate verification token
            verification_token = EmailTokenManager.generate_verification_token(user)
            
            # Send verification email
            EmailService.send_verification_email(user, verification_token)
            
            # Log registration attempt
            SecurityUtils.log_login_attempt(
                user=user,
                email=email,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                success=True,
                failure_reason=None
            )
            
            return Response({
                'message': 'Registration successful. Please check your email to confirm your account.',
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'full_name': user.full_name,
                    'phone_number': user.phone_number,
                    'role': user.role
                }
            }, status=status.HTTP_201_CREATED)
    
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        return Response(
            {'detail': 'Registration failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def login(request):
    """
    User Login
    POST /api/auth/login/
    """
    serializer = UserLoginSerializer(data=request.data)
    
    if not serializer.is_valid():
        # Log failed attempt
        ip_address = SecurityUtils.get_client_ip(request)
        email = request.data.get('email', '')

        try:
            user = User.objects.get(email=email)
            user.increment_failed_attempts()
        except User.DoesNotExist:
            pass
        
        SecurityUtils.log_login_attempt(
            user=None,
            email=email,
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            success=False,
            failure_reason='Invalid input data'
        )
        
        return Response(
            {'detail': 'Invalid credentials.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    ip_address = SecurityUtils.get_client_ip(request)
    email = serializer.validated_data['email']
    
    try:
        user = serializer.validated_data['user']
        deletion_warning = serializer.validated_data.get('deletion_warning')
        
        # Check if email is verified
        if not user.is_email_verified:
            # Generate and send new verification token
            verification_token = EmailTokenManager.generate_verification_token(user)
            EmailService.send_verification_email(user, verification_token)
            
            return Response(
                {'detail': 'Please verify your email address before logging in. A new verification email has been sent.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if user.two_factor_enabled:
            token_2fa = request.data.get('two_factor_token')
            backup_code = request.data.get('backup_code')

            if not token_2fa and not backup_code:
                return Response({
                    'detail': '2FA token or backup code required.',
                    'requires_2fa': True
                }, status=400)

            # Try backup code first
            if backup_code:
                if not TwoFactorManager.verify_backup_code(user, backup_code):
                    return Response({'detail': 'Invalid backup code.'}, status=400)
            # Then try TOTP token
            elif token_2fa:
                if not TwoFactorManager.verify_token(user.two_factor_secret, token_2fa):
                    return Response({'detail': 'Invalid 2FA token.'}, status=400)
            else:
                return Response({'detail': 'Invalid 2FA credentials.'}, status=400)
        
        with transaction.atomic():
            # Generate tokens
            access_token = JWTTokenManager.generate_access_token(user)
            refresh_token = JWTTokenManager.generate_refresh_token(user, request)
            
            # Check if this is a new device
            device_fingerprint = SecurityUtils.generate_device_fingerprint(request)
            is_new_device = SecurityUtils.is_new_device(user, device_fingerprint)
            
            # Create user session
            session = SecurityUtils.create_user_session(user, request, is_new_device)
            
            # Update user's last login
            user.last_login = timezone.now()
            user.reset_failed_attempts()  # Reset failed attempts on successful login
            user.save(update_fields=['last_login', 'failed_login_attempts'])
            
            # Log successful login
            SecurityUtils.log_login_attempt(
                user=user,
                email=email,
                ip_address=ip_address,
                user_agent=request.META.get('HTTP_USER_AGENT', ''),
                success=True
            )
            
            # Send email alerts
            if is_new_device:
                EmailService.send_new_device_email(user, session)
            else:
                EmailService.send_login_alert_email(user, session)
            
            response_data = {
                'message': 'Login successful.',
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': {
                    'id': str(user.id),
                    'email': user.email,
                    'full_name': user.full_name,
                    'phone_number': user.phone_number,
                    'role': user.role,
                    'is_deletion_pending': user.is_deletion_pending,
                    'deletion_scheduled_for': user.deletion_scheduled_for.isoformat() if user.deletion_scheduled_for else None
                }
            }

        # Add deletion warning if present
        if deletion_warning:
            response_data['warning'] = deletion_warning
            
        return Response(response_data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        
        # Log failed attempt
        SecurityUtils.log_login_attempt(
            user=None,
            email=email,
            ip_address=ip_address,
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            success=False,
            failure_reason=str(e)
        )
        
        return Response(
            {'detail': 'Login failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def forgot_password(request):
    """
    Request Password Reset
    POST /api/auth/forgot-password/
    """
    serializer = ForgotPasswordSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    email = serializer.validated_data['email']
    ip_address = SecurityUtils.get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    SecurityUtils.log_login_attempt(
        user=None,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False,
        failure_reason='Password reset request'
    )

    response_message = 'Password reset link sent to your email.'

    try:
        user = User.objects.get(email=email)
        if user.is_active:
            # Generate reset token
            reset_token = EmailTokenManager.generate_password_reset_token(user)
            # Send reset email
            EmailService.send_password_reset_email(user, reset_token)

            # Log attempt
            SecurityUtils.log_login_attempt(
                user=user,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
                success=True
            )

    except User.DoesNotExist:
        # Log unknown email attempt
        SecurityUtils.log_login_attempt(
            user=None,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True
        )

    return Response({'message': response_message}, status=status.HTTP_200_OK)



@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password_confirm(request):
    """
    Confirm Password Reset
    POST /api/auth/reset-password/confirm/
    """
    serializer = PasswordResetConfirmSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if account is locked
    if 'Account is temporarily locked' in str(serializer.errors):
        return Response(
            {'detail': 'Account is temporarily locked. Please try again later.'},
            status=status.HTTP_423_LOCKED
        )
    
    try:
        with transaction.atomic():
            reset_token = serializer.validated_data['reset_token']
            new_password = serializer.validated_data['new_password']
            
            # Update user password
            user = reset_token.user
            user.set_password(new_password)
            user.password_changed_at = timezone.now()
            user.save(update_fields=['password', 'password_changed_at'])
            
            # Mark token as used
            reset_token.is_used = True
            reset_token.save()
            
            # Blacklist all refresh tokens (force re-login)
            JWTTokenManager.blacklist_all_user_tokens(user)
            
            # Send password changed email
            EmailService.send_password_changed_email(user)
            
            return Response(
                {'message': 'Your password has been updated successfully.'},
                status=status.HTTP_200_OK
            )
    
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return Response(
            {'detail': 'Password reset failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_email(request):
    """
    Verify Email Address
    POST /api/auth/verify-email/
    """
    serializer = EmailVerificationSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if account is locked
    if 'Account is temporarily locked' in str(serializer.errors):
        return Response(
            {'detail': 'Account is temporarily locked. Please try again later.'},
            status=status.HTTP_423_LOCKED
        )
    
    try:
        verification_token = serializer.validated_data['token']
        
        with transaction.atomic():
            # Verify user email
            user = verification_token.user
            user.is_email_verified = True
            user.save(update_fields=['is_email_verified'])
            
            return Response(
                {'message': 'Email verified successfully.'},
                status=status.HTTP_200_OK
            )
    
    except Exception as e:
        logger.error(f"Email verification error: {str(e)}")
        return Response(
            {'detail': 'Email verification failed. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def resend_verification(request):
    """
    Resend Email Verification
    POST /api/auth/resend-verification/
    """
    serializer = ResendVerificationSerializer(data=request.data)

    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    # Check if account is locked
    if 'Account is temporarily locked' in str(serializer.errors):
        return Response(
            {'detail': 'Account is temporarily locked. Please try again later.'},
            status=status.HTTP_423_LOCKED
        )

    email = serializer.validated_data['email']
    ip_address = SecurityUtils.get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    SecurityUtils.log_login_attempt(
        user=None,
        email=email,
        ip_address=ip_address,
        user_agent=user_agent,
        success=False,
        failure_reason='Email verification request'
    )

    try:
        user = User.objects.get(email=email)

        # Generate and send verification token
        verification_token = EmailTokenManager.generate_verification_token(user)
        EmailService.send_verification_email(user, verification_token)

        # Log success
        SecurityUtils.log_login_attempt(
            user=user,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True
        )

        return Response({'message': 'Verification email sent successfully.'}, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        SecurityUtils.log_login_attempt(
            user=None,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            success=True
        )
        # Don't reveal email status
        return Response({'message': 'Verification email sent successfully.'}, status=status.HTTP_200_OK)

    except Exception as e:
        logger.error(f"Resend verification error: {str(e)}")
        return Response(
            {'detail': 'Failed to send verification email. Please try again.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
        

@api_view(['POST'])
@permission_classes([AllowAny])
def refresh_token(request):
    """
    Refresh Access Token with token rotation
    POST /api/auth/refresh/
    """
    serializer = RefreshTokenSerializer(data=request.data)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        old_token = request.data.get('refresh_token')
        refresh_token_obj = serializer.validated_data['refresh_token']
        user = refresh_token_obj.user
        
        # Generate new access token
        access_token = JWTTokenManager.generate_access_token(user)
        
        # Rotate refresh token
        new_refresh_token = JWTTokenManager.rotate_refresh_token(old_token)
        
        return Response({
            'access_token': access_token,
            'refresh_token': new_refresh_token,
            'message': 'Token refreshed successfully.'
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return Response(
            {'detail': 'Token refresh failed.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def enable_2fa(request):
    """Enable two-factor authentication"""
    if request.user.two_factor_enabled:
        return Response({'detail': '2FA is already enabled.'}, status=400)
    
    secret = TwoFactorManager.generate_secret()
    qr_code = TwoFactorManager.get_qr_code(request.user, secret)
    
    # Store secret temporarily (you might want to use cache)
    cache.set(f"2fa_setup_{request.user.id}", secret, 300)  # 5 minutes
    
    return Response({
        'secret': secret,
        'qr_code': qr_code,
        'manual_entry_key': secret,  # Same as secret, but clearer naming
        'issuer': 'NCLEX Virtual School',
        'account_name': request.user.email,
        'message': 'You can either scan the QR code OR manually enter the secret key into your authenticator app.',
        'instructions': {
            'option_1': 'Scan the QR code with your authenticator app',
            'option_2': f'Manually add account with key: {secret}'
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def confirm_2fa(request):
    """Confirm 2FA setup"""
    token = request.data.get('token')
    secret = cache.get(f"2fa_setup_{request.user.id}")
    
    if not secret:
        return Response({'detail': 'Setup expired. Please try again.'}, status=400)
    
    if not TwoFactorManager.verify_token(secret, token):
        return Response({'detail': 'Invalid token.'}, status=400)
    
    # Enable 2FA
    request.user.two_factor_enabled = True
    request.user.two_factor_secret = secret
    request.user.save()
    
    cache.delete(f"2fa_setup_{request.user.id}")
    
    return Response({'message': '2FA enabled successfully.'})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def disable_2fa(request):
    """Disable two-factor authentication"""
    if not request.user.two_factor_enabled:
        return Response({'detail': '2FA is not enabled.'}, status=400)
    
    # Require current password for security
    password = request.data.get('password')
    if not password or not request.user.check_password(password):
        return Response({'detail': 'Current password is required.'}, status=400)
    
    # Optional: Require 2FA token to disable (more secure)
    token = request.data.get('token')
    if not token or not TwoFactorManager.verify_token(request.user.two_factor_secret, token):
        return Response({'detail': 'Valid 2FA token required to disable.'}, status=400)
    
    # Disable 2FA
    request.user.two_factor_enabled = False
    request.user.two_factor_secret = None
    request.user.backup_codes = []
    request.user.save()
    
    # Log security event
    SecurityMonitor.log_security_event(
        event_type='2FA_DISABLED',
        user=request.user,
        details=f'2FA disabled by user',
        severity='WARNING'
    )
    
    return Response({'message': '2FA disabled successfully.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_backup_codes(request):
    """Generate backup codes for 2FA"""
    if not request.user.two_factor_enabled:
        return Response({'detail': '2FA must be enabled first.'}, status=400)
    
    # Generate 10 backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    
    # Hash and store them
    hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]
    request.user.backup_codes = hashed_codes
    request.user.save()
    
    return Response({
        'backup_codes': backup_codes,
        'message': 'Store these backup codes safely. They can only be used once.'
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_2fa_status(request):
    """Get current 2FA status"""
    return Response({
        'enabled': request.user.two_factor_enabled,
        'backup_codes_count': len(request.user.backup_codes) if request.user.backup_codes else 0
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def regenerate_backup_codes(request):
    """Regenerate backup codes when they're finished"""
    if not request.user.two_factor_enabled:
        return Response({'detail': '2FA must be enabled first.'}, status=400)
    
    # Require current 2FA token to regenerate (security)
    token = request.data.get('token')
    if not token or not TwoFactorManager.verify_token(request.user.two_factor_secret, token):
        return Response({'detail': 'Valid 2FA token required to regenerate backup codes.'}, status=400)
    
    # Generate new backup codes
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    
    # Hash and store them (replaces old ones)
    hashed_codes = [hashlib.sha256(code.encode()).hexdigest() for code in backup_codes]
    request.user.backup_codes = hashed_codes
    request.user.save()
    
    # Log security event
    SecurityMonitor.log_security_event(
        event_type='BACKUP_CODES_REGENERATED',
        user=request.user,
        details=f'User regenerated backup codes',
        severity='INFO'
    )
    
    return Response({
        'backup_codes': backup_codes,
        'message': 'New backup codes generated. Previous codes are now invalid.',
        'warning': 'Store these backup codes safely. They can only be used once each.'
    })



@api_view(['POST'])
@permission_classes([AllowAny])  # Emergency access
def emergency_disable_2fa(request):
    """Emergency disable 2FA if user has no access to authenticator or backup codes"""
    email = request.data.get('email')
    password = request.data.get('password')
    
    if not email or not password:
        return Response({'detail': 'Email and password required.'}, status=400)
  
    ip_address = SecurityUtils.get_client_ip(request)

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'detail': 'Invalid credentials.'}, status=400)
    
    if not user.check_password(password):
        return Response({'detail': 'Invalid credentials.'}, status=400)
    
    if not user.two_factor_enabled:
        return Response({'detail': '2FA is not enabled.'}, status=400)
    
    # Check if user has pending emergency request
    existing_request = cache.get(f"emergency_2fa_disable_{user.id}")
    if existing_request:
        return Response({
            'detail': 'You already have a pending emergency 2FA disable request.'
        }, status=400)
    
    # Create emergency disable request (requires admin approval)
    emergency_token = secrets.token_urlsafe(32)
    expires_at = timezone.now() + timedelta(hours=24)
    
    # Store in cache for admin to approve
    cache.set(f"emergency_2fa_disable_{emergency_token}", {
        'user_id': str(user.id),
        'email': user.email,
        'requested_at': timezone.now().isoformat(),
        'ip_address': ip_address,
        'user_agent': request.META.get('HTTP_USER_AGENT', ''),
        'expires_at': expires_at.isoformat()
    }, 86400)  # 24 hours
    
    # Also store by user ID to prevent multiple requests
    cache.set(f"emergency_2fa_disable_{user.id}", emergency_token, 86400)
    
    # Send emergency email to user
    EmailService.send_emergency_2fa_disable_email(user, request, emergency_token)
    
    # Alert admins
    SecurityMonitor.log_security_event(
        event_type='EMERGENCY_2FA_DISABLE_REQUESTED',
        user=user,
        details=f'User requested emergency 2FA disable from IP {ip_address}',
        severity='CRITICAL'
    )
    
    return Response({
        'message': 'Emergency 2FA disable request submitted. Check your email for further instructions.',
        'note': 'This request requires admin approval for security reasons and expires in 24 hours.'
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    """
    User Logout
    POST /api/auth/logout/
    """
    try:
        # Get refresh token from request
        refresh_token = request.data.get('refresh_token')
        
        if refresh_token:
            # Blacklist the refresh token
            JWTTokenManager.blacklist_refresh_token(refresh_token)
        
        # Optionally deactivate current session
        session_token = request.data.get('session_token')
        if session_token:
            from .models import UserSession
            UserSession.objects.filter(
                user=request.user,
                session_token=session_token
            ).update(is_active=False)
        
        return Response(
            {'message': 'Logged out successfully.'},
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        return Response(
            {'detail': 'Logout failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_all(request):
    """
    Logout from all devices
    POST /api/auth/logout-all/
    """
    try:
        # Blacklist all refresh tokens
        JWTTokenManager.blacklist_all_user_tokens(request.user)
        
        # Deactivate all sessions
        from .models import UserSession
        UserSession.objects.filter(user=request.user).update(is_active=False)
        
        return Response(
            {'message': 'Logged out from all devices successfully.'},
            status=status.HTTP_200_OK
        )
    
    except Exception as e:
        logger.error(f"Logout all error: {str(e)}")
        return Response(
            {'detail': 'Logout from all devices failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_profile(request):
    """
    Get User Profile
    GET /api/users/me/
    """
    serializer = UserProfileSerializer(request.user)
    return Response(serializer.data, status=status.HTTP_200_OK)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def update_profile(request):
    """
    Update User Profile
    PUT/PATCH /api/users/me/
    """
    serializer = UserProfileUpdateSerializer(request.user, data=request.data, partial=True)
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        user = serializer.save()
        response_serializer = UserProfileSerializer(user)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Profile update error: {str(e)}")
        return Response(
            {'detail': 'Profile update failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def change_password(request):
    """
    Change User Password
    POST /api/auth/change-password/
    """
    serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            user = request.user
            new_password = serializer.validated_data['new_password']
            
            # Update password
            user.set_password(new_password)
            user.password_changed_at = timezone.now()
            user.save(update_fields=['password', 'password_changed_at'])
            
            # Blacklist all refresh tokens (force re-login on other devices)
            JWTTokenManager.blacklist_all_user_tokens(user)
            
            # Send password changed email
            EmailService.send_password_changed_email(user)
            
            return Response(
                {'message': 'Password changed successfully.'},
                status=status.HTTP_200_OK
            )
    
    except Exception as e:
        logger.error(f"Password change error: {str(e)}")
        return Response(
            {'detail': 'Password change failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def user_sessions(request):
    """
    Get User Active Sessions
    GET /api/auth/sessions/
    """
    try:
        from .models import UserSession
        from .serializers import UserSessionSerializer
        
        sessions = UserSession.objects.filter(user=request.user, is_active=True)
        serializer = UserSessionSerializer(sessions, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Sessions fetch error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch sessions.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_account(request):
    """
    Request Account Deletion (14-day grace period)
    POST /api/auth/delete-account/
    """
    serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            user = request.user
            
            # Request deletion with 14-day grace period
            user.request_deletion(days=14)
            
            # Blacklist all tokens
            JWTTokenManager.blacklist_all_user_tokens(user)
            
            # Deactivate all sessions
            from .models import UserSession
            UserSession.objects.filter(user=user).update(is_active=False)
            
            # Send deletion confirmation email
            EmailService.send_account_deletion_email(user)
            
            return Response({
                'message': 'Account deletion requested. Your account will be deleted in 14 days. You can cancel this request by logging in before the deletion date.',
                'deletion_scheduled_for': user.deletion_scheduled_for.isoformat()
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Account deletion request error: {str(e)}")
        return Response(
            {'detail': 'Account deletion request failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cancel_deletion(request):
    """
    Cancel Pending Account Deletion
    POST /api/auth/cancel-deletion/
    """
    user = request.user
    
    if not user.is_deletion_pending:
        return Response(
            {'detail': 'No pending account deletion found.'},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    serializer = CancelDeletionSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            user.cancel_deletion()
            
            # Send cancellation confirmation email
            EmailService.send_deletion_cancelled_email(user)
            
            return Response({
                'message': 'Account deletion cancelled successfully. Your account has been reactivated.'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Cancel deletion error: {str(e)}")
        return Response(
            {'detail': 'Cancel deletion failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def delete_account_immediate(request):
    """
    Delete Account Immediately (no grace period)
    POST /api/auth/delete-account-immediate/
    """
    serializer = DeleteAccountSerializer(data=request.data, context={'request': request})
    
    if not serializer.is_valid():
        return Response(
            {'detail': 'Invalid input data.', 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    try:
        with transaction.atomic():
            user = request.user
            
            # Send goodbye email before deletion
            EmailService.send_account_deleted_email(user)
            
            # Delete user account immediately
            user.delete()
            
            return Response({
                'message': 'Account deleted successfully.'
            }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"Immediate account deletion error: {str(e)}")
        return Response(
            {'detail': 'Account deletion failed.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )