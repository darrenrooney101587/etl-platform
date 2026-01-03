"""
API views for S3 file processing operations.

This module provides REST API endpoints for managing S3 file processing operations,
allowing external systems to trigger processing jobs and retrieve status information.
"""

import base64
import json
import logging
import os
from typing import Any, Dict

from django.http import JsonResponse, HttpRequest
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from service.service_handler import ServiceHandler

logger = logging.getLogger(__name__)


class S3ProcessingBaseView(View):
    """Base view class for S3 processing API endpoints."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def _authenticate_request(self, request) -> bool:
        """
        Validate incoming request using Basic Auth or X-Trigger-Secret fallback.

        Basic Auth: compare credentials against BASIC_AUTH_USER and BASIC_AUTH_PASSWORD env vars.
        If no Authorization header is present, fall back to checking X-Trigger-Secret against TRIGGER_SECRET.
        """
        # Try Basic Auth first
        auth_header = request.headers.get("Authorization", "")
        if auth_header and isinstance(auth_header, str) and auth_header.lower().startswith("basic "):
            encoded = auth_header.split(" ", 1)[1].strip()
            try:
                decoded = base64.b64decode(encoded).decode("utf-8")
                username, _, password = decoded.partition(":")
            except Exception:
                logger.warning("Invalid Basic auth encoding from %s", request.META.get("REMOTE_ADDR"))
                return False

            expected_user = os.environ.get("BASIC_AUTH_USER")
            expected_password = os.environ.get("BASIC_AUTH_PASSWORD")
            if expected_user and expected_password and username == expected_user and password == expected_password:
                return True
            logger.warning("Basic auth failed for user %s from %s", username, request.META.get("REMOTE_ADDR"))
            return False

        return True


    def get_service(self, request_data: Dict[str, Any]) -> ServiceHandler:
        """Create and return an ServiceHandler instance with request parameters.

        :param request_data: Request data containing bucket configuration
        :type request_data: Dict[str, Any]
        :return: Configured ServiceHandler instance
        :rtype: ServiceHandler
        """
        source_bucket = request_data.get('source_bucket')
        if isinstance(source_bucket, str):
            source_bucket = source_bucket.strip() or None
        else:
            source_bucket = None

        destination_bucket = request_data.get('destination_bucket')
        if isinstance(destination_bucket, str):
            destination_bucket = destination_bucket.strip() or None
        else:
            destination_bucket = None

        return ServiceHandler(
            source_bucket=source_bucket,
            destination_bucket=destination_bucket
        )

    def parse_request_json(self, request: HttpRequest) -> Dict[str, Any]:
        """Parse JSON request body safely.

        :param request: HTTP request object
        :type request: HttpRequest
        :return: Parsed JSON data or empty dict
        :rtype: Dict[str, Any]
        """
        try:
            if request.body:
                return json.loads(request.body.decode('utf-8'))
            return {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    @staticmethod
    def parse_bool(value: Any, default: bool = False) -> bool:
        """Parse a flexible boolean value from request payloads.

        Accepts actual booleans, 0/1, and common truthy strings.

        :param value: Raw value to parse
        :type value: Any
        :param default: Default when value is None or unrecognized
        :type default: bool
        :return: Parsed boolean
        :rtype: bool
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return default


@method_decorator(csrf_exempt, name='dispatch')
class S3ProcessingAnalyzeView(S3ProcessingBaseView):
    """API view for analyzing agency data without processing (dry run)."""

    def post(self, request: HttpRequest) -> JsonResponse:
        """Analyze agency data and return summary without processing files.

        Expected JSON payload:
        {
            "agency_id": 10,
            "source_bucket": "optional-source-bucket",
            "destination_bucket": "optional-destination-bucket",
            "dry_run": true
        }

        :param request: HTTP request object
        :type request: HttpRequest
        :return: JSON response with analysis results
        :rtype: JsonResponse
        """
        try:
            if not self._authenticate_request(request):
                return JsonResponse({"status": "unauthorized"}, status=401)

            request_data = self.parse_request_json(request)

            # Validate required parameters
            agency_id = request_data.get('agency_id')
            if not agency_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'agency_id is required'
                }, status=400)

            try:
                agency_id = int(agency_id)
            except (ValueError, TypeError):
                return JsonResponse({
                    'status': 'error',
                    'message': 'agency_id must be a valid integer'
                }, status=400)

            dry_run = self.parse_bool(request_data.get('dry_run', True), default=True)

            # Create service and analyze
            service = self.get_service(request_data)
            result = service.analyze_agency_data(agency_id, dry_run=dry_run)

            # Return appropriate HTTP status based on result
            if result['status'] == 'error':
                return JsonResponse(result, status=500)
            else:
                return JsonResponse(result, status=200)
        except Exception as e:
            logger.exception("Unexpected error in S3ProcessingAnalyzeView")
            return JsonResponse({
                'status': 'error',
                'message': 'Internal server error'
            }, status=500)


@method_decorator(csrf_exempt, name='dispatch')
class S3ProcessingProcessView(S3ProcessingBaseView):
    """API view for processing S3 files and employment history."""

    def post(self, request: HttpRequest) -> JsonResponse:
        """Process S3 files and employment history for an agency.

        Expected JSON payload:
        {
            "agency_id": 10,
            "source_bucket": "optional-source-bucket",
            "destination_bucket": "optional-destination-bucket",
            "dry_run": false
        }

        :param request: HTTP request object
        :type request: HttpRequest
        :return: JSON response with processing results
        :rtype: JsonResponse
        """
        try:
            if not self._authenticate_request(request):
                return JsonResponse({"status": "unauthorized"}, status=401)

            request_data = self.parse_request_json(request)

            # Validate required parameters
            agency_id = request_data.get('agency_id')
            if not agency_id:
                return JsonResponse({
                    'status': 'error',
                    'message': 'agency_id is required'
                }, status=400)

            try:
                agency_id = int(agency_id)
            except (ValueError, TypeError):
                return JsonResponse({
                    'status': 'error',
                    'message': 'agency_id must be a valid integer'
                }, status=400)

            dry_run = self.parse_bool(request_data.get('dry_run', False), default=False)

            # Create service and process files
            service = self.get_service(request_data)
            result = service.process_agency_files(agency_id, dry_run=dry_run)

            # Return appropriate HTTP status based on result
            if result['status'] == 'error':
                return JsonResponse(result, status=500)
            elif result['status'] == 'warning':
                return JsonResponse(result, status=200)  # 200 for warnings as operation succeeded
            else:
                return JsonResponse(result, status=200)
        except Exception as e:
            logger.exception("Unexpected error in S3ProcessingProcessView")
            return JsonResponse({
                'status': 'error',
                'message': 'Internal server error'
            }, status=500)
