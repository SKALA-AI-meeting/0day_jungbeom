package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

@Entity
@Table(name = "messages")
public class Message {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @Column(name = "session_id") public String sessionId;
    public int idx;
    public String speaker;
    @Column(columnDefinition = "text") public String text;
    public String milestone;
    public String choice;
    @Column(columnDefinition = "text") public String sourcesJson;
    public OffsetDateTime createdAt = OffsetDateTime.now();
}
