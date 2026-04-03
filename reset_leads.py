import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'linkedin.django_settings'
import django
django.setup()

from crm.models import Deal, Lead

# Reset deals that failed due to "no Connect button"
failed = Deal.objects.filter(
    state='Failed',
    reason__icontains='no Connect button',
)
count = failed.count()
failed.update(state='Qualified', connect_attempts=0, reason='', closing_reason='')

# Un-disqualify their leads
Lead.objects.filter(disqualified=True, deal__reason='').update(disqualified=False)

# Also reset any QUALIFIED deals that had partial attempts
Deal.objects.filter(state='Qualified').update(connect_attempts=0)

print(f'Reset {count} failed deals + cleared attempts on all Qualified deals')
