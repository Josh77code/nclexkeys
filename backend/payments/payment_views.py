# payments/views.py - Core payment views that are missing
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.paginator import Paginator
from .models import Payment, PaymentRefund
from .serializers import PaymentSerializer
import logging

logger = logging.getLogger(__name__)

# Create your views here.
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_history(request):
    """
    Get user's payment history - STUDENTS ONLY
    GET /api/payments/transactions/
    """
    if request.user.role != 'user':
        return Response({'detail': 'Student access required'}, status=403)
    
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        status_filter = request.GET.get('status', '')
        
        payments = Payment.objects.filter(user=request.user).select_related('course')
        
        if status_filter:
            payments = payments.filter(status=status_filter)
        
        payments = payments.order_by('-created_at')
        
        paginator = Paginator(payments, per_page)
        page_obj = paginator.get_page(page)
        
        serializer = PaymentSerializer(page_obj.object_list, many=True)
        
        return Response({
            'payments': serializer.data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_payments': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Payment history error: {str(e)}")
        return Response({'detail': 'Failed to fetch payment history'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payment_detail(request, payment_id):
    """
    Get payment details - STUDENTS can view their own, SUPER_ADMIN can view all
    GET /api/payments/transactions/{payment_id}/
    """
    try:
        if request.user.role == 'user':
            # Students can only view their own payments
            payment = Payment.objects.select_related('course').get(
                id=payment_id,
                user=request.user
            )
        elif request.user.role == 'super_admin':
            # Platform managers can view any payment
            payment = Payment.objects.select_related('course', 'user').get(id=payment_id)
        else:
            return Response({'detail': 'Access denied'}, status=403)
        
        serializer = PaymentSerializer(payment)
        
        return Response({
            'payment': serializer.data
        })
        
    except Payment.DoesNotExist:
        return Response({'detail': 'Payment not found'}, status=404)
    except Exception as e:
        logger.error(f"Payment detail error: {str(e)}")
        return Response({'detail': 'Failed to fetch payment details'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def admin_payment_overview(request):
    """
    Platform manager payment overview - SUPER_ADMIN ONLY
    GET /api/payments/admin/overview/
    """
    if request.user.role != 'super_admin':
        return Response({'detail': 'Platform manager access required'}, status=403)
    
    try:
        from django.db.models import Count, Sum
        from datetime import datetime, timedelta
        from django.utils import timezone
        
        # Get overview stats
        today = timezone.now().date()
        last_30_days = today - timedelta(days=30)
        
        stats = {
            'total_payments': Payment.objects.count(),
            'completed_payments': Payment.objects.filter(status='completed').count(),
            'failed_payments': Payment.objects.filter(status='failed').count(),
            'pending_payments': Payment.objects.filter(status='pending').count(),
            'total_revenue': Payment.objects.filter(status='completed').aggregate(
                total=Sum('amount')
            )['total'] or 0,
            'last_30_days_revenue': Payment.objects.filter(
                status='completed',
                paid_at__date__gte=last_30_days
            ).aggregate(total=Sum('amount'))['total'] or 0,
            'pending_refunds': PaymentRefund.objects.filter(
                status__in=['pending', 'pending_review']
            ).count()
        }
        
        # Recent payments
        recent_payments = Payment.objects.select_related(
            'user', 'course'
        ).order_by('-created_at')[:10]
        
        return Response({
            'stats': stats,
            'recent_payments': PaymentSerializer(recent_payments, many=True).data
        })
        
    except Exception as e:
        logger.error(f"Admin payment overview error: {str(e)}")
        return Response({'detail': 'Failed to fetch payment overview'}, status=500)