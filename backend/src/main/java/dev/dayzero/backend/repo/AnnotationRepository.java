package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Annotation;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AnnotationRepository extends JpaRepository<Annotation, Long> {
    java.util.List<Annotation> findBySessionIdOrderByIdAsc(String sessionId); java.util.List<Annotation> findBySessionIdAndMsgIdxGreaterThanEqualOrderByIdAsc(String sessionId, int msgIdx); long countBySessionId(String sessionId); java.util.Optional<Annotation> findByIdAndSessionId(Long id, String sessionId);
}
