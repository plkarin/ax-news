-- Migration 002: add audio summary/TTS columns to articles
-- Applied: 2026-07-22
ALTER TABLE articles ADD COLUMN IF NOT EXISTS audio_status VARCHAR(20) DEFAULT 'none';
-- values: 'none' | 'generating' | 'done' | 'failed'
ALTER TABLE articles ADD COLUMN IF NOT EXISTS audio_summary_text TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS audio_url TEXT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS audio_duration_seconds INT;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS audio_generated_at TIMESTAMPTZ;
ALTER TABLE articles ADD COLUMN IF NOT EXISTS audio_error TEXT;
