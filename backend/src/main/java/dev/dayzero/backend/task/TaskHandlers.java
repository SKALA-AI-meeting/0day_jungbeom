package dev.dayzero.backend.task;

import dev.dayzero.backend.service.TaskFinishedEvent;
import java.util.*;
import org.springframework.context.event.EventListener;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Registry of TaskHandler beans by type. Unknown types cannot be created; old rows of a removed type get no hooks. */
@Component
public class TaskHandlers {
    private static final TaskHandler NONE = () -> "";

    private final Map<String, TaskHandler> byType = new LinkedHashMap<>();

    public TaskHandlers(List<TaskHandler> all) {
        for (TaskHandler h : all) {
            if (byType.put(h.type(), h) != null) throw new IllegalStateException("duplicate TaskHandler for " + h.type());
        }
    }

    public Set<String> types() { return Collections.unmodifiableSet(byType.keySet()); }

    public Optional<TaskHandler> find(String type) { return Optional.ofNullable(byType.get(type)); }

    /** For a new task: the type must be registered. */
    public TaskHandler require(String type) {
        return find(type).orElseThrow(() -> new ResponseStatusException(HttpStatus.BAD_REQUEST, "알 수 없는 작업 종류예요."));
    }

    /** For a stored task: its handler, or one with only the defaults (not visible, not resumable, no hooks). */
    public TaskHandler of(String type) { return find(type).orElse(NONE); }

    /** End of the loop: TaskService publishes TaskFinishedEvent for the agent's DONE / FAILED and for watchdog timeouts. */
    @EventListener
    public void onTaskFinished(TaskFinishedEvent e) {
        of(e.task().type).onFinished(e.task(), e.status(), e.data());
    }
}
