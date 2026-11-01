-- The sync and the sources look new stories up by address, and by title from
-- the same source, to leave duplicates out (db.drop_duplicates). Hash
-- indexes: an address or a title may be longer than a btree entry allows,
-- which would make the insert fail. CONCURRENTLY: the site keeps running
-- while they are built (psql -f runs each statement outside a transaction).
CREATE INDEX CONCURRENTLY IF NOT EXISTS articles_url_hash ON articles USING hash (url);
CREATE INDEX CONCURRENTLY IF NOT EXISTS articles_title_hash ON articles USING hash (lower(trim(title)));
