# users/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User, EmailVerificationToken, PasswordResetToken, UserSession
import re


class UserRegistrationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True)
    role = serializers.ChoiceField(choices=['student', 'instructor'], required=True)
    
    class Meta:
        model = User
        fields = ['email', 'full_name', 'phone_number', 'role', 'password', 'confirm_password']
        extra_kwargs = {
            'email': {'required': True},
            'full_name': {'required': True},
            'phone_number': {'required': True},
        }
    
    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value
    
    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Full name must be at least 2 characters long.")
        
        # Check if it contains at least 2 words separated by space
        words = value.split()
        if len(words) < 2:
            raise serializers.ValidationError("Full name must contain at least 2 words separated by a space (e.g., 'John Doe').")
        
        return value
        
    def validate_phone_number(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits long.")

        # Remove spaces, hyphens, parentheses for validation
        cleaned = re.sub(r'[\s\-\(\)]', '', value)
        if not re.match(r'^\+?[\d]{10,15}$', cleaned):
            raise serializers.ValidationError("Enter a valid phone number.")

        return value

    def validate_role(self, value):
        # Map frontend roles to backend roles (only student and instructor allowed)
        role_mapping = {
            'student': 'user',      # Student -> User
            'instructor': 'admin'   # Instructor -> Admin (Course Creator/Instructor)
        }

        if value not in role_mapping:
            raise serializers.ValidationError("Only 'student' and 'instructor' roles are allowed during registration.")

        # Return the mapped backend role
        return role_mapping[value]
    
    def validate_password(self, value):
        # Custom password validation
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        
        return value
    
    def validate(self, attrs):
        if attrs['password'] != attrs['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('confirm_password')
        user = User.objects.create_user(**validated_data)
        return user


class UserLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")
        
        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid credentials.")
        
        # Check if account is locked
        if user.is_account_locked():
            raise serializers.ValidationError("Account is temporarily locked due to multiple failed login attempts. Please try again later. Check you email for further info")
        
        # Check if deletion is pending - allow login but show warning
        if user.is_deletion_pending:
            from django.utils import timezone
            days_remaining = (user.deletion_scheduled_for - timezone.now()).days
            # Allow login but add warning message to attrs
            attrs['deletion_warning'] = f"Your account is scheduled for deletion in {days_remaining} days. You can cancel this by going to your account settings."
        
        # Check if account is active
        if not user.is_active:
            raise serializers.ValidationError("Account is deactivated.")
        
        # Authenticate user
        user = authenticate(username=email, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        
        attrs['user'] = user
        return attrs


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if not user.is_active:
                raise serializers.ValidationError("Account is deactivated.")
        except User.DoesNotExist:
            # Don't reveal that the user doesn't exist
            pass
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_new_password = serializers.CharField(write_only=True)
    
    def validate_new_password(self, value):
        # Same validation as registration
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        
        return value
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError("Passwords do not match.")

        # Validate token first
        token = attrs.get('token')
        try:
            reset_token = PasswordResetToken.objects.get(token=token)
            if not reset_token.is_valid():
                raise serializers.ValidationError("Invalid or expired token.")
            attrs['reset_token'] = reset_token
        except PasswordResetToken.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired token.")

        # Then check if account is locked
        if reset_token.user.is_account_locked():
            raise serializers.ValidationError("Account is temporarily locked. Please try again later.")

        return attrs


class EmailVerificationSerializer(serializers.Serializer):
    token = serializers.CharField()
    
    def validate_token(self, value):
        try:
            verification_token = EmailVerificationToken.objects.get(token=value)
            if not verification_token.is_valid():
                raise serializers.ValidationError("Invalid or expired token.")
            
            if verification_token.user.is_account_locked():
                raise serializers.ValidationError("Account is temporarily locked. Please try again later.")

            return verification_token
        except EmailVerificationToken.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired token.")


class ResendVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
            if user.is_email_verified:
                raise serializers.ValidationError("Email is already verified.")
            if not user.is_active:
                raise serializers.ValidationError("Account is deactivated.")
            if user.is_account_locked():
                raise serializers.ValidationError("Account is temporarily locked. Please try again later.")
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        return value


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'phone_number', 'role', 'created_at',                 'is_email_verified', 'is_deletion_pending', 'deletion_scheduled_for']
        read_only_fields = ['id', 'email', 'role', 'created_at', 'is_email_verified', 
        'is_deletion_pending', 'deletion_scheduled_for']
    
    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Full name must be at least 2 characters long.")

        # Check if it contains at least 2 words separated by space
        words = value.split()
        if len(words) < 2:
            raise serializers.ValidationError("Full name must contain at least 2 words separated by a space (e.g., 'John Doe').")

        return value


class UserProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['full_name', 'phone_number']
    
    def validate_full_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Full name must be at least 2 characters long.")
        
        # Check if it contains at least 2 words separated by space
        words = value.split()
        if len(words) < 2:
            raise serializers.ValidationError("Full name must contain at least 2 words separated by a space (e.g., 'John Doe').")
        
        return value
    
    def validate_phone_number(self, value):
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Phone number must be at least 10 digits long.")

        cleaned = re.sub(r'[\s\-\(\)]', '', value)
        if not re.match(r'^\+?[\d]{10,15}$', cleaned):
            raise serializers.ValidationError("Enter a valid phone number.")

        return value


class RefreshTokenSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()
    
    def validate_refresh_token(self, value):
        from .models import RefreshToken
        try:
            refresh_token = RefreshToken.objects.get(token=value)
            if not refresh_token.is_valid():
                raise serializers.ValidationError("Invalid or expired refresh token.")
            return refresh_token
        except RefreshToken.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired refresh token.")


class UserSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserSession
        fields = ['id', 'ip_address', 'user_agent', 'location', 'is_new_device', 'created_at', 'last_activity', 'is_active']
        read_only_fields = ['id', 'created_at', 'last_activity']


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_new_password = serializers.CharField(write_only=True)
    
    def validate_new_password(self, value):
        # Same validation as registration
        if len(value) < 8:
            raise serializers.ValidationError("Password must be at least 8 characters long.")
        
        if not re.search(r'[A-Z]', value):
            raise serializers.ValidationError("Password must contain at least one uppercase letter.")
        
        if not re.search(r'[a-z]', value):
            raise serializers.ValidationError("Password must contain at least one lowercase letter.")
        
        if not re.search(r'\d', value):
            raise serializers.ValidationError("Password must contain at least one number.")
        
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', value):
            raise serializers.ValidationError("Password must contain at least one special character.")
        
        try:
            validate_password(value)
        except ValidationError as e:
            raise serializers.ValidationError(list(e.messages))
        
        return value
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['confirm_new_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return attrs
    
    def validate_current_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
    

class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    confirm_deletion = serializers.BooleanField()
    
    def validate_confirm_deletion(self, value):
        if not value:
            raise serializers.ValidationError("You must confirm account deletion.")
        return value
    
    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Password is incorrect.")
        return value
    

class CancelDeletionSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)
    
    def validate_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Password is incorrect.")
        return value