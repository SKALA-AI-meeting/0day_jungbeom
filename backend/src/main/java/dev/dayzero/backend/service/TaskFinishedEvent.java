package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.AiTask;

/** Published when a task reaches a terminal state (DONE / FAILED / REJECTED): the loop's end, for domain hooks. */
public record TaskFinishedEvent(AiTask task, String status) {
}
