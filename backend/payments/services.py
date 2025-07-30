# payments/services.py
import requests
import hmac
import hashlib
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import Payment, PaymentGateway, PaymentWebhook
from django.db.models import Sum, Q
from datetime import datetime, timedelta
from courses.models import CourseEnrollment
from .models import Payment, InstructorPayout, InstructorBankAccount
from users.models import User

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


class PaymentServiceFactory:
    """Factory to get payment service based on gateway"""
    
    @staticmethod
    def get_service(gateway_name):
        """Get payment service with proper validation"""
        services = {
            'paystack': PaystackService,
            'flutterwave': FlutterwaveService,
        }
        
        service_class = services.get(gateway_name.lower())
        if not service_class:
            raise ValueError(f"Unsupported payment gateway: {gateway_name}")
        
        try:
            return service_class()
        except ValueError as e:
            logger.error(f"Payment service initialization failed: {str(e)}")
            raise e


class BasePaymentService:
    """Base payment service interface"""
    
    def __init__(self):
        self.gateway = None
    
    def initialize_payment(self, payment: Payment, callback_url: str) -> dict:
        raise NotImplementedError
    
    def verify_payment(self, reference: str) -> dict:
        raise NotImplementedError
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        raise NotImplementedError
    
    def process_webhook(self, payload: dict, headers: dict) -> dict:
        raise NotImplementedError
    
    def initiate_refund(self, payment: Payment, amount: Decimal, reason: str) -> dict:
        raise NotImplementedError


