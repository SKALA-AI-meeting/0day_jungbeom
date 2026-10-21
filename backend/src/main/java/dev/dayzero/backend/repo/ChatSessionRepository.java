package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.ChatSession;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ChatSessionRepository extends JpaRepository<ChatSession, String> {
    java.util.List<ChatSession> findByCompanyIdOrderByCreatedAtDesc(Long companyId); java.util.List<ChatSession> findByConditionJsonIsNotNull();
}
