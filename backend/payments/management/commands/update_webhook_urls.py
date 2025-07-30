# commands/update_webhook_urls.py
# This command helps you update webhook URLs when ngrok restarts

from django.core.management.base import BaseCommand
from payments.models import PaymentGateway
import requests
import os

class Command(BaseCommand):
    help = 'Update webhook URLs for development with ngrok'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ngrok-url',
            type=str,
            help='Your ngrok HTTPS URL (e.g., https://abc123.ngrok.io)',
        )
        parser.add_argument(
            '--auto-detect',
            action='store_true',
            help='Auto-detect ngrok URL from local API',
        )

    def handle(self, *args, **options):
        ngrok_url = options.get('ngrok_url')
        
        # Auto-detect ngrok URL if requested
        if options.get('auto_detect'):
            try:
                response = requests.get('http://127.0.0.1:4040/api/tunnels', timeout=5)
                tunnels = response.json()['tunnels']
                
                # Find HTTPS tunnel
                for tunnel in tunnels:
                    if tunnel['proto'] == 'https':
                        ngrok_url = tunnel['public_url']
                        break
                        
                if ngrok_url:
                    self.stdout.write(f"🔍 Auto-detected ngrok URL: {ngrok_url}")
                else:
                    self.stdout.write(self.style.ERROR("❌ Could not auto-detect ngrok URL"))
                    return
                    
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to auto-detect ngrok URL: {str(e)}"))
                return
        
        if not ngrok_url:
            self.stdout.write(self.style.ERROR("❌ Please provide --ngrok-url or use --auto-detect"))
            return
        
        # Ensure HTTPS
        if not ngrok_url.startswith('https://'):
            ngrok_url = ngrok_url.replace('http://', 'https://')
        
        # Remove trailing slash
        ngrok_url = ngrok_url.rstrip('/')
        
        # Update environment variable (for this session)
        os.environ['NGROK_URL'] = ngrok_url
        
        self.stdout.write("🔧 Updated webhook URLs:")
        self.stdout.write("=" * 50)
        
        # Display webhook URLs for manual configuration
        webhook_urls = {
            'Paystack': f"{ngrok_url}/api/payments/webhooks/paystack/",
            'Flutterwave': f"{ngrok_url}/api/payments/webhooks/flutterwave/",
            'Test endpoint': f"{ngrok_url}/api/payments/webhooks/test/"
        }
        
        for service, url in webhook_urls.items():
            self.stdout.write(f"📡 {service}: {url}")
        
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("📋 Next Steps:")
        self.stdout.write("1. Copy the Paystack webhook URL above")
        self.stdout.write("2. Go to your Paystack dashboard")
        self.stdout.write("3. Update the 'Test Webhook URL' field")
        self.stdout.write("4. Save the settings")
        self.stdout.write("5. Test with a payment!")
        
        # Test webhook endpoint
        try:
            test_url = f"{ngrok_url}/api/payments/webhooks/test/"
            response = requests.get(test_url, timeout=10)
            
            if response.status_code == 200:
                self.stdout.write(f"\n✅ Webhook endpoint is accessible: {test_url}")
            else:
                self.stdout.write(f"\n⚠️  Webhook endpoint returned {response.status_code}: {test_url}")
                
        except Exception as e:
            self.stdout.write(f"\n❌ Could not test webhook endpoint: {str(e)}")
            
        # Save to a local file for reference
        try:
            with open('.ngrok_urls.txt', 'w') as f:
                f.write(f"# Generated webhook URLs - {ngrok_url}\n")
                for service, url in webhook_urls.items():
                    f.write(f"{service}: {url}\n")
            self.stdout.write(f"\n💾 URLs saved to .ngrok_urls.txt for reference")
        except Exception as e:
            self.stdout.write(f"\n⚠️  Could not save URLs to file: {str(e)}")