package dev.dayzero.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("dayzero")
public record AppProperties(
        int internalPort,
        String internalKey,
        String jwtSecret,
        int jwtTtlMinutes,
        String agentUrl,
        String dispatch,
        int inviteTtlHours,
        boolean seedDemo,
        // TaskWatchdog: QUEUED / RUNNING tasks without progress this long are failed (sweep every task-watchdog-interval-ms)
        @DefaultValue("10") int taskStaleMinutes) {
}
