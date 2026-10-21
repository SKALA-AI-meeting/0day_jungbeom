package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.AiTask;
import java.util.Map;

/**
 * Published when a task reaches a terminal state (DONE / FAILED / REJECTED): the loop's end, for domain hooks
 * (TaskHandlers -> TaskHandler.onFinished). `data` is the terminal event's data (empty when there was none).
 */
public record TaskFinishedEvent(AiTask task, String status, Map<String, Object> data) {
    public TaskFinishedEvent(AiTask task, String status) {
        this(task, status, Map.of());
    }
}
