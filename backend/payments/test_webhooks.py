# Create this file: payments/test_webhooks.py
import requests
import json
import hmac
import hashlib

# Create your tests here.
def test_paystack_webhook():
    # Test payload (similar to what Paystack sends)
    payload = {
        "event": "charge.success",
        "data": {
            "id": 302961,
            "domain": "live",
            "status": "success",
            "reference": "your_test_reference_here",
            "amount": 5000,
            "message": None,
            "gateway_response": "Successful",
            "paid_at": "2023-01-01T12:00:00.000Z",
            "created_at": "2023-01-01T12:00:00.000Z",
            "channel": "card",
            "currency": "NGN",
            "ip_address": "127.0.0.1",
            "metadata": {
                "user_id": "123",
                "course_id": "456"
            },
            "customer": {
                "id": 23070,
                "first_name": "John",
                "last_name": "Doe",
                "email": "john@example.com",
                "customer_code": "CUS_xnxdt6s1zg5f4rx",
                "phone": "+2348123456789",
                "metadata": {},
                "risk_action": "default"
            },
            "authorization": {
                "authorization_code": "AUTH_72btexffdgd",
                "bin": "408408",
                "last4": "4081",
                "exp_month": "12",
                "exp_year": "2020",
                "channel": "card",
                "card_type": "visa",
                "bank": "TEST BANK",
                "country_code": "NG",
                "brand": "visa",
                "reusable": True,
                "signature": "SIG_uNYD5mNgA6E7e29xQJFLzq8S"
            }
        }
    }
    
    # Convert to JSON string
    payload_json = json.dumps(payload)
    
    # Create signature (you need your webhook secret)
    webhook_secret = "your_webhook_secret_here"
    signature = hmac.new(
        webhook_secret.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha512
    ).hexdigest()
    
    # Send test webhook
    response = requests.post(
        'http://localhost:8000/api/webhooks/paystack/',
        data=payload_json,
        headers={
            'X-Paystack-Signature': signature,
            'Content-Type': 'application/json'
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")

if __name__ == "__main__":
    test_paystack_webhook()