package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.time.OffsetDateTime;

/** An agent job (START | TURN | REPORT). Created with 202, executed by the agent, progress relayed as SSE. */
@Entity
@Table(name = "ai_tasks")
public class AiTask {
    @Id public String id;
    public String sessionId;
    public Long companyId;
    public String type;
    public String status = "QUEUED"; // QUEUED RUNNING WAITING_APPROVAL DONE FAILED REJECTED
    public String threadId;
    @Column(columnDefinition = "text") public String payloadJson;
    @Column(columnDefinition = "text") public String resultJson;
    @Column(columnDefinition = "text") public String error;
    @Column(columnDefinition = "text") public String traceJson;
    public int attempts = 0;
    public String createdBy;
    public OffsetDateTime createdAt = OffsetDateTime.now();
    public OffsetDateTime updatedAt = OffsetDateTime.now();

    public boolean finished() {
        return "DONE".equals(status) || "FAILED".equals(status) || "REJECTED".equals(status);
    }
}
