package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Observation;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ObservationRepository extends JpaRepository<Observation, Long> {
    java.util.List<Observation> findBySessionIdOrderByIdAsc(String sessionId); long countBySessionId(String sessionId);
}