class PaystackService(BasePaymentService):
    """Paystack payment service"""
    
    def __init__(self):
        self.gateway = PaymentGateway.objects.filter(name='paystack', is_active=True).first()
        if not self.gateway:
            raise ValueError("Paystack gateway not configured")
        
        self.base_url = "https://api.paystack.co"
        self.secret_key = self.gateway.secret_key
        self.public_key = self.gateway.public_key
    
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
    
    def _convert_to_kobo(self, amount: Decimal) -> int:
        """Convert amount to kobo (smallest currency unit)"""
        return int(float(amount) * 100)
    
    def _convert_from_kobo(self, amount_kobo: int) -> Decimal:
        """Convert from kobo to main currency unit"""
        return Decimal(amount_kobo) / 100
    
    def initialize_payment(self, payment: Payment, callback_url: str) -> dict:
        """Initialize payment with Paystack"""
        try:
            url = f"{self.base_url}/transaction/initialize"
            
            # Convert amount to kobo for NGN, cents for USD
            if payment.currency == 'NGN':
                amount_subunit = self._convert_to_kobo(payment.amount)
            else:
                amount_subunit = self._convert_to_kobo(payment.amount)  # Works for most currencies
            
            payload = {
                "email": payment.customer_email,
                "amount": amount_subunit,
                "currency": payment.currency,
                "reference": payment.reference,
                "callback_url": callback_url,
                "metadata": {
                    "user_id": str(payment.user.id),
                    "course_id": str(payment.course.id),
                    "course_title": payment.course.title,
                    "user_name": payment.customer_name,
                    "payment_id": str(payment.id),
                    "custom_fields": [
                        {
                            "display_name": "Course Title",
                            "variable_name": "course_title",
                            "value": payment.course.title
                        },
                        {
                            "display_name": "Student Name",
                            "variable_name": "student_name", 
                            "value": payment.customer_name
                        }
                    ]
                },
                "channels": ["card", "bank", "ussd", "qr", "mobile_money", "bank_transfer"],
                "split_code": getattr(settings, 'PAYSTACK_SPLIT_CODE', None),  # For revenue sharing
            }
            
            # Remove None values
            payload = {k: v for k, v in payload.items() if v is not None}
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status'):
                # Update payment with gateway reference
                payment.gateway_reference = result['data'].get('reference', payment.reference)
                payment.gateway_response = result
                payment.save(update_fields=['gateway_reference', 'gateway_response'])
                
                return {
                    'success': True,
                    'data': result['data'],
                    'payment_url': result['data']['authorization_url'],
                    'reference': payment.reference
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Payment initialization failed'),
                    'error': result
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack API error: {str(e)}")
            return {
                'success': False,
                'message': 'Payment service temporarily unavailable',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Payment initialization error: {str(e)}")
            return {
                'success': False,
                'message': 'Payment initialization failed',
                'error': str(e)
            }
    
    def verify_payment(self, reference: str) -> dict:
        """Verify payment with Paystack"""
        try:
            url = f"{self.base_url}/transaction/verify/{reference}"
            
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status'):
                data = result['data']
                
                return {
                    'success': True,
                    'data': data,
                    'verified': True,
                    'amount': self._convert_from_kobo(data.get('amount', 0)),
                    'currency': data.get('currency'),
                    'status': data.get('status'),
                    'reference': data.get('reference'),
                    'paid_at': data.get('paid_at'),
                    'customer': data.get('customer', {}),
                    'authorization': data.get('authorization', {}),
                    'fees': data.get('fees'),
                    'gateway_response': data.get('gateway_response'),
                }
            else:
                return {
                    'success': False,
                    'verified': False,
                    'message': result.get('message', 'Payment verification failed'),
                    'error': result
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack verification error: {str(e)}")
            return {
                'success': False,
                'verified': False,
                'message': 'Payment verification failed',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Payment verification error: {str(e)}")
            return {
                'success': False,
                'verified': False,
                'message': 'Payment verification failed',
                'error': str(e)
            }
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Paystack webhook signature"""
        try:
            computed_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()
            
            return hmac.compare_digest(computed_signature, signature)
        except Exception as e:
            logger.error(f"Webhook signature verification error: {str(e)}")
            return False
    
    def process_webhook(self, payload: dict, headers: dict) -> dict:
        """Process Paystack webhook"""
        try:
            event_type = payload.get('event')
            data = payload.get('data', {})
            reference = data.get('reference', '')
            
            # Log webhook
            webhook = PaymentWebhook.objects.create(
                gateway=self.gateway,
                event_type=event_type,
                reference=reference,
                payload=payload,
                headers=headers
            )
            
            result = {'success': False, 'message': 'Unknown event type'}
            
            if event_type == 'charge.success':
                result = self._handle_charge_success(data)
            elif event_type == 'charge.failed':
                result = self._handle_charge_failed(data)
            elif event_type == 'transfer.success':
                result = self._handle_transfer_success(data)
            elif event_type == 'refund.processed':
                result = self._handle_refund_processed(data)
            
            # Update webhook log
            webhook.success = result.get('success', False)
            webhook.processed = True
            webhook.processed_at = timezone.now()
            if not result.get('success'):
                webhook.error_message = result.get('message', '')
            webhook.save()
            
            return result
            
        except Exception as e:
            logger.error(f"Webhook processing error: {str(e)}")
            return {
                'success': False,
                'message': f'Webhook processing failed: {str(e)}'
            }
    
    def _handle_charge_success(self, data: dict) -> dict:
        """Handle successful charge webhook"""
        try:
            reference = data.get('reference')
            if not reference:
                return {'success': False, 'message': 'No reference in webhook data'}
            
            payment = Payment.objects.filter(reference=reference).first()
            if not payment:
                return {'success': False, 'message': f'Payment not found: {reference}'}
            
            if payment.status == 'completed':
                return {'success': True, 'message': 'Payment already completed'}
            
            # Update payment
            payment.status = 'completed'
            payment.paid_at = timezone.now()
            payment.gateway_response = data
            payment.webhook_verified = True
            
            # Extract additional data
            authorization = data.get('authorization', {})
            if authorization:
                payment.authorization_code = authorization.get('authorization_code', '')
                payment.card_type = authorization.get('card_type', '')
                payment.last_4_digits = authorization.get('last4', '')
                payment.exp_month = authorization.get('exp_month', '')
                payment.exp_year = authorization.get('exp_year', '')
                payment.bank = authorization.get('bank', '')
            
            payment.payment_method = data.get('channel', '')
            
            # Calculate fees
            fees = data.get('fees', 0)
            if fees:
                payment.gateway_fee = self._convert_from_kobo(fees)
                payment.net_amount = payment.amount - payment.gateway_fee
            
            payment.save()
            
            return {'success': True, 'message': 'Payment completed successfully'}
            
        except Exception as e:
            logger.error(f"Charge success handling error: {str(e)}")
            return {'success': False, 'message': f'Failed to process charge success: {str(e)}'}
    
    def _handle_charge_failed(self, data: dict) -> dict:
        """Handle failed charge webhook"""
        try:
            reference = data.get('reference')
            payment = Payment.objects.filter(reference=reference).first()
            
            if payment and payment.status != 'failed':
                payment.status = 'failed'
                payment.failed_at = timezone.now()
                payment.failure_reason = data.get('gateway_response', 'Payment failed')
                payment.gateway_response = data
                payment.webhook_verified = True
                payment.save()
            
            return {'success': True, 'message': 'Payment failure processed'}
            
        except Exception as e:
            logger.error(f"Charge failed handling error: {str(e)}")
            return {'success': False, 'message': f'Failed to process charge failure: {str(e)}'}
    
    def _handle_transfer_success(self, data: dict) -> dict:
        """Handle transfer success (for refunds)"""
        # Implementation for refund completion
        return {'success': True, 'message': 'Transfer processed'}
    
    def _handle_refund_processed(self, data: dict) -> dict:
        """Handle refund processed webhook"""
        # Implementation for refund completion
        return {'success': True, 'message': 'Refund processed'}
    
    def initiate_refund(self, payment: Payment, amount: Decimal, reason: str) -> dict:
        """Initiate refund with Paystack"""
        try:
            url = f"{self.base_url}/refund"
            
            payload = {
                "transaction": payment.gateway_reference,
                "amount": self._convert_to_kobo(amount),
                "currency": payment.currency,
                "customer_note": reason,
                "merchant_note": f"Refund for course: {payment.course.title}"
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status'):
                return {
                    'success': True,
                    'data': result['data'],
                    'message': 'Refund initiated successfully'
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Refund initiation failed'),
                    'error': result
                }
                
        except Exception as e:
            logger.error(f"Refund initiation error: {str(e)}")
            return {
                'success': False,
                'message': 'Refund initiation failed',
                'error': str(e)
            }


class FlutterwaveService(BasePaymentService):
    """Flutterwave payment service"""
    
    def __init__(self):
        self.gateway = PaymentGateway.objects.filter(name='flutterwave', is_active=True).first()
        if not self.gateway:
            raise ValueError("Flutterwave gateway not configured")
        
        self.base_url = "https://api.flutterwave.com/v3"
        self.secret_key = self.gateway.secret_key
        self.public_key = self.gateway.public_key
    
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
    
    def initialize_payment(self, payment: Payment, callback_url: str) -> dict:
        """Initialize payment with Flutterwave"""
        try:
            url = f"{self.base_url}/payments"
            
            payload = {
                "tx_ref": payment.reference,
                "amount": str(payment.amount),
                "currency": payment.currency,
                "redirect_url": callback_url,
                "customer": {
                    "email": payment.customer_email,
                    "name": payment.customer_name,
                    "phonenumber": payment.customer_phone or ""
                },
                "customizations": {
                    "title": "NCLEX Virtual School",
                    "description": f"Payment for {payment.course.title}",
                    "logo": f"{settings.SITE_URL}/static/images/logo.png"
                },
                "meta": {
                    "user_id": str(payment.user.id),
                    "course_id": str(payment.course.id),
                    "payment_id": str(payment.id)
                }
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') == 'success':
                # Update payment with gateway reference
                payment.gateway_reference = result['data'].get('id', payment.reference)
                payment.gateway_response = result
                payment.save(update_fields=['gateway_reference', 'gateway_response'])
                
                return {
                    'success': True,
                    'data': result['data'],
                    'payment_url': result['data']['link'],
                    'reference': payment.reference
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Payment initialization failed'),
                    'error': result
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave API error: {str(e)}")
            return {
                'success': False,
                'message': 'Payment service temporarily unavailable',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Flutterwave initialization error: {str(e)}")
            return {
                'success': False,
                'message': 'Payment initialization failed',
                'error': str(e)
            }
    
    def verify_payment(self, reference: str) -> dict:
        """Verify payment with Flutterwave"""
        try:
            url = f"{self.base_url}/transactions/{reference}/verify"
            
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') == 'success':
                data = result['data']
                
                return {
                    'success': True,
                    'data': data,
                    'verified': True,
                    'amount': Decimal(str(data.get('amount', 0))),
                    'currency': data.get('currency'),
                    'status': data.get('status'),
                    'reference': data.get('tx_ref'),
                    'paid_at': data.get('created_at'),
                    'customer': data.get('customer', {}),
                    'card': data.get('card', {}),
                    'gateway_response': data.get('gateway_response'),
                }
            else:
                return {
                    'success': False,
                    'verified': False,
                    'message': result.get('message', 'Payment verification failed'),
                    'error': result
                }
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave verification error: {str(e)}")
            return {
                'success': False,
                'verified': False,
                'message': 'Payment verification failed',
                'error': str(e)
            }
        except Exception as e:
            logger.error(f"Flutterwave verification error: {str(e)}")
            return {
                'success': False,
                'verified': False,
                'message': 'Payment verification failed',
                'error': str(e)
            }
    
    def verify_webhook(self, payload: bytes, signature: str) -> bool:
        """Verify Flutterwave webhook signature"""
        try:
            computed_signature = hmac.new(
                self.gateway.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(computed_signature, signature)
        except Exception as e:
            logger.error(f"Flutterwave webhook signature verification error: {str(e)}")
            return False
    
    def process_webhook(self, payload: dict, headers: dict) -> dict:
        """Process Flutterwave webhook"""
        try:
            event_type = payload.get('event')
            data = payload.get('data', {})
            reference = data.get('tx_ref', '')
            
            # Log webhook
            webhook = PaymentWebhook.objects.create(
                gateway=self.gateway,
                event_type=event_type,
                reference=reference,
                payload=payload,
                headers=headers
            )
            
            result = {'success': False, 'message': 'Unknown event type'}
            
            if event_type == 'charge.completed':
                result = self._handle_charge_completed(data)
            elif event_type == 'charge.failed':
                result = self._handle_charge_failed(data)
            
            # Update webhook log
            webhook.success = result.get('success', False)
            webhook.processed = True
            webhook.processed_at = timezone.now()
            if not result.get('success'):
                webhook.error_message = result.get('message', '')
            webhook.save()
            
            return result
            
        except Exception as e:
            logger.error(f"Flutterwave webhook processing error: {str(e)}")
            return {
                'success': False,
                'message': f'Webhook processing failed: {str(e)}'
            }
    
    def _handle_charge_completed(self, data: dict) -> dict:
        """Handle completed charge webhook"""
        try:
            reference = data.get('tx_ref')
            if not reference:
                return {'success': False, 'message': 'No reference in webhook data'}
            
            payment = Payment.objects.filter(reference=reference).first()
            if not payment:
                return {'success': False, 'message': f'Payment not found: {reference}'}
            
            if payment.status == 'completed':
                return {'success': True, 'message': 'Payment already completed'}
            
            # Update payment
            payment.status = 'completed'
            payment.paid_at = timezone.now()
            payment.gateway_response = data
            payment.webhook_verified = True
            
            # Extract card info if available
            card_info = data.get('card', {})
            if card_info:
                payment.card_type = card_info.get('type', '')
                payment.last_4_digits = card_info.get('last_4digits', '')
                payment.exp_month = card_info.get('expiry_month', '')
                payment.exp_year = card_info.get('expiry_year', '')
            
            payment.payment_method = data.get('payment_type', '')
            
            # Calculate fees (Flutterwave charges are usually deducted from amount)
            app_fee = data.get('app_fee', 0)
            if app_fee:
                payment.gateway_fee = Decimal(str(app_fee))
                payment.net_amount = payment.amount - payment.gateway_fee
            
            payment.save()
            
            return {'success': True, 'message': 'Payment completed successfully'}
            
        except Exception as e:
            logger.error(f"Flutterwave charge completed handling error: {str(e)}")
            return {'success': False, 'message': f'Failed to process charge completion: {str(e)}'}
    
    def _handle_charge_failed(self, data: dict) -> dict:
        """Handle failed charge webhook"""
        try:
            reference = data.get('tx_ref')
            payment = Payment.objects.filter(reference=reference).first()
            
            if payment and payment.status != 'failed':
                payment.status = 'failed'
                payment.failed_at = timezone.now()
                payment.failure_reason = data.get('response_message', 'Payment failed')
                payment.gateway_response = data
                payment.webhook_verified = True
                payment.save()
            
            return {'success': True, 'message': 'Payment failure processed'}
            
        except Exception as e:
            logger.error(f"Flutterwave charge failed handling error: {str(e)}")
            return {'success': False, 'message': f'Failed to process charge failure: {str(e)}'}
    
    def initiate_refund(self, payment: Payment, amount: Decimal, reason: str) -> dict:
        """Initiate refund with Flutterwave"""
        try:
            url = f"{self.base_url}/transactions/{payment.gateway_reference}/refund"
            
            payload = {
                "amount": str(amount),
                "comments": reason
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'data': result['data'],
                    'message': 'Refund initiated successfully'
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Refund initiation failed'),
                    'error': result
                }
                
        except Exception as e:
            logger.error(f"Flutterwave refund initiation error: {str(e)}")
            return {
                'success': False,
                'message': 'Refund initiation failed',
                'error': str(e)
            }
        
class PayoutService:
    
    @staticmethod
    def calculate_instructor_earnings(instructor, start_date, end_date):
        """Calculate instructor earnings for a period"""
        
        # Get completed payments for instructor's courses in the period
        earnings = Payment.objects.filter(
            course__created_by=instructor,
            status='completed',
            paid_at__date__gte=start_date,
            paid_at__date__lte=end_date
        ).aggregate(
            total_revenue=Sum('amount'),
            total_fees=Sum('gateway_fee')
        )
        
        total_revenue = earnings['total_revenue'] or Decimal('0')
        total_fees = earnings['total_fees'] or Decimal('0')
        
        # Calculate splits (70% to instructor, 30% to platform)
        instructor_share = total_revenue * Decimal('0.70')
        platform_fee = total_revenue * Decimal('0.30')
        
        # Subtract gateway fees from instructor share
        net_instructor_share = instructor_share - total_fees
        
        return {
            'total_revenue': total_revenue,
            'instructor_share': instructor_share,
            'platform_fee': platform_fee,
            'gateway_fees': total_fees,
            'net_instructor_share': net_instructor_share,
            'payment_count': Payment.objects.filter(
                course__created_by=instructor,
                status='completed',
                paid_at__date__gte=start_date,
                paid_at__date__lte=end_date
            ).count()
        }
    
    @staticmethod
    def create_monthly_payouts():
        """Create monthly payouts for all instructors"""
        
        # Get last month's date range
        today = timezone.now().date()
        last_month = today.replace(day=1) - timedelta(days=1)
        period_start = last_month.replace(day=1)
        period_end = last_month
        
        # Get all instructors with earnings
        instructors_with_earnings = User.objects.filter(
            role='admin',
            is_active=True,
            created_courses__payments__status='completed',
            created_courses__payments__paid_at__date__gte=period_start,
            created_courses__payments__paid_at__date__lte=period_end
        ).distinct()
        
        created_payouts = []
        auto_processed = 0
        
        for instructor in instructors_with_earnings:
            # Check if payout already exists
            existing_payout = InstructorPayout.objects.filter(
                instructor=instructor,
                period_start=period_start,
                period_end=period_end
            ).first()
            
            if existing_payout:
                continue
            
            # Calculate earnings
            earnings = PayoutService.calculate_instructor_earnings(
                instructor, period_start, period_end
            )
            
            if earnings['net_instructor_share'] <= 0:
                continue
            
            # Create payout record
            payout = InstructorPayout.objects.create(
                instructor=instructor,
                period_start=period_start,
                period_end=period_end,
                total_revenue=earnings['total_revenue'],
                instructor_share=earnings['instructor_share'],
                platform_fee=earnings['platform_fee'],
                net_payout=earnings['net_instructor_share']
            )
            
            created_payouts.append(payout)
            logger.info(f"Created payout for {instructor.email}: {earnings['net_instructor_share']}")

            # AUTO-PROCESS if below threshold
            if payout.net_payout <= Decimal('10000.00'):  # 10k NGN
                result = PayoutService.process_payout(payout.id, auto_process=True)
                if result['success']:
                    auto_processed += 1

            logger.info(f"Created {len(created_payouts)} payouts, auto-processed {auto_processed}")
            return created_payouts
        
        return created_payouts
    
    @staticmethod
    def create_recipient_code(instructor_bank_account):
        """Create recipient code for transfers on payment gateways"""
        try:
            # For Paystack
            paystack_gateway = PaymentGateway.objects.filter(
                name='paystack', 
                is_active=True,
                supports_transfers=True
            ).first()
            
            if paystack_gateway:
                paystack_service = PaystackTransferService(paystack_gateway)
                recipient_result = paystack_service.create_transfer_recipient(instructor_bank_account)
                
                if recipient_result['success']:
                    instructor_bank_account.paystack_recipient_code = recipient_result['recipient_code']
                    instructor_bank_account.save()
            
            # For Flutterwave
            flutterwave_gateway = PaymentGateway.objects.filter(
                name='flutterwave', 
                is_active=True,
                supports_transfers=True
            ).first()
            
            if flutterwave_gateway:
                flutterwave_service = FlutterwaveTransferService(flutterwave_gateway)
                recipient_result = flutterwave_service.create_transfer_recipient(instructor_bank_account)
                
                if recipient_result['success']:
                    instructor_bank_account.flutterwave_recipient_id = recipient_result['recipient_id']
                    instructor_bank_account.save()
            
            return {'success': True, 'message': 'Recipient codes created successfully'}
            
        except Exception as e:
            logger.error(f"Create recipient code error: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    @staticmethod
    def process_payout(payout_id, auto_process=False):
        """Updated process_payout with actual bank transfer"""
        try:
            payout = InstructorPayout.objects.get(id=payout_id)

            # Auto-processing limits
            if auto_process:
                MAX_AUTO_AMOUNT = Decimal('10000.00')  # 10k NGN max
                if payout.net_payout > MAX_AUTO_AMOUNT:
                    return {'success': False, 'message': 'Amount exceeds auto-processing limit'}
            
            if payout.status != 'pending':
                return {'success': False, 'message': 'Payout already processed'}
            
            if not payout.is_eligible_for_payout():
                return {'success': False, 'message': f'Payout below minimum threshold'}
            
            # Get instructor bank account
            try:
                bank_account = payout.instructor.bank_account
            except InstructorBankAccount.DoesNotExist:
                return {'success': False, 'message': 'No bank account configured for instructor'}
            
            if not bank_account.is_verified:
                return {'success': False, 'message': 'Bank account not verified'}
            
            # Mark as processing
            payout.status = 'processing'
            payout.processed_at = timezone.now()
            payout.save()
            
            # Try Paystack first, then Flutterwave
            transfer_result = PayoutService._execute_bank_transfer(payout, bank_account)
            
            if transfer_result['success']:
                payout.status = 'completed'
                payout.gateway_reference = transfer_result.get('reference', '')
                payout.gateway_response = transfer_result
                payout.save()
                
                # Send notification
                from courses.instructor_views import AdminEmailService
                AdminEmailService.send_instructor_payout_notification(
                    payout.instructor, 
                    payout.net_payout, 
                    f"{payout.period_start} to {payout.period_end}"
                )

                # Send notification
                from backend.utils.auth import EmailService
                EmailService.send_payout_completed_notification(payout)
                
                return {'success': True, 'message': 'Payout completed successfully'}
            else:
                payout.status = 'failed'
                payout.gateway_response = transfer_result
                payout.save()
                
                return {'success': False, 'message': transfer_result.get('message', 'Transfer failed')}
                
        except InstructorPayout.DoesNotExist:
            return {'success': False, 'message': 'Payout not found'}
        except Exception as e:
            logger.error(f"Payout processing error: {str(e)}")
            return {'success': False, 'message': f'Processing error: {str(e)}'}
    
    @staticmethod
    def _execute_bank_transfer(payout, bank_account):
        """Execute actual bank transfer using available payment gateway"""
        
        # Try Paystack first
        if bank_account.paystack_recipient_code:
            paystack_gateway = PaymentGateway.objects.filter(
                name='paystack', 
                is_active=True,
                supports_transfers=True
            ).first()
            
            if paystack_gateway:
                transfer_service = PaystackTransferService(paystack_gateway)
                result = transfer_service.initiate_transfer(
                    recipient_code=bank_account.paystack_recipient_code,
                    amount=payout.net_payout,
                    reason=f"Course earnings payout for {payout.period_start} to {payout.period_end}"
                )
                
                if result['success']:
                    return result
        
        # Try Flutterwave if Paystack fails
        if bank_account.flutterwave_recipient_id:
            flutterwave_gateway = PaymentGateway.objects.filter(
                name='flutterwave', 
                is_active=True,
                supports_transfers=True
            ).first()
            
            if flutterwave_gateway:
                transfer_service = FlutterwaveTransferService(flutterwave_gateway)
                result = transfer_service.initiate_transfer(
                    recipient_id=bank_account.flutterwave_recipient_id,
                    amount=payout.net_payout,
                    narration=f"Course earnings payout"
                )
                
                if result['success']:
                    return result
        
        return {'success': False, 'message': 'No valid transfer method available'}
    
    
# Transfer Services for actual bank transfers
class PaystackTransferService:
    """Handle Paystack bank transfers"""
    
    def __init__(self, gateway):
        self.gateway = gateway
        self.secret_key = gateway.transfer_secret_key or gateway.secret_key
        self.base_url = "https://api.paystack.co"
    
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
    
    def create_transfer_recipient(self, bank_account):
        """Create transfer recipient on Paystack"""
        try:
            url = f"{self.base_url}/transferrecipient"
            
            payload = {
                "type": "nuban",
                "name": bank_account.account_name,
                "account_number": bank_account.account_number,
                "bank_code": bank_account.bank_code,
                "currency": "NGN"
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status'):
                return {
                    'success': True,
                    'recipient_code': result['data']['recipient_code'],
                    'data': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to create recipient')
                }
                
        except Exception as e:
            logger.error(f"Paystack create recipient error: {str(e)}")
            return {'success': False, 'message': str(e)}
    
    def initiate_transfer(self, recipient_code, amount, reason):
        """Initiate bank transfer on Paystack"""
        try:
            url = f"{self.base_url}/transfer"
            
            # Convert to kobo
            amount_kobo = int(float(amount) * 100)
            
            payload = {
                "source": "balance",
                "reason": reason,
                "amount": amount_kobo,
                "recipient": recipient_code,
                "reference": f"payout_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{recipient_code[-6:]}"
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status'):
                return {
                    'success': True,
                    'reference': result['data']['reference'],
                    'transfer_code': result['data']['transfer_code'],
                    'data': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Transfer initiation failed')
                }
                
        except Exception as e:
            logger.error(f"Paystack transfer error: {str(e)}")
            return {'success': False, 'message': str(e)}
        

class FlutterwaveTransferService:
    """Handle Flutterwave bank transfers"""
    
    def __init__(self, gateway):
        self.gateway = gateway
        self.secret_key = gateway.transfer_secret_key or gateway.secret_key
        self.base_url = "https://api.flutterwave.com/v3"
    
    def _get_headers(self):
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }
    
    def create_transfer_recipient(self, bank_account):
        """Create transfer recipient on Flutterwave"""
        # Flutterwave doesn't require pre-creating recipients
        # We can transfer directly to bank account
        return {
            'success': True,
            'recipient_id': f"flw_{bank_account.account_number}_{bank_account.bank_code}",
            'message': 'Recipient ready for transfer'
        }
    
    def initiate_transfer(self, recipient_id, amount, narration):
        """Initiate bank transfer on Flutterwave"""
        try:
            url = f"{self.base_url}/transfers"
            
            # Extract account details from recipient_id
            _, account_number, bank_code = recipient_id.split('_')
            
            payload = {
                "account_bank": bank_code,
                "account_number": account_number,
                "amount": float(amount),
                "narration": narration,
                "currency": "NGN",
                "reference": f"flw_payout_{timezone.now().strftime('%Y%m%d_%H%M%S')}",
                "callback_url": f"{settings.SITE_URL}/api/payments/webhooks/flutterwave/",
                "debit_currency": "NGN"
            }
            
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
            response.raise_for_status()
            
            result = response.json()
            
            if result.get('status') == 'success':
                return {
                    'success': True,
                    'reference': result['data']['reference'],
                    'id': result['data']['id'],
                    'data': result['data']
                }
            else:
                return {
                    'success': False,
                    'message': result.get('message', 'Transfer initiation failed')
                }
                
        except Exception as e:
            logger.error(f"Flutterwave transfer error: {str(e)}")
            return {'success': False, 'message': str(e)}


class BankVerificationService:
    
    @staticmethod
    def verify_bank_account(bank_account):
        """
        Verify bank account with multiple providers
        Returns: {'success': bool, 'account_name': str, 'message': str}
        """
        # Try Paystack first, then fallback to Flutterwave
        paystack_result = BankVerificationService._verify_with_paystack(bank_account)
        
        if paystack_result['success']:
            return paystack_result
        
        # Fallback to Flutterwave
        logger.info(f"Paystack verification failed, trying Flutterwave for {bank_account.account_number}")
        return BankVerificationService._verify_with_flutterwave(bank_account)
    
    @staticmethod
    def _verify_with_paystack(bank_account):
        """Verify bank account using Paystack"""
        try:
            url = "https://api.paystack.co/bank/resolve"
            headers = {
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json"
            }
            
            params = {
                "account_number": bank_account.account_number,
                "bank_code": bank_account.bank_code
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                if data.get('status') and data.get('data'):
                    account_name = data['data'].get('account_name', '').strip()
                    
                    # Check if account name matches (fuzzy matching)
                    if BankVerificationService._names_match(account_name, bank_account.account_name):
                        return {
                            'success': True,
                            'account_name': account_name,
                            'message': 'Bank account verified successfully',
                            'provider': 'paystack'
                        }
                    else:
                        return {
                            'success': False,
                            'account_name': account_name,
                            'message': f'Account name mismatch. Bank: "{account_name}", Provided: "{bank_account.account_name}"',
                            'provider': 'paystack'
                        }
                else:
                    return {
                        'success': False,
                        'message': data.get('message', 'Bank account verification failed'),
                        'provider': 'paystack'
                    }
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                return {
                    'success': False,
                    'message': error_data.get('message', f'Verification failed with status {response.status_code}'),
                    'provider': 'paystack'
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'message': 'Bank verification timeout. Please try again.',
                'provider': 'paystack'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Paystack bank verification error: {str(e)}")
            return {
                'success': False,
                'message': 'Network error during verification. Please try again.',
                'provider': 'paystack'
            }
        except Exception as e:
            logger.error(f"Paystack bank verification unexpected error: {str(e)}")
            return {
                'success': False,
                'message': 'Verification service temporarily unavailable.',
                'provider': 'paystack'
            }
    
    @staticmethod
    def _verify_with_flutterwave(bank_account):
        """Verify bank account using Flutterwave"""
        try:
            url = "https://api.flutterwave.com/v3/accounts/resolve"
            headers = {
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                "Content-Type": "application/json"
            }
            
            data = {
                "account_number": bank_account.account_number,
                "account_bank": bank_account.bank_code
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                
                if response_data.get('status') == 'success' and response_data.get('data'):
                    account_name = response_data['data'].get('account_name', '').strip()
                    
                    # Check if account name matches
                    if BankVerificationService._names_match(account_name, bank_account.account_name):
                        return {
                            'success': True,
                            'account_name': account_name,
                            'message': 'Bank account verified successfully',
                            'provider': 'flutterwave'
                        }
                    else:
                        return {
                            'success': False,
                            'account_name': account_name,
                            'message': f'Account name mismatch. Bank: "{account_name}", Provided: "{bank_account.account_name}"',
                            'provider': 'flutterwave'
                        }
                else:
                    return {
                        'success': False,
                        'message': response_data.get('message', 'Bank account verification failed'),
                        'provider': 'flutterwave'
                    }
            else:
                error_data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
                return {
                    'success': False,
                    'message': error_data.get('message', f'Verification failed with status {response.status_code}'),
                    'provider': 'flutterwave'
                }
                
        except requests.exceptions.Timeout:
            return {
                'success': False,
                'message': 'Bank verification timeout. Please try again.',
                'provider': 'flutterwave'
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Flutterwave bank verification error: {str(e)}")
            return {
                'success': False,
                'message': 'Network error during verification. Please try again.',
                'provider': 'flutterwave'
            }
        except Exception as e:
            logger.error(f"Flutterwave bank verification unexpected error: {str(e)}")
            return {
                'success': False,
                'message': 'Verification service temporarily unavailable.',
                'provider': 'flutterwave'
            }
    
    @staticmethod
    def _names_match(bank_name, provided_name, threshold=0.8):
        """
        Compare two names with fuzzy matching
        Returns True if names are similar enough
        """
        import difflib
        
        # Normalize names
        bank_name = bank_name.upper().strip()
        provided_name = provided_name.upper().strip()
        
        # Direct match
        if bank_name == provided_name:
            return True
        
        # Remove common prefixes/suffixes and special characters
        def normalize_name(name):
            # Remove common titles and suffixes
            prefixes = ['MR', 'MRS', 'MISS', 'DR', 'PROF', 'ENGR']
            suffixes = ['JR', 'SR', 'II', 'III']
            
            words = name.replace('.', '').replace(',', '').split()
            words = [w for w in words if w not in prefixes + suffixes]
            
            return ' '.join(words)
        
        normalized_bank = normalize_name(bank_name)
        normalized_provided = normalize_name(provided_name)
        
        # Calculate similarity ratio
        similarity = difflib.SequenceMatcher(None, normalized_bank, normalized_provided).ratio()
        
        return similarity >= threshold
    
    @staticmethod
    def get_bank_list():
        """Get list of supported banks from Paystack"""
        try:
            url = "https://api.paystack.co/bank"
            headers = {
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json"
            }
            
            response = requests.get(url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') and data.get('data'):
                    banks = []
                    for bank in data['data']:
                        banks.append({
                            'name': bank.get('name'),
                            'code': bank.get('code'),
                            'slug': bank.get('slug')
                        })
                    return {
                        'success': True,
                        'banks': banks
                    }
            
            return {
                'success': False,
                'message': 'Failed to fetch bank list'
            }
            
        except Exception as e:
            logger.error(f"Get bank list error: {str(e)}")
            return {
                'success': False,
                'message': 'Failed to fetch bank list'
            }