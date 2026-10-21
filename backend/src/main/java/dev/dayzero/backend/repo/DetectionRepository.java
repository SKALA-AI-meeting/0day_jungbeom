package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Detection;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DetectionRepository extends JpaRepository<Detection, Long> {
    java.util.List<Detection> findBySessionId(String sessionId); java.util.Optional<Detection> findBySessionIdAndMsgIdx(String sessionId, int msgIdx);
}
