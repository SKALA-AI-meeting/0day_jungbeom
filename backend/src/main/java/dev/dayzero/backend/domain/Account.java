package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** A candidate account. Created by signup; the agent decides ACTIVE / REJECTED or asks an admin. */
@Entity
@Table(name = "accounts")
public class Account {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @ManyToOne(optional = false) @JoinColumn(name = "company_id") public Company company;
    @ManyToOne @JoinColumn(name = "invite_id") public Invite invite;
    public String email;
    public String passwordHash;
    public String nickname;
    public String desiredJob;
    public String industry;
    public int experienceYears;
    @Column(columnDefinition = "text") public String bio;
    public boolean consent;
    public String status = "PENDING_REVIEW"; // PENDING_REVIEW ACTIVE REJECTED REVIEW_ERROR
    @Column(columnDefinition = "text") public String reviewJson;
    public String reviewedBy;
    public OffsetDateTime reviewedAt;
    public OffsetDateTime createdAt = OffsetDateTime.now();
}
