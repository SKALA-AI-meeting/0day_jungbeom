package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** A candidate's markup on a shared work item: a line range and/or a quote, a kind (question risk suggest ok) and a note. */
@Entity
@Table(name = "annotations")
public class Annotation {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @Column(name = "session_id") public String sessionId;
    public String artifactId;
    public Integer lineStart;
    public Integer lineEnd;
    public String quote;
    public String kind;
    public String text;
    public int msgIdx;
    public OffsetDateTime createdAt = OffsetDateTime.now();
}
