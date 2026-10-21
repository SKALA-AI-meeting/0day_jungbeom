package dev.dayzero.backend.domain;

import jakarta.persistence.*;

@Entity
@Table(name = "detections")
public class Detection {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    @Column(name = "session_id") public String sessionId;
    public int msgIdx;
    @Column(columnDefinition = "text") public String docJson;
}
