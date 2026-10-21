package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.SessionArtifact;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SessionArtifactRepository extends JpaRepository<SessionArtifact, SessionArtifact.Key> {
    java.util.List<SessionArtifact> findBySessionIdOrderByOrdAsc(String sessionId); java.util.Optional<SessionArtifact> findBySessionIdAndArtifactId(String sessionId, String artifactId);
}
