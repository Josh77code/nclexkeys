# payments/bank_views.py
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.db import transaction
from .models import InstructorBankAccount, InstructorPayout
from .services import PayoutService, BankVerificationService
from django.db.models import Sum
from django.utils import timezone
import logging

logger = logging.getLogger(__name__)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_banks(request):
    """Get list of supported banks"""
    try:
        result = BankVerificationService.get_bank_list()
        
        if result['success']:
            return Response({
                'banks': result['banks']
            })
        else:
            return Response({
                'detail': result['message']
            }, status=500)
            
    except Exception as e:
        logger.error(f"Get banks error: {str(e)}")
        return Response({'detail': 'Failed to fetch banks'}, status=500)
    

@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def instructor_bank_account(request):
    """Get or create instructor bank account"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    if request.method == 'GET':
        try:
            bank_account = request.user.bank_account
            return Response({
                'bank_name': bank_account.bank_name,
                'account_number': bank_account.account_number,
                'account_name': bank_account.account_name,
                'bank_code': bank_account.bank_code,
                'is_verified': bank_account.is_verified,
                'verified_at': bank_account.verified_at,
                'auto_payout_enabled': bank_account.auto_payout_enabled,
                'verification_attempts': bank_account.verification_attempts,
                'last_verification_attempt': bank_account.last_verification_attempt,
                'verification_error': bank_account.verification_error
            })
        except InstructorBankAccount.DoesNotExist:
            return Response({'message': 'No bank account configured'}, status=404)
    
    elif request.method == 'POST':
        # Validate required fields
        required_fields = ['bank_name', 'account_number', 'account_name', 'bank_code']
        for field in required_fields:
            if not request.data.get(field):
                return Response({
                    'detail': f'{field.replace("_", " ").title()} is required'
                }, status=400)
        
        # Validate account number length (Nigerian banks typically use 10 digits)
        account_number = request.data['account_number'].strip()
        if not account_number.isdigit() or len(account_number) != 10:
            return Response({
                'detail': 'Account number must be exactly 10 digits'
            }, status=400)
        
        try:
            with transaction.atomic():
                # Get or create bank account
                bank_account, created = InstructorBankAccount.objects.get_or_create(
                    instructor=request.user,
                    defaults={
                        'bank_name': request.data['bank_name'].strip(),
                        'account_number': account_number,
                        'account_name': request.data['account_name'].strip(),
                        'bank_code': request.data['bank_code'].strip(),
                        'auto_payout_enabled': request.data.get('auto_payout_enabled', False),
                        'is_verified': False,
                        'verification_attempts': 0
                    }
                )
                
                if not created:
                    # Update existing account
                    bank_account.bank_name = request.data['bank_name'].strip()
                    bank_account.account_number = account_number
                    bank_account.account_name = request.data['account_name'].strip()
                    bank_account.bank_code = request.data['bank_code'].strip()
                    bank_account.auto_payout_enabled = request.data.get('auto_payout_enabled', False)
                    bank_account.is_verified = False  # Reset verification on update
                    bank_account.verified_at = None
                    bank_account.verification_attempts = 0
                    bank_account.verification_error = None
                
                # Verify the bank account
                verification_result = BankVerificationService.verify_bank_account(bank_account)
                
                # Update verification attempts
                bank_account.verification_attempts += 1
                bank_account.last_verification_attempt = timezone.now()
                
                if verification_result['success']:
                    bank_account.is_verified = True
                    bank_account.verified_at = timezone.now()
                    bank_account.verified_account_name = verification_result['account_name']
                    bank_account.verification_provider = verification_result['provider']
                    bank_account.verification_error = None
                    bank_account.save()
                    
                    logger.info(f"Bank account {'created' if created else 'updated'} and verified: {request.user.email}")
                    
                    return Response({
                        'message': f'Bank account {"configured" if created else "updated"} and verified successfully',
                        'is_verified': True,
                        'account_name': verification_result['account_name'],
                        'auto_payout_enabled': bank_account.auto_payout_enabled,
                        'created': created
                    })
                else:
                    bank_account.verification_error = verification_result['message']
                    bank_account.save()
                    
                    logger.warning(f"Bank account saved but verification failed: {request.user.email} - {verification_result['message']}")
                    
                    return Response({
                        'message': f'Bank account {"saved" if created else "updated"} but verification failed',
                        'error': verification_result['message'],
                        'is_verified': False,
                        'can_retry': bank_account.verification_attempts < 3,
                        'attempts_remaining': 3 - bank_account.verification_attempts,
                        'created': created
                    }, status=400)
                    
        except Exception as e:
            logger.error(f"Bank account configuration error: {str(e)}")
            return Response({
                'detail': 'Failed to configure bank account. Please try again.'
            }, status=500)
        

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_bank_account(request):
    """Re-verify existing bank account"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    try:
        bank_account = request.user.bank_account
        
        # Check verification attempts limit
        if bank_account.verification_attempts >= 3:
            return Response({
                'detail': 'Maximum verification attempts reached. Please contact support.'
            }, status=400)
        
        # Verify the bank account
        verification_result = BankVerificationService.verify_bank_account(bank_account)
        
        # Update verification attempts
        bank_account.verification_attempts += 1
        bank_account.last_verification_attempt = timezone.now()
        
        if verification_result['success']:
            bank_account.is_verified = True
            bank_account.verified_at = timezone.now()
            bank_account.verified_account_name = verification_result['account_name']
            bank_account.verification_provider = verification_result['provider']
            bank_account.verification_error = None
            bank_account.save()
            
            return Response({
                'message': 'Bank account verified successfully',
                'is_verified': True,
                'account_name': verification_result['account_name']
            })
        else:
            bank_account.verification_error = verification_result['message']
            bank_account.save()
            
            return Response({
                'message': 'Bank account verification failed',
                'error': verification_result['message'],
                'attempts_remaining': 3 - bank_account.verification_attempts
            }, status=400)
            
    except InstructorBankAccount.DoesNotExist:
        return Response({'detail': 'No bank account found'}, status=404)
    except Exception as e:
        logger.error(f"Bank account verification error: {str(e)}")
        return Response({'detail': 'Verification failed'}, status=500)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_auto_payout(request):
    """Enable/disable auto payout"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    try:
        bank_account = request.user.bank_account
        
        if not bank_account.is_verified:
            return Response({
                'detail': 'Bank account must be verified before enabling auto payout'
            }, status=400)
        
        enable = request.data.get('enable', False)
        bank_account.auto_payout_enabled = enable
        bank_account.save()
        
        return Response({
            'message': f'Auto payout {"enabled" if enable else "disabled"} successfully',
            'auto_payout_enabled': bank_account.auto_payout_enabled
        })
        
    except InstructorBankAccount.DoesNotExist:
        return Response({'detail': 'No bank account found'}, status=404)
    except Exception as e:
        logger.error(f"Toggle auto payout error: {str(e)}")
        return Response({'detail': 'Failed to update auto payout setting'}, status=500)
    
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_bank_account(request):
    """Delete instructor bank account"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    try:
        bank_account = request.user.bank_account
        
        # Check if there are pending payouts
        pending_payouts = InstructorPayout.objects.filter(
            instructor=request.user,
            status='pending'
        ).count()
        
        if pending_payouts > 0:
            return Response({
                'detail': f'Cannot delete bank account. You have {pending_payouts} pending payouts.',
                'pending_payouts': pending_payouts,
                'suggestion': 'Please wait for pending payouts to be processed before deleting your bank account.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        bank_account.delete()
        
        logger.info(f"Bank account deleted for instructor: {request.user.email}")
        
        return Response({
            'message': 'Bank account deleted successfully'
        }, status=status.HTTP_200_OK)
        
    except InstructorBankAccount.DoesNotExist:
        return Response({'detail': 'No bank account found'}, status=404)
    except Exception as e:
        logger.error(f"Delete bank account error: {str(e)}")
        return Response({'detail': 'Failed to delete bank account'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def bank_account_summary(request):
    """Get bank account summary with earnings info"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    try:
        bank_account = None
        try:
            bank_account = request.user.bank_account
        except InstructorBankAccount.DoesNotExist:
            pass
        
        # Calculate earnings
        from courses.models import CourseEnrollment
        total_revenue = CourseEnrollment.objects.filter(
            course__created_by=request.user,
            payment_status='completed'
        ).aggregate(total=Sum('amount_paid'))['total'] or 0
        
        instructor_earnings = float(total_revenue) * 0.7  # 70% to instructor
        
        # Pending payouts
        pending_payouts = InstructorPayout.objects.filter(
            instructor=request.user,
            status='pending'
        ).aggregate(total=Sum('net_payout'))['total'] or 0
        
        # Processed payouts
        processed_payouts = InstructorPayout.objects.filter(
            instructor=request.user,
            status='completed'
        ).aggregate(total=Sum('net_payout'))['total'] or 0
        
        response_data = {
            'earnings_summary': {
                'total_revenue': float(total_revenue),
                'instructor_share': instructor_earnings,
                'platform_fee': float(total_revenue) * 0.3,
                'pending_payouts': float(pending_payouts),
                'processed_payouts': float(processed_payouts),
                'available_balance': instructor_earnings - float(processed_payouts) - float(pending_payouts)
            },
            'bank_account': None
        }
        
        if bank_account:
            response_data['bank_account'] = {
                'bank_name': bank_account.bank_name,
                'account_number': bank_account.account_number,
                'account_name': bank_account.account_name,
                'bank_code': bank_account.bank_code,
                'is_verified': bank_account.is_verified,
                'verified_at': bank_account.verified_at,
                'auto_payout_enabled': bank_account.auto_payout_enabled,
                'verification_attempts': bank_account.verification_attempts,
                'last_verification_attempt': bank_account.last_verification_attempt,
                'verification_error': bank_account.verification_error
            }
        
        return Response(response_data)
        
    except Exception as e:
        logger.error(f"Bank account summary error: {str(e)}")
        return Response({'detail': 'Failed to fetch bank account summary'}, status=500)
    

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def payout_history(request):
    """Get instructor payout history"""
    if request.user.role != 'admin':
        return Response({'detail': 'Access denied'}, status=403)
    
    try:
        from django.core.paginator import Paginator
        
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        payouts = InstructorPayout.objects.filter(
            instructor=request.user
        ).order_by('-created_at')
        
        paginator = Paginator(payouts, per_page)
        page_obj = paginator.get_page(page)
        
        payout_data = []
        for payout in page_obj.object_list:
            payout_data.append({
                'id': str(payout.id),
                'period_start': payout.period_start,
                'period_end': payout.period_end,
                'total_revenue': float(payout.total_revenue),
                'instructor_share': float(payout.instructor_share),
                'platform_fee': float(payout.platform_fee),
                'net_payout': float(payout.net_payout),
                'status': payout.status,
                'processed_at': payout.processed_at,
                'gateway_reference': payout.gateway_reference,
                'is_auto_processed': payout.is_auto_processed
            })
        
        return Response({
            'payouts': payout_data,
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_payouts': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Payout history error: {str(e)}")
        return Response({'detail': 'Failed to fetch payout history'}, status=500)
    

# Super Admin Views for Processing Payouts
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def pending_payouts(request):
    """Super Admin: Get all pending payouts"""
    if request.user.role != 'super_admin':
        return Response({'detail': 'Super admin access required'}, status=403)
    
    try:
        from django.core.paginator import Paginator
        
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 20))
        
        payouts = InstructorPayout.objects.filter(
            status='pending'
        ).select_related('instructor', 'instructor__bank_account').order_by('-created_at')
        
        paginator = Paginator(payouts, per_page)
        page_obj = paginator.get_page(page)
        
        payout_data = []
        for payout in page_obj.object_list:
            bank_account = getattr(payout.instructor, 'bank_account', None)
            
            payout_data.append({
                'id': str(payout.id),
                'instructor_name': payout.instructor.full_name,
                'instructor_email': payout.instructor.email,
                'period_start': payout.period_start,
                'period_end': payout.period_end,
                'net_payout': float(payout.net_payout),
                'created_at': payout.created_at,
                'is_eligible': payout.is_eligible_for_payout(),
                'bank_verified': bank_account.is_verified if bank_account else False,
                'auto_payout_enabled': bank_account.auto_payout_enabled if bank_account else False
            })
        
        total_pending_amount = InstructorPayout.objects.filter(
            status='pending'
        ).aggregate(total=Sum('net_payout'))['total'] or 0
        
        return Response({
            'pending_payouts': payout_data,
            'total_pending_amount': float(total_pending_amount),
            'pagination': {
                'current_page': page,
                'total_pages': paginator.num_pages,
                'total_payouts': paginator.count,
                'per_page': per_page,
                'has_next': page_obj.has_next(),
                'has_previous': page_obj.has_previous()
            }
        })
        
    except Exception as e:
        logger.error(f"Pending payouts error: {str(e)}")
        return Response({'detail': 'Failed to fetch pending payouts'}, status=500)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def process_payout_request(request, payout_id):
    """Super Admin: Process individual payout"""
    if request.user.role != 'super_admin':
        return Response({'detail': 'Super admin access required'}, status=403)
    
    try:
        result = PayoutService.process_payout(payout_id)
        
        if result['success']:
            return Response({
                'message': result['message'],
                'success': True
            })
        else:
            return Response({
                'message': result['message'],
                'success': False
            }, status=400)
            
    except Exception as e:
        logger.error(f"Process payout error: {str(e)}")
        return Response({'detail': 'Failed to process payout'}, status=500)
    

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_process_payouts(request):
    """Super Admin: Process multiple payouts at once"""
    if request.user.role != 'super_admin':
        return Response({'detail': 'Super admin access required'}, status=403)
    
    try:
        payout_ids = request.data.get('payout_ids', [])
        
        if not payout_ids:
            return Response({'detail': 'No payout IDs provided'}, status=400)
        
        results = []
        successful_count = 0
        failed_count = 0
        
        for payout_id in payout_ids:
            result = PayoutService.process_payout(payout_id)
            results.append({
                'payout_id': payout_id,
                'success': result['success'],
                'message': result['message']
            })
            
            if result['success']:
                successful_count += 1
            else:
                failed_count += 1
        
        return Response({
            'message': f'Processed {len(payout_ids)} payouts: {successful_count} successful, {failed_count} failed',
            'results': results,
            'summary': {
                'total_processed': len(payout_ids),
                'successful': successful_count,
                'failed': failed_count
            }
        })
        
    except Exception as e:
        logger.error(f"Bulk process payouts error: {str(e)}")
        return Response({'detail': 'Failed to process bulk payouts'}, status=500)