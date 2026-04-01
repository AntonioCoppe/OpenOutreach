import os
os.environ['DJANGO_SETTINGS_MODULE'] = 'linkedin.django_settings'
import django
django.setup()
from linkedin.models import Task
from django.utils import timezone
Task.objects.filter(status='pending').update(scheduled_at=timezone.now())
print('Done')
