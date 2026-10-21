package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** One candidate's assessment session. Conversation rules (status, milestones, choice) are enforced in SessionService. */
@Entity
@Table(name = "sessions")
public class ChatSession {
    @Id public String id;
    @ManyToOne(optional = false) @JoinColumn(name = "company_id") public Company company;
    @ManyToOne @JoinColumn(name = "invite_id") public Invite invite;
    @ManyToOne @JoinColumn(name = "account_id") public Account account;
    public String alias;
    public String scenarioId;
    public String status = "active";
    public int milestoneIdx = 0;
    public int turnsInMilestone = 0;
    @Column(columnDefinition = "text") public String conditionJson;
    @Column(columnDefinition = "text") public String choiceJson;
    @Column(columnDefinition = "text") public String milestoneLogJson = "[]";
    @Column(columnDefinition = "text") public String notes = "";
    @Column(columnDefinition = "text") public String reportJson;
    public String reportStatus = "none";
    public OffsetDateTime createdAt = OffsetDateTime.now();
    public OffsetDateTime endedAt;
}
