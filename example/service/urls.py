"""
URL configuration for service app.

This module defines the URL patterns for the data processor API endpoints.
"""

from django.urls import path
from . import views

app_name = 'service'

urlpatterns = [
    # API endpoints for S3 processing
    path('api/s3/analyze/', views.S3ProcessingAnalyzeView.as_view(), name='s3_analyze'),
    path('api/s3/process/', views.S3ProcessingProcessView.as_view(), name='s3_process'),
]
