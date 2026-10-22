package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.ChatSession;
import jakarta.persistence.LockModeType;
import java.time.OffsetDateTime;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ChatSessionRepository extends JpaRepository<ChatSession, String> {
    java.util.List<ChatSession> findByCompanyIdOrderByCreatedAtDesc(Long companyId); java.util.List<ChatSession> findByAccountIdOrderByCreatedAtDesc(Long accountId); java.util.List<ChatSession> findByCompanyIdAndReportStatusOrderByCreatedAtAsc(Long companyId, String reportStatus);

    /** Every assigned condition (balanced allocation, GET /internal/conditions): only that column, never the whole rows with their snapshots. */
    @Query("select s.conditionJson from ChatSession s where s.conditionJson is not null")
    java.util.List<String> allConditionJson();

    /** One more change that affects analytics (in the database, so two concurrent changes count twice). */
    @Modifying
    @Query(value = "UPDATE sessions SET state_rev = state_rev + 1 WHERE id = :id", nativeQuery = true)
    int bumpRev(@Param("id") String id);

    /** The session row, locked until the transaction ends (analytics snapshot guard, one ANALYTICS task at a time). */
    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select s from ChatSession s where s.id = :id")
    Optional<ChatSession> findForUpdate(@Param("id") String id);

    @Modifying
    @Query(value = "UPDATE sessions SET analytics_json = :json, analytics_at = :at WHERE id = :id", nativeQuery = true)
    int storeAnalytics(@Param("id") String id, @Param("json") String json, @Param("at") OffsetDateTime at);
}
