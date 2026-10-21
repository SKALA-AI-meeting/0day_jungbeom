package dev.dayzero.backend.task;

import org.springframework.stereotype.Component;

/** TURN: the teammates answer one candidate message; the candidate follows the stream (TOKEN, TOOL_*, DONE). */
@Component
public class TurnHandler implements TaskHandler {
    @Override public String type() { return "TURN"; }
    @Override public boolean candidateVisible() { return true; }
}
