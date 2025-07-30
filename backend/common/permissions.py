# common/permissions.py
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger(__name__)

class IsAuthenticated(BasePermission):
    """
    Custom authentication check that works with JWT middleware
    """
    def has_permission(self, request, view):
        print("=== IsAuthenticated Permission Check ===")
        print(f"Request user: {request.user}")
        print(f"User type: {type(request.user)}")
        print(f"User is_authenticated: {getattr(request.user, 'is_authenticated', 'No is_authenticated attribute')}")
        print(f"User is_anonymous: {getattr(request.user, 'is_anonymous', 'No is_anonymous attribute')}")
        print(f"User has backend: {hasattr(request.user, 'backend')}")
        
        # Check if user exists and is authenticated
        result = bool(request.user and not request.user.is_anonymous and request.user.is_authenticated)
        print(f"Authentication result: {result}")
        return result

class IsAdmin(BasePermission):
    """
    Permission class to check if user is admin or super_admin
    """
    def has_permission(self, request, view):
        print("=== IsAdmin Permission Check ===")
        print(f"Request user: {request.user}")
        print(f"User type: {type(request.user)}")
        print(f"User is_authenticated: {getattr(request.user, 'is_authenticated', 'No is_authenticated attribute')}")
        print(f"User is_anonymous: {getattr(request.user, 'is_anonymous', 'No is_anonymous attribute')}")
        print(f"User role: {getattr(request.user, 'role', 'No role attribute')}")
        print(f"User has backend: {hasattr(request.user, 'backend')}")
        
        # First check if user is authenticated
        if not request.user or request.user.is_anonymous or not request.user.is_authenticated:
            print("User not authenticated - permission denied")
            return False
        
        # Check if user has admin role
        if not hasattr(request.user, 'role'):
            print("User has no role attribute - permission denied")
            return False
            
        result = request.user.role in ['admin', 'super_admin']
        print(f"Admin role check result: {result}")
        return result

class IsSuperAdmin(BasePermission):
    """
    Permission class to check if user is super_admin
    """
    def has_permission(self, request, view):
        print("=== IsSuperAdmin Permission Check ===")
        print(f"Request user: {request.user}")
        print(f"User role: {getattr(request.user, 'role', 'No role attribute')}")
        
        if not request.user or request.user.is_anonymous or not request.user.is_authenticated:
            print("User not authenticated - permission denied")
            return False
        
        result = hasattr(request.user, 'role') and request.user.role == 'super_admin'
        print(f"Super admin check result: {result}")
        return result

class IsUser(BasePermission):
    """
    Permission class to check if user has 'user' role
    """
    def has_permission(self, request, view):
        print("=== IsUser Permission Check ===")
        print(f"Request user: {request.user}")
        print(f"User role: {getattr(request.user, 'role', 'No role attribute')}")
        
        if not request.user or request.user.is_anonymous or not request.user.is_authenticated:
            print("User not authenticated - permission denied")
            return False
        
        result = hasattr(request.user, 'role') and request.user.role == 'user'
        print(f"User role check result: {result}")
        return result

class IsOwnerOrAdmin(BasePermission):
    """
    Permission class to check if user is owner of object or admin
    """
    def has_permission(self, request, view):
        if not request.user or request.user.is_anonymous or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        # Check if user is admin/super_admin
        if hasattr(request.user, 'role') and request.user.role in ['admin', 'super_admin']:
            return True
        
        # Check if user is owner (assuming obj has user or created_by field)
        if hasattr(obj, 'user'):
            return obj.user == request.user
        elif hasattr(obj, 'created_by'):
            return obj.created_by == request.user
        
        return False

# Decorator functions for function-based views (keep these as backup)
def authentication_required(view_func):
    """Decorator to check if user is authenticated"""
    def wrapper(request, *args, **kwargs):
        print("=== AUTH DECORATOR DEBUG ===")
        print(f"User: {request.user}")
        print(f"User type: {type(request.user)}")
        print(f"User authenticated: {request.user.is_authenticated}")
        
        if not request.user.is_authenticated:
            print("User not authenticated - returning 401")
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        print("Authentication check passed - proceeding to view")
        return view_func(request, *args, **kwargs)
    return wrapper

def admin_required(view_func):
    """Decorator to check if user is admin"""
    def wrapper(request, *args, **kwargs):
        print("=== ADMIN DECORATOR DEBUG ===")
        print(f"User: {request.user}")
        print(f"User type: {type(request.user)}")
        print(f"User authenticated: {request.user.is_authenticated}")
        print(f"User role: {getattr(request.user, 'role', 'No role attribute')}")
        print(f"User ID: {getattr(request.user, 'id', 'No ID')}")
        
        if not request.user.is_authenticated:
            print("User not authenticated - returning 401")
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        # Check if user has admin role
        if not hasattr(request.user, 'role') or request.user.role not in ['admin', 'super_admin']:
            print(f"User role check failed - role is: {getattr(request.user, 'role', 'undefined')}")
            return Response(
                {'detail': 'Admin access required. Your role: ' + str(getattr(request.user, 'role', 'undefined'))},
                status=status.HTTP_403_FORBIDDEN
            )
        
        print("Admin check passed - proceeding to view")
        return view_func(request, *args, **kwargs)
    return wrapper

def super_admin_required(view_func):
    """Decorator to check if user is super admin"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not hasattr(request.user, 'role') or request.user.role != 'super_admin':
            return Response(
                {'detail': 'Super Admin access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return view_func(request, *args, **kwargs)
    return wrapper

def user_required(view_func):
    """Decorator to check if user has 'user' role"""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return Response(
                {'detail': 'Authentication required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        
        if not hasattr(request.user, 'role') or request.user.role != 'user':
            return Response(
                {'detail': 'User access required.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return view_func(request, *args, **kwargs)
    return wrapper