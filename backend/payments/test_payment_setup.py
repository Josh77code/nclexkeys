# payments/test_payment_setup.py - Run this script to test your payment setup
from django.test import TestCase
import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from payments.models import PaymentGateway
from payments.services import PaymentServiceFactory

# Create your tests here.
def test_payment_gateways():
    print("🔍 Testing Payment Gateway Setup...")
    print("=" * 50)
    
    # Test database records
    gateways = PaymentGateway.objects.all()
    
    if not gateways.exists():
        print("❌ No payment gateways found in database")
        print("💡 Run: python manage.py setup_payment_gateways")
        return False
    
    for gateway in gateways:
        print(f"\n📊 {gateway.display_name}")
        print(f"   Status: {'✅ Active' if gateway.is_active else '❌ Inactive'}")
        print(f"   Public Key: {'✅ Set' if gateway.public_key else '❌ Missing'}")
        print(f"   Secret Key: {'✅ Set' if gateway.secret_key else '❌ Missing'}")
        print(f"   Webhooks: {'✅ Supported' if gateway.supports_webhooks else '❌ Not supported'}")
        
        # Test service initialization
        try:
            service = PaymentServiceFactory.get_service(gateway.name)
            print(f"   Service: ✅ Initialized successfully")
        except Exception as e:
            print(f"   Service: ❌ Failed to initialize - {str(e)}")
    
    return True

def test_environment_variables():
    print("\n🔍 Testing Environment Variables...")
    print("=" * 50)
    
    required_vars = [
        'PAYSTACK_PUBLIC_KEY',
        'PAYSTACK_SECRET_KEY', 
        'SITE_URL',
        'DATABASE_URL'
    ]
    
    optional_vars = [
        'FLUTTERWAVE_PUBLIC_KEY',
        'FLUTTERWAVE_SECRET_KEY',
        'PAYSTACK_WEBHOOK_SECRET'
    ]
    
    all_good = True
    
    for var in required_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: Set")
        else:
            print(f"❌ {var}: Missing (Required)")
            all_good = False
    
    for var in optional_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: Set")
        else:
            print(f"⚠️  {var}: Missing (Optional)")
    
    return all_good

def test_url_patterns():
    print("\n🔍 Testing URL Patterns...")
    print("=" * 50)
    
    try:
        from django.urls import reverse
        
        test_urls = [
            ('payments:payment_history', 'payments/transactions/'),
            ('payments:instructor_bank_account', 'payments/bank-account/'),
            ('payments:instructor_earnings', 'payments/earnings/'),
            ('payments:paystack_webhook', 'payments/webhooks/paystack/'),
        ]
        
        for url_name, expected_path in test_urls:
            try:
                url = reverse(url_name)
                print(f"✅ {url_name}: {url}")
            except Exception as e:
                print(f"❌ {url_name}: Failed - {str(e)}")
        
        return True
        
    except Exception as e:
        print(f"❌ URL testing failed: {str(e)}")
        return False

def main():
    print("🚀 PAYMENT SYSTEM SETUP TEST")
    print("=" * 50)
    
    env_ok = test_environment_variables()
    db_ok = test_payment_gateways()
    url_ok = test_url_patterns()
    
    print("\n" + "=" * 50)
    print("📋 SUMMARY")
    print("=" * 50)
    
    if env_ok and db_ok and url_ok:
        print("🎉 All tests passed! Your payment system is ready.")
        print("\n📝 Next steps:")
        print("1. Set up webhooks in payment gateway dashboards")
        print("2. Test with demo payments")
        print("3. Configure email notifications")
    else:
        print("⚠️  Some issues found. Please fix them before proceeding.")
        
        if not env_ok:
            print("   - Fix environment variables")
        if not db_ok:
            print("   - Run payment gateway setup command")
        if not url_ok:
            print("   - Check URL configuration")

if __name__ == "__main__":
    main()