-- Analytics snapshot (api-contract §5): the bundle analytics-mcp computes for the admin screens (timeline, heatmap,
-- TKI, observer-vs-detector agreement, planted checkpoints), stored as the agent hands it over
-- (business.save_analytics -> PUT /internal/sessions/{id}/analytics). Admin only, never shown to the candidate.
-- state_rev counts the changes that affect analytics (init, turn, choice, detection, markup add/delete, report save,
-- completion); a snapshot computed from an older state_rev is stale.
ALTER TABLE sessions ADD COLUMN analytics_json TEXT;
ALTER TABLE sessions ADD COLUMN analytics_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE sessions ADD COLUMN state_rev BIGINT NOT NULL DEFAULT 0;
