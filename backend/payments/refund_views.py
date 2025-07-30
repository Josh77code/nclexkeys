# payments/refund_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
import logging

from .models import Payment, PaymentRefund
from .services import PaymentServiceFactory
from courses.models import CourseEnrollment, UserCourseProgress
from utils.auth import EmailService
from .serializers import RefundSerializer

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def request_refund(request, payment_id):
    """
    Request a refund for a payment - STUDENTS ONLY
    POST /api/payments/{payment_id}/refund/
    """
    # Students (users) can request refunds
    if request.user.role not in ['user']:
        return Response({'detail': 'Only students can request refunds'}, status=403)
    
    try:
        # Get the payment
        payment = Payment.objects.get(
            id=payment_id,
            user=request.user,
            status='completed'
        )
        
        # Check if payment is eligible for refund
        if not payment.is_refundable():
            return Response(
                {'detail': 'This payment is not eligible for refund.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if refund already exists
        existing_refund = PaymentRefund.objects.filter(
            payment=payment,
            status__in=['pending', 'processing', 'completed']
        ).first()
        
        if existing_refund:
            return Response(
                {'detail': 'A refund request already exists for this payment.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get refund details from request
        reason = request.data.get('reason', '').strip()
        refund_amount = request.data.get('amount')
        
        if not reason:
            return Response(
                {'detail': 'Refund reason is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate refund amount
        if refund_amount:
            try:
                refund_amount = Decimal(str(refund_amount))
                if refund_amount <= 0 or refund_amount > payment.amount:
                    return Response(
                        {'detail': 'Invalid refund amount.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            except (ValueError, TypeError):
                return Response(
                    {'detail': 'Invalid refund amount format.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            # Full refund if no amount specified
            refund_amount = payment.amount
        
        # Create refund request
        with transaction.atomic():
            refund = PaymentRefund.objects.create(
                payment=payment,
                user=request.user,
                amount=refund_amount,
                reason=reason,
                status='pending',
                requested_at=timezone.now()
            )
            
            # Process refund automatically or mark for manual review
            auto_process = payment.amount <= Decimal('50000.00')  # Auto-process refunds <= 50k NGN
            
            if auto_process:
                # Process refund immediately
                result = process_refund_internal(refund)
                if not result['success']:
                    refund.status = 'failed'
                    refund.failure_reason = result['message']
                    refund.save()
                    
                    return Response(
                        {'detail': f'Refund processing failed: {result["message"]}'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                # Mark for manual review by platform managers
                refund.status = 'pending_review'
                refund.save()
                
                # Send notification to platform managers (super_admins)
                EmailService.send_refund_review_notification(refund)
            
            # Send confirmation to user
            EmailService.send_refund_request_confirmation(request.user, refund)
            
            logger.info(f"Refund request created: {request.user.email} -> {payment.reference} (Amount: {refund_amount})")
            
            return Response({
                'message': 'Refund request submitted successfully.',
                'refund': RefundSerializer(refund).data,
                'auto_processed': auto_process and refund.status != 'failed'
            }, status=status.HTTP_201_CREATED)
    
    except Payment.DoesNotExist:
        return Response(
            {'detail': 'Payment not found or not accessible.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Refund request error: {str(e)}")
        return Response(
            {'detail': 'Failed to process refund request.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_refund(request, refund_id):
    """
    Process a refund - PLATFORM MANAGERS ONLY (super_admin)
    POST /api/refunds/{refund_id}/process/
    """
    # Only platform managers (super_admin) can process refunds
    if request.user.role != 'super_admin':
        return Response(
            {'detail': 'Platform manager access required.'},
            status=status.HTTP_403_FORBIDDEN
        )
    
    try:
        refund = PaymentRefund.objects.get(id=refund_id)
        
        if refund.status not in ['pending', 'pending_review']:
            return Response(
                {'detail': 'Refund is not in a processable state.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Process the refund
        result = process_refund_internal(refund)
        
        if result['success']:
            return Response({
                'message': 'Refund processed successfully.',
                'refund': RefundSerializer(refund).data
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'detail': f'Refund processing failed: {result["message"]}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    except PaymentRefund.DoesNotExist:
        return Response(
            {'detail': 'Refund not found.'},
            status=status.HTTP_404_NOT_FOUND
        )
    except Exception as e:
        logger.error(f"Process refund error: {str(e)}")
        return Response(
            {'detail': 'Failed to process refund.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_refunds(request):
    """
    Get user's refund requests - STUDENTS ONLY
    GET /api/payments/my-refunds/
    """
    # Only students can view their refunds
    if request.user.role != 'user':
        return Response({'detail': 'Student access required'}, status=403)
    
    try:
        refunds = PaymentRefund.objects.filter(user=request.user).order_by('-requested_at')
        
        # Pagination
        from django.core.paginator import Paginator
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 10))
        
        paginator = Paginator(refunds, per_page)
        page_obj = paginator.get_page(page)
        
        serializer = RefundSerializer(page_obj.object_list, many=True)
        
        return Response({
            'refunds': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_refunds': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        }, status=status.HTTP_200_OK)
    
    except Exception as e:
        logger.error(f"My refunds error: {str(e)}")
        return Response(
            {'detail': 'Failed to fetch refunds.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_refunds(request):
    """
    Get all pending refunds - PLATFORM MANAGERS ONLY (super_admin)
    GET /api/refunds/pending/
    """
    # Only platform managers can view all pending refunds
    if request.user.role != 'super_admin':
        return Response({'detail': 'Platform manager access required'}, status=403)
    
    try:
        from django.core.paginator import Paginator
        
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        refunds = PaymentRefund.objects.filter(
            status__in=['pending', 'pending_review']
        ).select_related('payment', 'user', 'payment__course').order_by('-requested_at')
        
        paginator = Paginator(refunds, per_page)
        page_obj = paginator.get_page(page)
        
        refunds_data = []
        for refund in page_obj.object_list:
            refunds_data.append({
                'id': str(refund.id),
                'student_name': refund.user.full_name,
                'student_email': refund.user.email,
                'course_title': refund.payment.course.title,
                'amount': float(refund.amount),
                'reason': refund.reason,
                'requested_at': refund.requested_at,
                'status': refund.status,
                'payment_reference': refund.payment.reference
            })
        
        return Response({
            'pending_refunds': refunds_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_refunds': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Pending refunds error: {str(e)}")
        return Response({'detail': 'Failed to fetch pending refunds'}, status=500)


def process_refund_internal(refund):
    """
    Internal function to process refund with payment gateway
    """
    try:
        payment = refund.payment
        
        # Update refund status
        refund.status = 'processing'
        refund.processed_at = timezone.now()
        refund.save()
        
        # Get payment service
        payment_service = PaymentServiceFactory.get_service(payment.gateway_name)
        
        # Initiate refund with gateway
        result = payment_service.initiate_refund(
            payment=payment,
            amount=refund.amount,
            reason=refund.reason
        )
        
        if result['success']:
            # Update refund status
            refund.status = 'completed'
            refund.gateway_response = result.get('data', {})
            refund.gateway_reference = result.get('data', {}).get('id', '')
            refund.completed_at = timezone.now()
            refund.save()
            
            # Handle enrollment cancellation if full refund
            if refund.amount >= payment.amount:
                handle_enrollment_cancellation(payment)
            
            # Send completion notification
            EmailService.send_refund_completed_notification(refund.user, refund)
            
            logger.info(f"Refund completed: {refund.user.email} -> {payment.reference} (Amount: {refund.amount})")
            
            return {'success': True, 'message': 'Refund completed successfully'}
        
        else:
            # Update refund status
            refund.status = 'failed'
            refund.failure_reason = result.get('message', 'Gateway error')
            refund.gateway_response = result.get('error', {})
            refund.save()
            
            return {'success': False, 'message': result.get('message', 'Refund failed')}
    
    except Exception as e:
        # Update refund status
        refund.status = 'failed'
        refund.failure_reason = str(e)
        refund.save()
        
        logger.error(f"Refund processing error: {str(e)}")
        return {'success': False, 'message': f'Processing error: {str(e)}'}


def handle_enrollment_cancellation(payment):
    """
    Handle enrollment cancellation for full refunds
    """
    try:
        # Get enrollment
        enrollment = CourseEnrollment.objects.get(
            payment_id=payment.reference,
            payment_status='completed'
        )
        
        # Check if significant progress has been made
        try:
            progress = UserCourseProgress.objects.get(
                user=enrollment.user,
                course=enrollment.course
            )
            
            # If user has made significant progress, don't cancel enrollment
            # Just mark as refunded but keep access
            if progress.progress_percentage > 20:  # More than 20% progress
                enrollment.payment_status = 'refunded_with_access'
                enrollment.save()
                logger.info(f"Enrollment kept due to progress: {enrollment.user.email} -> {enrollment.course.title}")
                return
        
        except UserCourseProgress.DoesNotExist:
            pass
        
        # Cancel enrollment
        with transaction.atomic():
            enrollment.is_active = False
            enrollment.payment_status = 'refunded'
            enrollment.cancelled_at = timezone.now()
            enrollment.save()
            
            # Archive progress instead of deleting
            if hasattr(enrollment, 'user_progress'):
                progress = enrollment.user_progress.first()
                if progress:
                    progress.is_active = False
                    progress.save()
        
        logger.info(f"Enrollment cancelled: {enrollment.user.email} -> {enrollment.course.title}")
        
    except CourseEnrollment.DoesNotExist:
        logger.warning(f"No enrollment found for payment: {payment.reference}")
    except Exception as e:
        logger.error(f"Enrollment cancellation error: {str(e)}")