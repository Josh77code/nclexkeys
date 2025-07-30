# utils/payment_helpers.py - Add helper functions
from decimal import Decimal
from django.conf import settings

class PaymentHelper:
    """Helper functions for payment processing"""
    
    @staticmethod
    def calculate_platform_fee(amount: Decimal) -> dict:
        """Calculate platform fees"""
        # Your revenue split: 70% instructor, 30% platform
        instructor_share = amount * Decimal('0.70')
        platform_fee = amount * Decimal('0.30')
        
        return {
            'instructor_share': instructor_share,
            'platform_fee': platform_fee,
            'total': amount
        }
    
    @staticmethod
    def is_test_payment(payment_data: dict) -> bool:
        """Check if payment is in test mode"""
        return any([
            payment_data.get('reference', '').startswith('test_'),
            payment_data.get('customer', {}).get('email') == 'test@example.com',
            settings.DEBUG and not settings.PAYMENT_LIVE_MODE
        ])
    
    @staticmethod
    def generate_receipt_data(payment, enrollment):
        """Generate receipt data for successful payments"""
        return {
            'receipt_id': f"RCP-{payment.reference[-8:].upper()}",
            'student_name': payment.customer_name,
            'student_email': payment.customer_email,
            'course_title': payment.course.title,
            'amount_paid': float(payment.amount),
            'currency': payment.currency,
            'payment_method': payment.payment_method,
            'payment_date': payment.paid_at,
            'reference': payment.reference,
            'enrollment_date': enrollment.enrolled_at,
            'institution': 'NCLEX Virtual School'
        }
