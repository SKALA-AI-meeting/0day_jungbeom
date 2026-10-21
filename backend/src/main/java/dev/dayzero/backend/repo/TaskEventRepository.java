package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.TaskEvent;
import org.springframework.data.jpa.repository.JpaRepository;

public interface TaskEventRepository extends JpaRepository<TaskEvent, Long> {
    java.util.List<TaskEvent> findByTaskIdOrderBySeqAsc(String taskId); int countByTaskId(String taskId);
}
