#!/usr/bin/env bash
set -eu

# Minimal curl-based API test script for quick manual testing inside a container.
# Usage: ./config/test_api.sh [BASE_URL] [AGENCY_ID] [SOURCE_BUCKET] [DESTINATION_BUCKET]
# Example: ./config/test_api.sh http://localhost:8000 10 my-source-bucket my-dest-bucket

BASE_URL=${1:-http://localhost:5090}
AGENCY_ID=${2:-1}
SOURCE_BUCKET=${3:-my-source-bucket}
DESTINATION_BUCKET=${4:-my-destination-bucket}

echo "POST ${BASE_URL}/api/s3/analyze/ -> {\"agency_id\": ${AGENCY_ID}, \"source_bucket\": \"${SOURCE_BUCKET}\", \"destination_bucket\": \"${DESTINATION_BUCKET}\"}"
curl -i -X POST "${BASE_URL}/api/s3/analyze/" \
  -H 'Content-Type: application/json' \
  -d "{\"agency_id\": ${AGENCY_ID}, \"source_bucket\": \"${SOURCE_BUCKET}\", \"destination_bucket\": \"${DESTINATION_BUCKET}\"}"

echo

#echo "POST ${BASE_URL}/api/s3/process/ -> {\"agency_id\": ${AGENCY_ID}, \"source_bucket\": \"${SOURCE_BUCKET}\", \"destination_bucket\": \"${DESTINATION_BUCKET}\"}"
#curl -i -X POST "${BASE_URL}/api/s3/process/" \
#  -H 'Content-Type: application/json' \
#  -d "{\"agency_id\": ${AGENCY_ID}, \"source_bucket\": \"${SOURCE_BUCKET}\", \"destination_bucket\": \"${DESTINATION_BUCKET}\"}"
#
#exit 0
