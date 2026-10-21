package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

@Entity
@Table(name = "invites")
public class Invite {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @ManyToOne(optional = false) @JoinColumn(name = "company_id") public Company company;
    public String token;
    public String alias;
    public String email;
    public boolean reusable;
    public OffsetDateTime expiresAt;
    public OffsetDateTime usedAt;
    public OffsetDateTime createdAt = OffsetDateTime.now();
}
