package dev.dayzero.backend.task;

import dev.dayzero.backend.config.AppProperties;
import dev.dayzero.backend.domain.AiTask;
import dev.dayzero.backend.repo.AiTaskRepository;
import dev.dayzero.backend.service.TaskService;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * Loop closure for tasks the agent never finishes (agent down, lost message, crash between events):
 * QUEUED / RUNNING with no progress (updated_at) for dayzero.task-stale-minutes -> FAILED, through the normal event
 * path, so SSE subscribers get the FAILED event and the handler hooks run (START -> the candidate can restart,
 * REPORT -> REPORT_FAILED, ACCOUNT_REVIEW -> REVIEW_ERROR on the checklist).
 * WAITING_APPROVAL never times out: a person decides, and it is on the checklist.
 */
@Component
public class TaskWatchdog {
    private static final Logger log = LoggerFactory.getLogger(TaskWatchdog.class);
    private static final Set<String> WATCHED = Set.of("QUEUED", "RUNNING");

    private final AiTaskRepository tasks;
    private final TaskService service;
    private final AppProperties props;

    public TaskWatchdog(AiTaskRepository tasks, TaskService service, AppProperties props) {
        this.tasks = tasks; this.service = service; this.props = props;
    }

    @Scheduled(fixedDelayString = "${dayzero.task-watchdog-interval-ms:60000}", initialDelayString = "${dayzero.task-watchdog-interval-ms:60000}")
    public void tick() {
        sweep();
    }

    /** One pass; returns the ids of the tasks it failed. */
    public List<String> sweep() {
        int minutes = props.taskStaleMinutes();
        OffsetDateTime cutoff = OffsetDateTime.now().minusMinutes(minutes);
        String error = "작업이 " + minutes + "분 넘게 진행되지 않아 중단했어요.";
        List<String> closed = new ArrayList<>();
        for (AiTask t : tasks.findByStatusInAndUpdatedAtBefore(WATCHED, cutoff)) {
            try {
                if (service.expire(t.id, cutoff, error)) closed.add(t.id);
            } catch (Exception e) {
                log.warn("watchdog could not close task {}: {}", t.id, e.toString());
            }
        }
        if (!closed.isEmpty()) log.warn("watchdog failed {} stale task(s): {}", closed.size(), closed);
        return closed;
    }
}
