# payments/serializers.py
from rest_framework import serializers
from .models import (
    PaymentRefund, Payment
)

class PaymentSerializer(serializers.ModelSerializer):
    course_title = serializers.CharField(source='course.title', read_only=True)
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'reference', 'amount', 'currency', 'status',
            'gateway_name', 'payment_method', 'created_at', 'paid_at',
            'course_title', 'user_name', 'user_email', 'gateway_fee',
            'net_amount'
        ]
        read_only_fields = ['id', 'reference', 'created_at']


class RefundSerializer(serializers.ModelSerializer):
    payment_reference = serializers.CharField(source='payment.reference', read_only=True)
    course_title = serializers.CharField(source='payment.course.title', read_only=True)
    gateway_name = serializers.CharField(source='payment.gateway_name', read_only=True)
    
    class Meta:
        model = PaymentRefund
        fields = [
            'id', 'amount', 'reason', 'status', 'payment_reference',
            'course_title', 'gateway_name', 'requested_at', 'processed_at',
            'completed_at', 'failure_reason', 'admin_notes'
        ]
        read_only_fields = [
            'id', 'status', 'processed_at', 'completed_at', 
            'failure_reason', 'admin_notes'
        ]