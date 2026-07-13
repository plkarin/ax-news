#!/bin/bash
TOKEN=$(grep '^INTERNAL_SYNC_TOKEN=' /opt/ax-news/backend/.env | cut -d= -f2)
curl -sf -X POST "http://127.0.0.1:8000/api/tv/refresh" \
  -H "X-Internal-Token: ${TOKEN}"
