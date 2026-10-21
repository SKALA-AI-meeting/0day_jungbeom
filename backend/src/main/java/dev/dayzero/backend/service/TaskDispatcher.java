package dev.dayzero.backend.service;

import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/** How a stored task reaches the agent. Selected by dayzero.dispatch = http | rabbit | none. */
public interface TaskDispatcher {
    void dispatch(Map<String, Object> taskMessage);

    /** Test / offline mode: keeps messages in memory. */
    class Recording implements TaskDispatcher {
        public final List<Map<String, Object>> sent = new CopyOnWriteArrayList<>();
        @Override public void dispatch(Map<String, Object> m) { sent.add(m); }
    }
}
