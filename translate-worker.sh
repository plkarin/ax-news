#!/bin/bash
LOG="/var/log/ax-news/translate.log"
API="http://127.0.0.1:8000"
TOKEN="ax-news-tv-readonly-2026"

date -u >> $LOG

PGPASSWORD="${DB_PASSWORD}" psql -U ax_news -d ax_news -h 127.0.0.1 -c \
  "UPDATE articles SET translated_at = NULL, original_lang = NULL
   WHERE title ~ '[가-힣]' OR title ~ '[一-鿿]';" >> $LOG 2>&1

for i in 1 2 3 4 5; do
  RESULT=$(curl -sf -X POST "${API}/api/tv/translate?token=${TOKEN}&limit=50")
  COUNT=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('translated',0))" 2>/dev/null || echo 0)
  echo "Batch $i: $COUNT" >> $LOG
  if [ "$COUNT" = "0" ]; then break; fi
  sleep 3
done

PGPASSWORD="${DB_PASSWORD}" psql -U ax_news -d ax_news -h 127.0.0.1 -t \
  -c "SELECT COUNT(*) FROM articles WHERE title ~ '[가-힣]' OR title ~ '[一-鿿]';" >> $LOG 2>&1
