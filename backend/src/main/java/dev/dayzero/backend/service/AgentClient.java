package dev.dayzero.backend.service;

import dev.dayzero.backend.config.AppProperties;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.client.RestClient;
import org.springframework.web.server.ResponseStatusException;

/**
 * Internal HTTP to the FastAPI agent (Spring -> agent only; never an LLM call from Spring).
 * Catalog and view endpoints are pure functions over scenario data that lives with the agent.
 */
@Component
public class AgentClient {
    private final RestClient http;
    private final AtomicReference<Map<String, Object>> metaCache = new AtomicReference<>();
    private volatile long metaAt = 0;

    public AgentClient(AppProperties props) {
        var f = new SimpleClientHttpRequestFactory();
        f.setConnectTimeout(Duration.ofSeconds(3));
        f.setReadTimeout(Duration.ofSeconds(20));
        this.http = RestClient.builder().baseUrl(props.agentUrl()).requestFactory(f)
                .defaultHeader("X-Internal-Key", props.internalKey()).build();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> meta() {
        if (metaCache.get() == null || System.currentTimeMillis() - metaAt > 60_000) {
            metaCache.set(call(() -> http.get().uri("/agent/meta").retrieve().body(Map.class)));
            metaAt = System.currentTimeMillis();
        }
        return metaCache.get();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> scenario(String id) {
        try {
            return http.get().uri("/agent/scenarios/{id}", id).retrieve().body(Map.class);
        } catch (HttpClientErrorException.NotFound e) {
            return null;
        } catch (Exception e) {
            throw unavailable(e);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> view(String kind, Map<String, Object> state) {
        return call(() -> http.post().uri("/agent/views/{kind}", kind).body(state).retrieve().body(Map.class));
    }

    @SuppressWarnings("unchecked")
    public List<Map<String, Object>> rows(List<Map<String, Object>> states) {
        return call(() -> http.post().uri("/agent/views/admin-rows").body(states).retrieve().body(List.class));
    }

    public void submit(Map<String, Object> taskMessage) {
        http.post().uri("/agent/tasks").body(taskMessage).retrieve().toBodilessEntity();
    }

    /** Task types the agent serves: [{type, resumable, description}]. Empty when the agent is unreachable or predates it. */
    @SuppressWarnings("unchecked")
    public Optional<List<Map<String, Object>>> handlers() {
        try {
            return Optional.ofNullable(http.get().uri("/agent/handlers").retrieve().body(List.class));
        } catch (Exception e) {
            return Optional.empty();
        }
    }

    private <T> T call(java.util.function.Supplier<T> s) {
        try { return s.get(); } catch (Exception e) { throw unavailable(e); }
    }

    private ResponseStatusException unavailable(Exception e) {
        return new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "Agent 서버에 연결하지 못했어요.", e);
    }
}
