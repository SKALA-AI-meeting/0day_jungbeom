package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Message;
import org.springframework.data.jpa.repository.JpaRepository;

public interface MessageRepository extends JpaRepository<Message, Long> {
    java.util.List<Message> findBySessionIdOrderByIdxAsc(String sessionId); long countBySessionId(String sessionId);
}
