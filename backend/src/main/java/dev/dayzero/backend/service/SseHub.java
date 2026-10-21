package dev.dayzero.backend.service;

import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.UnaryOperator;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Relays agent progress events to browsers (publish/subscribe). The agent never knows which screen listens.
 * TOKEN events are kept only in memory for live replay; other events are also stored in task_events.
 */
@Component
public class SseHub {
    public record Ev(int seq, String type, Object data) {}

    private record Sub(SseEmitter em, UnaryOperator<Ev> view) {}

    private final Map<String, List<Sub>> emitters = new ConcurrentHashMap<>();
    private final Map<String, List<Ev>> live = new ConcurrentHashMap<>();

    public SseEmitter subscribe(String taskId, List<Ev> replay, boolean finished) {
        return subscribe(taskId, replay, finished, UnaryOperator.identity());
    }

    /** `view` may rewrite or drop (return null) events for this subscriber, e.g. hide agent internals from candidates. */
    public SseEmitter subscribe(String taskId, List<Ev> replay, boolean finished, UnaryOperator<Ev> view) {
        SseEmitter em = new SseEmitter(10 * 60_000L);
        List<Ev> buffered = live.getOrDefault(taskId, List.of());
        try {
            for (Ev e : (buffered.isEmpty() ? replay : buffered)) send(em, view.apply(e));
        } catch (IOException ex) {
            em.completeWithError(ex);
            return em;
        }
        if (finished) {
            em.complete();
            return em;
        }
        Sub sub = new Sub(em, view);
        emitters.computeIfAbsent(taskId, k -> new CopyOnWriteArrayList<>()).add(sub);
        Runnable drop = () -> emitters.getOrDefault(taskId, List.of()).remove(sub);
        em.onCompletion(drop);
        em.onTimeout(drop);
        em.onError(t -> drop.run());
        return em;
    }

    public void publish(String taskId, Ev e, boolean terminal) {
        live.computeIfAbsent(taskId, k -> new CopyOnWriteArrayList<>()).add(e);
        for (Sub sub : emitters.getOrDefault(taskId, List.of())) {
            try {
                send(sub.em(), sub.view().apply(e));
                if (terminal) sub.em().complete();
            } catch (Exception ex) {
                sub.em().completeWithError(ex);
            }
        }
        if (terminal) {
            emitters.remove(taskId);
            live.remove(taskId);
        }
    }

    private static void send(SseEmitter em, Ev e) throws IOException {
        if (e == null) return;
        em.send(SseEmitter.event().id(String.valueOf(e.seq())).name(e.type()).data(e.data() == null ? Map.of() : e.data()));
    }
}
