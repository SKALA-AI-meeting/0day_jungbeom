package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.AiTask;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AiTaskRepository extends JpaRepository<AiTask, String> {
    java.util.List<AiTask> findBySessionIdOrderByCreatedAtDesc(String sessionId); java.util.List<AiTask> findTop30ByCreatedByOrderByCreatedAtDesc(String createdBy); java.util.List<AiTask> findTop30ByCompanyIdOrderByCreatedAtDesc(Long companyId); java.util.List<AiTask> findTop30ByCompanyIdAndTypeNotInOrderByCreatedAtDesc(Long companyId, java.util.Collection<String> types); java.util.List<AiTask> findByCompanyIdAndStatusOrderByCreatedAtAsc(Long companyId, String status); java.util.List<AiTask> findByAccountIdAndTypeOrderByCreatedAtDesc(Long accountId, String type); java.util.List<AiTask> findBySessionIdAndTypeAndStatusIn(String sessionId, String type, java.util.Collection<String> statuses); java.util.List<AiTask> findBySessionIdAndTypeOrderByCreatedAtDesc(String sessionId, String type); java.util.List<AiTask> findByStatusInAndUpdatedAtBefore(java.util.Collection<String> statuses, java.time.OffsetDateTime cutoff);
}
