-- Dialogue ledger (issues, commitments, positions, compacted summary) kept by the agent's turn graph.
-- Stored opaque; shown read-only to the admin, never to the candidate.
ALTER TABLE sessions ADD COLUMN dialogue_json TEXT;
