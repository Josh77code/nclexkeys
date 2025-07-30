# payments/webhook_views.py
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
import json
import logging

from .services import PaymentServiceFactory
from .models import Payment, PaymentWebhook
from courses.models import CourseEnrollment, UserCourseProgress
from utils.auth import EmailService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook(request):
    """
    Handle Paystack webhook notifications
    POST /api/webhooks/paystack/
    """
    try:
        # Get the signature from headers
        signature = request.headers.get('X-Paystack-Signature', '')
        
        if not signature:
            logger.warning("Paystack webhook: Missing signature")
            return HttpResponse("Missing signature", status=400)
        
        # Get raw payload
        payload = request.body
        
        # Verify webhook signature
        try:
            paystack_service = PaymentServiceFactory.get_service('paystack')
            is_valid = paystack_service.verify_webhook(payload, signature)
            
            if not is_valid:
                logger.warning("Paystack webhook: Invalid signature")
                return HttpResponse("Invalid signature", status=400)
                
        except Exception as e:
            logger.error(f"Paystack webhook signature verification error: {str(e)}")
            return HttpResponse("Signature verification failed", status=400)
        
        # Parse JSON payload
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Paystack webhook: Invalid JSON payload: {str(e)}")
            return HttpResponse("Invalid JSON", status=400)
        
        # Process webhook
        result = paystack_service.process_webhook(
            webhook_data, 
            dict(request.headers)
        )
        
        if result['success']:
            logger.info(f"Paystack webhook processed successfully: {webhook_data.get('event')}")
            
            # Handle specific events that require additional actions
            event_type = webhook_data.get('event')
            if event_type == 'charge.success':
                handle_successful_payment(webhook_data.get('data', {}))
            
            return HttpResponse("OK", status=200)
        else:
            logger.error(f"Paystack webhook processing failed: {result['message']}")
            return HttpResponse("Processing failed", status=400)
            
    except Exception as e:
        logger.error(f"Paystack webhook error: {str(e)}")
        return HttpResponse("Internal server error", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def flutterwave_webhook(request):
    """
    Handle Flutterwave webhook notifications
    POST /api/webhooks/flutterwave/
    """
    try:
        # Get the signature from headers
        signature = request.headers.get('verif-hash', '')
        
        if not signature:
            logger.warning("Flutterwave webhook: Missing signature")
            return HttpResponse("Missing signature", status=400)
        
        # Get raw payload
        payload = request.body
        
        # Verify webhook signature
        try:
            flutterwave_service = PaymentServiceFactory.get_service('flutterwave')
            is_valid = flutterwave_service.verify_webhook(payload, signature)
            
            if not is_valid:
                logger.warning("Flutterwave webhook: Invalid signature")
                return HttpResponse("Invalid signature", status=400)
                
        except Exception as e:
            logger.error(f"Flutterwave webhook signature verification error: {str(e)}")
            return HttpResponse("Signature verification failed", status=400)
        
        # Parse JSON payload
        try:
            webhook_data = json.loads(payload.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Flutterwave webhook: Invalid JSON payload: {str(e)}")
            return HttpResponse("Invalid JSON", status=400)
        
        # Process webhook
        result = flutterwave_service.process_webhook(
            webhook_data, 
            dict(request.headers)
        )
        
        if result['success']:
            logger.info(f"Flutterwave webhook processed successfully: {webhook_data.get('event')}")
            
            # Handle specific events that require additional actions
            event_type = webhook_data.get('event')
            if event_type == 'charge.completed':
                handle_successful_payment(webhook_data.get('data', {}))
            
            return HttpResponse("OK", status=200)
        else:
            logger.error(f"Flutterwave webhook processing failed: {result['message']}")
            return HttpResponse("Processing failed", status=400)
            
    except Exception as e:
        logger.error(f"Flutterwave webhook error: {str(e)}")
        return HttpResponse("Internal server error", status=500)


def handle_successful_payment(payment_data):
    """
    Handle successful payment webhook - complete enrollment process
    """
    try:
        # Extract reference based on gateway
        reference = payment_data.get('reference') or payment_data.get('tx_ref')
        
        if not reference:
            logger.error("No payment reference found in webhook data")
            return
        
        # Get payment and enrollment
        try:
            payment = Payment.objects.get(reference=reference)
            enrollment = CourseEnrollment.objects.get(
                payment_id=reference,
                payment_status='pending'
            )
        except (Payment.DoesNotExist, CourseEnrollment.DoesNotExist) as e:
            logger.error(f"Payment or enrollment not found for reference {reference}: {str(e)}")
            return
        
        # Check if already processed
        if payment.status == 'completed':
            logger.info(f"Payment {reference} already completed")
            return
        
        # Complete the enrollment process
        with transaction.atomic():
            # Update payment status
            payment.status = 'completed'
            payment.paid_at = timezone.now()
            payment.webhook_verified = True
            payment.save()
            
            # Update enrollment status
            enrollment.payment_status = 'completed'
            enrollment.save(update_fields=['payment_status'])
            
            # Create or update course progress
            progress, created = UserCourseProgress.objects.get_or_create(
                user=enrollment.user,
                course=enrollment.course,
                defaults={'progress_percentage': 0}
            )
            
            if created:
                logger.info(f"Course progress created for {enrollment.user.email} -> {enrollment.course.title}")

            # Send notification to instructor about new sale
            from backend.utils.auth import EmailService
            try:
                EmailService.send_instructor_sale_notification(
                    payment.course.created_by, 
                    payment
                )
            except Exception as e:
                logger.warning(f"Failed to send instructor notification: {str(e)}")
        
            
            # Send enrollment confirmation email
            try:
                EmailService.send_enrollment_confirmation(
                    enrollment.user,
                    enrollment.course,
                    enrollment
                )
                logger.info(f"Enrollment confirmation sent to {enrollment.user.email}")
            except Exception as email_error:
                logger.error(f"Failed to send enrollment confirmation: {str(email_error)}")
            
            logger.info(f"Webhook payment completed: {enrollment.user.email} -> {enrollment.course.title}")
            
    except Exception as e:
        logger.error(f"Error handling successful payment webhook: {str(e)}")


@api_view(['GET'])
@permission_classes([AllowAny])
def webhook_test(request):
    """
    Test endpoint to verify webhook setup
    GET /api/webhooks/test/
    """
    return Response({
        'message': 'Webhook endpoints are working',
        'endpoints': {
            'paystack': '/api/webhooks/paystack/',
            'flutterwave': '/api/webhooks/flutterwave/',
        }
    }, status=status.HTTP_200_OK)