#!/bin/bash
LOG="/var/log/ax-news/dedup.log"
date -u >> $LOG

# Remove title duplicates keeping oldest
DELETED=$(PGPASSWORD="${DB_PASSWORD}" psql -U ax_news -d ax_news -h 127.0.0.1 -t -c "
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
FUTURE=$(PGPASSWORD="${DB_PASSWORD}" psql -U ax_news -d ax_news -h 127.0.0.1 -t -c "
DELETE FROM articles WHERE published_at > NOW() RETURNING id;
" | wc -l)

echo "Deleted $FUTURE future-dated articles" >> $LOG

# Stats
PGPASSWORD="${DB_PASSWORD}" psql -U ax_news -d ax_news -h 127.0.0.1 -c "
SELECT COUNT(*) as total_articles FROM articles;
" >> $LOG 2>&1
