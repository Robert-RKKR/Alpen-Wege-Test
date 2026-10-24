#!/usr/bin/env bash
set -euo pipefail

# Smoke test for the track pipeline.
# Environment variables: HOST (default http://localhost:8000), EMAIL, PASSWORD

HOST="${HOST:-http://localhost:8000}"
API="$HOST/api/v1"

if [[ -z "${EMAIL:-}" || -z "${PASSWORD:-}" ]]; then
  echo "Usage: EMAIL=user@example.com PASSWORD=secret HOST=http://localhost:8000 bash scripts/smoke_tracks.sh"
  exit 1
fi

echo "=== Login ==="
TOKEN=$(curl -sf "$API/profile/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\": \"$EMAIL\", \"password\": \"$PASSWORD\"}" \
  | jq -r '.response_data.access_token')

if [[ -z "$TOKEN" || "$TOKEN" == "null" ]]; then
  echo "FAIL: login returned no token"; exit 1
fi
echo "Token: ${TOKEN:0:20}..."

AUTH="-H \"Authorization: Bearer $TOKEN\""

# Generate sample files inside the api container
VARIANTS="full no-time no-ele two-trk route-only"
for v in $VARIANTS; do
  echo "--- Generating $v.gpx ---"
  sudo docker exec -w /app -e PYTHONPATH=/app alpen-api \
    python scripts/make_sample_gpx.py --variant "$v" --out "/tmp/$v.gpx" 2>&1 || true
done

# Upload each variant
declare -A TRACK_IDS
declare -A JOB_IDS
for v in $VARIANTS; do
  echo ""
  echo "=== Upload: $v ==="
  RESP=$(curl -sf -X POST "$API/explorer/tracks" \
    -H "Authorization: Bearer $TOKEN" \
    -F "name=$v test" \
    -F "gpx_file=@/tmp/$v.gpx;type=application/gpx+xml" \
    -w "\n%{http_code}" 2>/dev/null || echo "UPLOAD_FAILED")

  if echo "$RESP" | grep -q "UPLOAD_FAILED"; then
    # Try copying from container
    sudo docker cp "alpen-api:/tmp/$v.gpx" "/tmp/$v.gpx" 2>/dev/null || true
    RESP=$(curl -sf -X POST "$API/explorer/tracks" \
      -H "Authorization: Bearer $TOKEN" \
      -F "name=$v test" \
      -F "gpx_file=@/tmp/$v.gpx;type=application/gpx+xml" \
      -w "\n%{http_code}" 2>/dev/null || echo "UPLOAD_FAILED")
  fi

  HTTP=$(echo "$RESP" | tail -1)
  BODY=$(echo "$RESP" | sed '$d')
  TID=$(echo "$BODY" | jq -r '.response_data.id // empty' 2>/dev/null || echo "")
  JID=$(echo "$BODY" | jq -r '.response_data.job_id // empty' 2>/dev/null || echo "")

  echo "  HTTP: $HTTP"
  echo "  Track ID: $TID"
  if [[ -n "$TID" && "$TID" != "null" ]]; then
    TRACK_IDS[$v]="$TID"
    JOB_IDS[$v]="$JID"
  fi
done

# Poll for processing to complete
echo ""
echo "=== Polling for processing ==="
for v in $VARIANTS; do
  TID="${TRACK_IDS[$v]:-}"
  if [[ -z "$TID" ]]; then continue; fi

  for i in $(seq 1 30); do
    STATUS=$(curl -sf "$API/explorer/tracks/$TID" \
      -H "Authorization: Bearer $TOKEN" \
      | jq -r '.response_data.processing_status' 2>/dev/null || echo "error")

    if [[ "$STATUS" == "ready" || "$STATUS" == "failed" ]]; then
      break
    fi
    sleep 2
  done

  echo "  $v ($TID): $STATUS"

  # The job of a ready track ends shortly after the track is ready (POI detection runs last).
  JID="${JOB_IDS[$v]:-}"
  if [[ -n "$JID" ]]; then
    for i in $(seq 1 10); do
      JSTATUS=$(curl -sf "$API/management/my-jobs/$JID" -H "Authorization: Bearer $TOKEN" \
        | jq -r '.response_data.status' 2>/dev/null || echo "error")
      if [[ "$JSTATUS" == "succeeded" || "$JSTATUS" == "failed" ]]; then
        break
      fi
      sleep 2
    done
    echo "    job $JID: $(curl -sf "$API/management/my-jobs/$JID" -H "Authorization: Bearer $TOKEN" \
      | jq -c '.response_data | {status, stage, progress, attempts, result}' 2>/dev/null)"
  fi

  if [[ "$STATUS" == "ready" ]]; then
    DETAIL=$(curl -sf "$API/explorer/tracks/$TID" -H "Authorization: Bearer $TOKEN")
    echo "    warnings: $(echo "$DETAIL" | jq -c '.response_data.processing_warnings')"
    echo "    sport: $(echo "$DETAIL" | jq -r '.response_data.sport_type_id')"
    echo "    metrics: $(echo "$DETAIL" | jq -c '.response_data.metrics')"
  elif [[ "$STATUS" == "failed" ]]; then
    ERR=$(curl -sf "$API/explorer/tracks/$TID" -H "Authorization: Bearer $TOKEN" \
      | jq -r '.response_data.processing_error' 2>/dev/null)
    echo "    error: $ERR"
  fi
done

# Archive and restore the first ready track
FIRST_TID="${TRACK_IDS[full]:-}"
if [[ -n "$FIRST_TID" ]]; then
  echo ""
  echo "=== Archive & Restore ==="
  curl -sf -X DELETE "$API/explorer/tracks/$FIRST_TID" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.response_message'

  echo "  After archive:"
  curl -sf "$API/explorer/tracks?archived=true" \
    -H "Authorization: Bearer $TOKEN" \
    | jq -c '[.response_data[] | .id]' 2>/dev/null

  curl -sf -X POST "$API/explorer/tracks/$FIRST_TID/restore" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.response_message'

  echo "  After restore:"
  curl -sf "$API/explorer/tracks/$FIRST_TID" \
    -H "Authorization: Bearer $TOKEN" \
    | jq -r '.response_data.processing_status'
fi

echo ""
echo "=== Done ==="
