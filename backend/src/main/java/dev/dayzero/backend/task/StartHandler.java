package dev.dayzero.backend.task;

import org.springframework.stereotype.Component;

/**
 * START: the agent assigns the counterpart condition, seeds the shared work items and writes the opening message.
 * A failed START is closed by the candidate (POST /api/sessions/{id}/restart while the session has no messages).
 */
@Component
public class StartHandler implements TaskHandler {
    @Override public String type() { return "START"; }
    @Override public boolean candidateVisible() { return true; }
}
