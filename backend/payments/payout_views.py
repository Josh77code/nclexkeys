# payments/payout_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.core.paginator import Paginator
from django.db.models import Sum
from datetime import datetime, timedelta
from django.utils import timezone
from .services import PayoutService
import logging
from .models import InstructorPayout

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def instructor_earnings(request):
    """Get instructor's earnings summary"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    try:
        # Get date range
        days = int(request.GET.get('days', 30))
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days)
        
        # Calculate earnings
        earnings = PayoutService.calculate_instructor_earnings(
            request.user, start_date, end_date
        )
        
        # Get payout history
        payouts = InstructorPayout.objects.filter(
            instructor=request.user
        ).order_by('-created_at')[:5]
        
        payout_data = []
        for payout in payouts:
            payout_data.append({
                'id': str(payout.id),
                'period': f"{payout.period_start} to {payout.period_end}",
                'net_payout': float(payout.net_payout),
                'status': payout.status,
                'processed_at': payout.processed_at
            })
        
        return Response({
            'current_period_earnings': {
                'total_revenue': float(earnings['total_revenue']),
                'your_share': float(earnings['net_instructor_share']),
                'platform_fee': float(earnings['platform_fee']),
                'gateway_fees': float(earnings['gateway_fees']),
                'payment_count': earnings['payment_count']
            },
            'recent_payouts': payout_data,
            'payout_schedule': 'Monthly payouts on the 5th of each month',
            'minimum_payout': '1,000 NGN'
        })
        
    except Exception as e:
        logger.error(f"Instructor earnings error: {str(e)}")
        return Response({'detail': 'Failed to fetch earnings'}, status=500)