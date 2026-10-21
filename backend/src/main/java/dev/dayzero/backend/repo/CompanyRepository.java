package dev.dayzero.backend.repo;

import dev.dayzero.backend.domain.Company;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CompanyRepository extends JpaRepository<Company, Long> {
    
}
