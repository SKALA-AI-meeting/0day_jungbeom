package dev.dayzero.backend.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("dayzero")
public record AppProperties(
        int internalPort,
        String internalKey,
        String jwtSecret,
        int jwtTtlMinutes,
        String agentUrl,
        String dispatch,
        int inviteTtlHours,
        boolean seedDemo) {
}
