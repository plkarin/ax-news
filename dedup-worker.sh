#!/bin/bash
LOG="/var/log/ax-news/dedup.log"
# DATABASE_URL comes from backend/.env (EnvironmentFile in ax-news-dedup.service).
: "${DATABASE_URL:?DATABASE_URL is not set}"
date -u >> $LOG

# Remove title duplicates keeping oldest
DELETED=$(psql "${DATABASE_URL}" -t -c "
WITH dupes AS (
    SELECT id,
           ROW_NUMBER() OVER (
               PARTITION BY lower(trim(title)), feed_source
               ORDER BY id ASC
           ) as rn
    FROM articles
)
DELETE FROM articles WHERE id IN (
    SELECT id FROM dupes WHERE rn > 1
)
RETURNING id;
" | wc -l)

echo "Deleted $DELETED duplicate articles" >> $LOG

# Remove future-dated articles
FUTURE=$(psql "${DATABASE_URL}" -t -c "
DELETE FROM articles WHERE published_at > NOW() RETURNING id;
" | wc -l)

echo "Deleted $FUTURE future-dated articles" >> $LOG

# Stats
psql "${DATABASE_URL}" -c "
SELECT COUNT(*) as total_articles FROM articles;
" >> $LOG 2>&1
