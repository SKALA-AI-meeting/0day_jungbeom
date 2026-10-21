package dev.dayzero.backend.domain;

import jakarta.persistence.*;
import java.io.Serializable;
import java.util.Objects;

/** A shared work item of a session (design | result | code). Seeded by the agent at START; read-only for the candidate. */
@Entity
@Table(name = "session_artifacts")
@IdClass(SessionArtifact.Key.class)
public class SessionArtifact {
    @Id @Column(name = "session_id") public String sessionId;
    @Id public String artifactId;
    public int ord;
    public String kind;
    public String title;
    public String owner;
    public String status;
    public String summary;
    public String lang;
    @Column(columnDefinition = "text") public String body;

    /** Lines are body.split("\n") with trailing empty lines kept (same numbering as the agent and the browser). */
    public int lineCount() {
        return (body == null ? "" : body).split("\n", -1).length;
    }

    public static class Key implements Serializable {
        public String sessionId;
        public String artifactId;

        public Key() {}
        public Key(String sessionId, String artifactId) { this.sessionId = sessionId; this.artifactId = artifactId; }

        @Override public boolean equals(Object o) {
            return o instanceof Key k && Objects.equals(sessionId, k.sessionId) && Objects.equals(artifactId, k.artifactId);
        }
        @Override public int hashCode() { return Objects.hash(sessionId, artifactId); }
    }
}
