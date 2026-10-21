package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Invite;
import org.springframework.data.jpa.repository.JpaRepository;

public interface InviteRepository extends JpaRepository<Invite, Long> {
    java.util.Optional<Invite> findByToken(String token); java.util.List<Invite> findByCompanyIdOrderByCreatedAtDesc(Long companyId);
}
