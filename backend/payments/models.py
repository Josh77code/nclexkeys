# payments/models.py
from django.db import models
from django.utils import timezone
from users.models import User
from courses.models import Course
import uuid
import random
import string
from django.contrib.auth import get_user_model
from decimal import Decimal


# Create your models here.
class PaymentGateway(models.Model):
    """Payment gateway configuration"""
    GATEWAY_CHOICES = (
        ('paystack', 'Paystack'),
        ('flutterwave', 'Flutterwave'),
        ('stripe', 'Stripe'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=50, choices=GATEWAY_CHOICES, unique=True)
    display_name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    
    # Gateway specific settings
    public_key = models.CharField(max_length=255, blank=True)
    secret_key = models.CharField(max_length=255, blank=True)
    webhook_secret = models.CharField(max_length=255, blank=True)
    
    # Supported currencies (JSON field)
    supported_currencies = models.JSONField(default=list, help_text="List of supported currency codes")
    
    # Fee settings
    transaction_fee_percentage = models.DecimalField(max_digits=5, decimal_places=4, default=0.0150)  # 1.5%
    transaction_fee_cap = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Payout configuration
    supports_transfers = models.BooleanField(default=False)
    transfer_secret_key = models.CharField(max_length=500, blank=True, null=True)  # For payouts
    minimum_transfer_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    
    class Meta:
        db_table = 'payment_gateways'
        ordering = ['name']
    
    def __str__(self):
        return self.display_name
    
    def save(self, *args, **kwargs):
        # Ensure only one default gateway
        if self.is_default:
            PaymentGateway.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class Payment(models.Model):
    """Payment transactions"""
    STATUS_CHOICES = (
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('partially_refunded', 'Partially Refunded'),
    )
    
    CURRENCY_CHOICES = (
        ('NGN', 'Nigerian Naira'),
        ('USD', 'US Dollar'),
        ('EUR', 'Euro'),
        ('GBP', 'British Pound'),
        ('GHS', 'Ghanaian Cedi'),
        ('KES', 'Kenyan Shilling'),
        ('ZAR', 'South African Rand'),
    )
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Payment details
    reference = models.CharField(max_length=100, unique=True, db_index=True)
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.PROTECT)
    gateway_reference = models.CharField(max_length=255, blank=True, help_text="Gateway's transaction reference")
    
    # User and course
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='payments')
    
    # Amount details
    amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount in the specified currency")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='NGN')
    
    # Fee breakdown
    gateway_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    platform_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, help_text="Amount after fees")
    
    # Status and metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=50, blank=True, help_text="card, bank_transfer, ussd, etc.")
    
    # Customer info (from gateway response)
    customer_email = models.EmailField()
    customer_name = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    
    # Authorization data (for recurring payments)
    authorization_code = models.CharField(max_length=255, blank=True)
    card_type = models.CharField(max_length=20, blank=True)
    last_4_digits = models.CharField(max_length=4, blank=True)
    exp_month = models.CharField(max_length=2, blank=True)
    exp_year = models.CharField(max_length=4, blank=True)
    bank = models.CharField(max_length=100, blank=True)
    
    # Timestamps
    initiated_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)
    
    # Gateway response data
    gateway_response = models.JSONField(default=dict, blank=True)
    failure_reason = models.TextField(blank=True)
    
    # Callback URLs
    callback_url = models.URLField(blank=True)
    webhook_verified = models.BooleanField(default=False)
    
    # IP tracking
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    
    class Meta:
        db_table = 'payments'
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['reference']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['course']),
            models.Index(fields=['status', 'initiated_at']),
            models.Index(fields=['gateway_reference']),
        ]
    
    def __str__(self):
        return f"Payment {self.reference} - {self.user.full_name} - {self.amount} {self.currency}"
    
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = self.generate_reference()
        
        # Calculate net amount
        if self.amount and not self.net_amount:
            self.net_amount = self.amount - self.gateway_fee - self.platform_fee
        
        # Set customer details from user if not provided
        if not self.customer_email:
            self.customer_email = self.user.email
        if not self.customer_name:
            self.customer_name = self.user.full_name
        if not self.customer_phone:
            self.customer_phone = getattr(self.user, 'phone_number', '')
        
        super().save(*args, **kwargs)
    
    def generate_reference(self):
        """Generate unique payment reference"""
        while True:
            reference = f"NCLEX_{timezone.now().strftime('%Y%m%d')}_{self.user.id.hex[:8]}_{uuid.uuid4().hex[:8]}"
            if not Payment.objects.filter(reference=reference).exists():
                return reference
    
    def mark_as_paid(self):
        """Mark payment as completed"""
        self.status = 'completed'
        self.paid_at = timezone.now()
        self.save(update_fields=['status', 'paid_at'])
    
    def mark_as_failed(self, reason=''):
        """Mark payment as failed"""
        self.status = 'failed'
        self.failed_at = timezone.now()
        self.failure_reason = reason
        self.save(update_fields=['status', 'failed_at', 'failure_reason'])
    
    def is_successful(self):
        return self.status == 'completed'
    
    def can_be_refunded(self):
        return self.status in ['completed'] and self.paid_at
    
    def get_formatted_amount(self):
        """Get formatted amount with currency symbol"""
        symbols = {
            'NGN': '₦',
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'GHS': 'GH₵',
            'KES': 'KSh',
            'ZAR': 'R'
        }
        symbol = symbols.get(self.currency, self.currency)
        return f"{symbol}{self.amount:,.2f}"

    def is_refundable(self):
        '''Check if payment is eligible for refund'''
        if self.status != 'completed':
            return False
        
        # Check if payment is within refund window (e.g., 30 days)
        from datetime import timedelta
        refund_window = timedelta(days=30)
        
        if timezone.now() - self.paid_at > refund_window:
            return False
        
        # Check if already refunded
        if self.refunds.filter(status='completed').exists():
            return False
        
        return True
    
    @property
    def total_refunded(self):
        from decimal import Decimal
        '''Get total amount refunded for this payment'''
        return self.refunds.filter(status='completed').aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    @property
    def remaining_refundable_amount(self):
        '''Get remaining amount that can be refunded'''
        return self.amount - self.total_refunded
    
    def can_refund_amount(self, amount):
        '''Check if specific amount can be refunded'''
        return amount <= self.remaining_refundable_amount

