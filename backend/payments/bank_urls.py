# payments/bank_urls.py
from django.urls import path, include
from . import bank_views

urlpatterns = [
    # Bank account management
    path('banks/', bank_views.get_banks, name='get_banks'),
    path('bank-account/', bank_views.instructor_bank_account, name='instructor_bank_account'),
    path('bank-account/verify/', bank_views.verify_bank_account, name='verify_bank_account'),
    path('bank-account/auto-payout/', bank_views.toggle_auto_payout, name='toggle_auto_payout'),
    path('payout-history/', bank_views.payout_history, name='payout_history'),
    path('bank-account/summary/', bank_views.bank_account_summary, name='bank_account_summary'),
    path('bank-account/delete/', bank_views.delete_bank_account, name='delete_bank_account'),
    
    # Super admin payout management
    path('admin/pending-payouts/', bank_views.pending_payouts, name='pending_payouts'),
    path('admin/payouts/<uuid:payout_id>/process/', bank_views.process_payout_request, name='process_payout'),
    path('admin/payouts/bulk-process/', bank_views.bulk_process_payouts, name='bulk_process_payouts'),
]