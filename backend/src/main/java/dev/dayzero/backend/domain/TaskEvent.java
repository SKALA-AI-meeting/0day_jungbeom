package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

@Entity
@Table(name = "task_events")
public class TaskEvent {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY) public Long id;
    public String taskId;
    public int seq;
    public String type;
    @Column(columnDefinition = "text") public String dataJson;
    public OffsetDateTime createdAt = OffsetDateTime.now();
}
