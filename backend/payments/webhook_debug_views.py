# payments/webhook_debug_views.py
# Enhanced webhook testing and debugging for development

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

@csrf_exempt
@require_http_methods(["GET", "POST"])
def webhook_test_endpoint(request):
    """
    Enhanced test endpoint for webhook debugging
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if request.method == "GET":
        return JsonResponse({
            'status': 'success',
            'message': 'Webhook endpoints are working',
            'timestamp': timestamp,
            'endpoints': {
                'paystack': request.build_absolute_uri('/api/payments/webhooks/paystack/'),
                'flutterwave': request.build_absolute_uri('/api/payments/webhooks/flutterwave/'),
                'test': request.build_absolute_uri('/api/payments/webhooks/test/')
            },
            'ngrok_info': {
                'detected_host': request.get_host(),
                'is_https': request.is_secure(),
                'user_agent': request.META.get('HTTP_USER_AGENT', 'Unknown')
            }
        })
    
    elif request.method == "POST":
        # Log the webhook attempt
        headers = {key: value for key, value in request.META.items() 
                  if key.startswith('HTTP_')}
        
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except:
            payload = request.body.decode('utf-8')
        
        logger.info(f"Test webhook received at {timestamp}")
        logger.info(f"Headers: {headers}")
        logger.info(f"Payload: {payload}")
        
        return JsonResponse({
            'status': 'success',
            'message': 'Test webhook received successfully',
            'timestamp': timestamp,
            'received_data': {
                'headers': headers,
                'payload': payload,
                'method': request.method,
                'content_type': request.content_type
            }
        })

@api_view(['GET'])
@permission_classes([AllowAny])
def webhook_status(request):
    """
    Check webhook system status
    """
    from payments.models import PaymentGateway, PaymentWebhook
    from django.db.models import Count
    from datetime import timedelta
    from django.utils import timezone
    
    # Get recent webhook activity
    last_24h = timezone.now() - timedelta(hours=24)
    recent_webhooks = PaymentWebhook.objects.filter(
        created_at__gte=last_24h
    ).values('gateway__name', 'event_type', 'success').annotate(
        count=Count('id')
    )
    
    # Get gateway status
    gateways = PaymentGateway.objects.filter(is_active=True)
    gateway_status = []
    
    for gateway in gateways:
        gateway_status.append({
            'name': gateway.name,
            'display_name': gateway.display_name,
            'supports_webhooks': gateway.supports_webhooks,
            'webhook_secret_configured': bool(gateway.webhook_secret),
            'last_webhook': PaymentWebhook.objects.filter(
                gateway=gateway
            ).order_by('-created_at').first()
        })
    
    return Response({
        'system_status': 'operational',
        'timestamp': timezone.now(),
        'ngrok_detected': 'ngrok' in request.get_host().lower(),
        'webhook_url': request.build_absolute_uri('/api/payments/webhooks/'),
        'gateways': gateway_status,
        'recent_activity': list(recent_webhooks),
        'debug_info': {
            'host': request.get_host(),
            'is_secure': request.is_secure(),
            'remote_addr': request.META.get('REMOTE_ADDR'),
            'user_agent': request.META.get('HTTP_USER_AGENT')
        }
    })

@csrf_exempt
@require_http_methods(["POST"])
def simulate_webhook(request):
    """
    Simulate webhook for testing (development only)
    """
    try:
        data = json.loads(request.body)
        event_type = data.get('event', 'charge.success')
        gateway = data.get('gateway', 'paystack')
        
        # Simulate webhook data based on gateway
        if gateway == 'paystack':
            webhook_data = {
                "event": event_type,
                "data": {
                    "reference": data.get('reference', 'test-ref-123'),
                    "amount": data.get('amount', 10000),  # 100 NGN in kobo
                    "currency": "NGN",
                    "status": "success",
                    "customer": {
                        "email": data.get('email', 'test@example.com')
                    },
                    "authorization": {
                        "authorization_code": "AUTH_test123",
                        "card_type": "visa",
                        "last4": "1234"
                    }
                }
            }
            
            # Send to paystack webhook handler
            from .webhook_views import paystack_webhook
            response = paystack_webhook(request)
            
        elif gateway == 'flutterwave':
            webhook_data = {
                "event": event_type,
                "data": {
                    "tx_ref": data.get('reference', 'test-ref-123'),
                    "amount": data.get('amount', 100),  # 100 NGN
                    "currency": "NGN",
                    "status": "successful",
                    "customer": {
                        "email": data.get('email', 'test@example.com')
                    }
                }
            }
            
            # Send to flutterwave webhook handler
            from .webhook_views import flutterwave_webhook
            response = flutterwave_webhook(request)
        
        return JsonResponse({
            'success': True,
            'message': f'Simulated {gateway} {event_type} webhook',
            'webhook_data': webhook_data
        })
        
    except Exception as e:
        logger.error(f"Webhook simulation error: {str(e)}")
        return JsonResponse({
            'success': False,
            'message': f'Simulation failed: {str(e)}'
        }, status=500)