class InstructorPayout(models.Model):
    PAYOUT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled')
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instructor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payouts')
    period_start = models.DateField()
    period_end = models.DateField()
    
    # Earnings breakdown
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    instructor_share = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # 70%
    platform_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)     # 30%
    
    # Deductions
    previous_advance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refund_deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Final payout
    net_payout = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    minimum_payout = models.DecimalField(max_digits=12, decimal_places=2, default=1000)  # Min 1000 NGN
    
    # Payout details
    status = models.CharField(max_length=20, choices=PAYOUT_STATUS_CHOICES, default='pending')
    payout_method = models.CharField(max_length=50, default='bank_transfer')
    bank_account = models.JSONField(default=dict)  # Store bank details

    # Bank account fields for instructors
    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_number = models.CharField(max_length=20, blank=True, null=True)
    account_name = models.CharField(max_length=100, blank=True, null=True)
    bank_code = models.CharField(max_length=10, blank=True, null=True)  # For Paystack/Flutterwave
    recipient_code = models.CharField(max_length=100, blank=True, null=True)  # Paystack recipient code
    
    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    gateway_reference = models.CharField(max_length=255, blank=True)
    gateway_response = models.JSONField(default=dict)
    
    class Meta:
        db_table = 'instructor_payouts'
        unique_together = ['instructor', 'period_start', 'period_end']
        ordering = ['-created_at']
        
    def __str__(self):
        return f"Payout {self.instructor.full_name} - {self.period_start} to {self.period_end}"
    
    def calculate_payout(self):
        """Calculate net payout amount"""
        self.net_payout = self.instructor_share - self.previous_advance - self.refund_deductions
        self.save(update_fields=['net_payout'])
        return self.net_payout
    
    def is_eligible_for_payout(self):
        """Check if payout meets minimum requirements"""
        return self.net_payout >= self.minimum_payout


class InstructorBankAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instructor = models.OneToOneField(User, on_delete=models.CASCADE, related_name='bank_account')
    
    # Bank details
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=20)
    account_name = models.CharField(max_length=100)
    bank_code = models.CharField(max_length=10)  # Nigerian bank codes
    
    # Recipient codes for transfers (Payment gateway recipient codes)
    paystack_recipient_code = models.CharField(max_length=100, blank=True, null=True)
    flutterwave_recipient_id = models.CharField(max_length=100, blank=True, null=True)
    
    # Verification
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_account_name = models.CharField(max_length=100, blank=True)
    verification_provider = models.CharField(max_length=20, blank=True)  # 'paystack' or 'flutterwave'
    verification_attempts = models.IntegerField(default=0)
    last_verification_attempt = models.DateTimeField(null=True, blank=True)
    verification_error = models.TextField(blank=True)

    # Auto payout setting
    auto_payout_enabled = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'instructor_bank_accounts'

    def __str__(self):
        return f"{self.instructor.full_name} - {self.bank_name} ({self.account_number})"
    
    def can_enable_auto_payout(self):
        """Check if instructor can enable auto payout"""
        return self.is_verified and self.verification_attempts < 3
    
    def get_recipient_code(self, provider='paystack'):
        """Get recipient code for specific provider"""
        if provider == 'paystack':
            return self.paystack_recipient_code
        elif provider == 'flutterwave':
            return self.flutterwave_recipient_code
        return None


class PaymentRefund(models.Model):
    """Payment refunds"""
    REFUND_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('pending_review', 'Pending Review'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    
    # Refund details
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=REFUND_STATUS_CHOICES, default='pending')
    
    # Gateway details
    gateway_reference = models.CharField(max_length=255, blank=True)
    gateway_response = models.JSONField(default=dict, blank=True)
    
    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Failure tracking
    failure_reason = models.TextField(blank=True)
    
    # Admin details
    requested_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='requested_refunds')
    processed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='processed_refunds'
    )
    admin_notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'payment_refunds'
        ordering = ['-requested_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['payment']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Refund {self.amount} for {self.payment.reference} {self.payment.currency}"
    
    @property
    def is_processable(self):
        return self.status in ['pending', 'pending_review']
    
    @property
    def is_completed(self):
        return self.status == 'completed'
    
    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = f"REF_{self.payment.reference}_{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)


class PaymentWebhook(models.Model):
    """Webhook logs for debugging"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.ForeignKey(PaymentGateway, on_delete=models.CASCADE)
    
    # Webhook data
    event_type = models.CharField(max_length=100)
    reference = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    headers = models.JSONField(default=dict, blank=True)
    
    # Processing status
    processed = models.BooleanField(default=False)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    
    # Related payment
    payment = models.ForeignKey(Payment, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        db_table = 'payment_webhooks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['gateway', 'event_type']),
            models.Index(fields=['reference']),
            models.Index(fields=['processed', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.gateway.name} - {self.event_type} - {self.reference}"


class PaymentStat(models.Model):
    """Daily payment statistics"""
    date = models.DateField(unique=True)
    
    # Transaction counts
    total_transactions = models.PositiveIntegerField(default=0)
    successful_transactions = models.PositiveIntegerField(default=0)
    failed_transactions = models.PositiveIntegerField(default=0)
    
    # Revenue by currency
    ngn_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    usd_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total_revenue_ngn = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)  # All converted to NGN
    
    # Fees
    total_gateway_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_platform_fees = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_revenue = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    
    # Course enrollments
    course_enrollments = models.PositiveIntegerField(default=0)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'payment_stats'
        ordering = ['-date']
    
    def __str__(self):
        return f"Payment Stats - {self.date}"