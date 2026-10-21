package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

@Entity
@Table(name = "admin_users")
public class AdminUser {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @ManyToOne(optional = false) @JoinColumn(name = "company_id") public Company company;
    public String email;
    public String passwordHash;
    public OffsetDateTime createdAt = OffsetDateTime.now();
}
