package dev.dayzero.backend.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "observations")
public class Observation {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @Column(name = "session_id") public String sessionId;
    public String obsKey;
    public String competency;
    public String milestone;
    @Column(columnDefinition = "text") public String behavior;
    @Column(columnDefinition = "text") public String quote;
    public String signal;
    public int msgIdx;
}
