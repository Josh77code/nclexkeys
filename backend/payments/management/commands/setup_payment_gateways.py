# commands/setup_payment_gateways.py
import os
from django.core.management.base import BaseCommand
from payments.models import PaymentGateway

class Command(BaseCommand):
    help = 'Setup payment gateways with environment variables'

    def handle(self, *args, **options):
        # Create or update Paystack gateway
        paystack_gateway, created = PaymentGateway.objects.update_or_create(
            name='paystack',
            defaults={
                'display_name': 'Paystack',
                'public_key': os.environ.get('PAYSTACK_PUBLIC_KEY', ''),
                'secret_key': os.environ.get('PAYSTACK_SECRET_KEY', ''),
                'webhook_secret': os.environ.get('PAYSTACK_WEBHOOK_SECRET', ''),
                'base_url': 'https://api.paystack.co',
                'is_active': True,
                'supported_currencies': ['NGN', 'USD', 'GHS', 'ZAR'],
                'supports_webhooks': True,
                'supports_refunds': True,
                'supports_transfers': True,
                'gateway_config': {
                    'split_code': os.environ.get('PAYSTACK_SPLIT_CODE', ''),
                    'channels': ['card', 'bank', 'ussd', 'qr', 'mobile_money']
                }
            }
        )
        
        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f'{action} Paystack gateway successfully')
        )

        # Create or update Flutterwave gateway
        flutterwave_gateway, created = PaymentGateway.objects.update_or_create(
            name='flutterwave',
            defaults={
                'display_name': 'Flutterwave',
                'public_key': os.environ.get('FLUTTERWAVE_PUBLIC_KEY', ''),
                'secret_key': os.environ.get('FLUTTERWAVE_SECRET_KEY', ''),
                'webhook_secret': os.environ.get('FLUTTERWAVE_WEBHOOK_SECRET', ''),
                'base_url': 'https://api.flutterwave.com/v3',
                'is_active': True,
                'supported_currencies': ['NGN', 'USD', 'GHS', 'KES', 'UGX', 'TZS'],
                'supports_webhooks': True,
                'supports_refunds': True,
                'supports_transfers': True,
                'gateway_config': {
                    'encryption_key': os.environ.get('FLUTTERWAVE_ENCRYPTION_KEY', ''),
                    'payment_methods': ['card', 'account', 'ussd', 'qr', 'mobile_money']
                }
            }
        )
        
        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f'{action} Flutterwave gateway successfully')
        )

        # Display status
        self.stdout.write("\n" + "="*50)
        self.stdout.write("PAYMENT GATEWAY SETUP COMPLETE")
        self.stdout.write("="*50)
        
        if paystack_gateway.public_key:
            self.stdout.write(f"✅ Paystack: Configured")
        else:
            self.stdout.write(f"❌ Paystack: Missing keys in environment")
            
        if flutterwave_gateway.public_key:
            self.stdout.write(f"✅ Flutterwave: Configured")
        else:
            self.stdout.write(f"❌ Flutterwave: Missing keys in environment")

        self.stdout.write("\n⚠️  Next Steps:")
        self.stdout.write("1. Add payment gateway keys to your .env file")
        self.stdout.write("2. Run migrations: python manage.py migrate")
        self.stdout.write("3. Set up webhooks in your payment gateway dashboard")
        self.stdout.write("4. Test payments with test cards")