package dev.dayzero.backend.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class Json {
    private final ObjectMapper om;
    public Json(ObjectMapper om) { this.om = om; }

    public String write(Object o) {
        if (o == null) return null;
        try { return om.writeValueAsString(o); } catch (Exception e) { throw new IllegalStateException(e); }
    }

    public Map<String, Object> map(String s) {
        if (s == null || s.isBlank()) return null;
        try { return om.readValue(s, new TypeReference<>() {}); } catch (Exception e) { throw new IllegalStateException(e); }
    }

    public List<Object> list(String s) {
        if (s == null || s.isBlank()) return List.of();
        try { return om.readValue(s, new TypeReference<>() {}); } catch (Exception e) { throw new IllegalStateException(e); }
    }

    public Object any(String s) {
        if (s == null || s.isBlank()) return null;
        try { return om.readValue(s, Object.class); } catch (Exception e) { throw new IllegalStateException(e); }
    }
}
