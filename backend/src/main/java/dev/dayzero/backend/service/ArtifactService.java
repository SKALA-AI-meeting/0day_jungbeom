package dev.dayzero.backend.service;

import dev.dayzero.backend.domain.Annotation;
import dev.dayzero.backend.domain.ChatSession;
import dev.dayzero.backend.domain.SessionArtifact;
import dev.dayzero.backend.repo.AnnotationRepository;
import dev.dayzero.backend.repo.ChatSessionRepository;
import dev.dayzero.backend.repo.MessageRepository;
import dev.dayzero.backend.repo.SessionArtifactRepository;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.regex.Pattern;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Shared work items (같이 확인할 과제) and the candidate's markups on them (api-contract §1).
 * The agent seeds the items at START; the candidate marks them up; personas and the observer read both.
 * Internal shapes are snake_case (agent), public shapes camelCase (browser). Planted checkpoints never get here.
 * Adding or removing a markup changes the admin analytics (planted checkpoints spotted), so it bumps state_rev.
 */
@Service
public class ArtifactService {
    public static final Set<String> KINDS = Set.of("design", "result", "code");
    public static final Set<String> OWNERS = Set.of("lead", "peer", "team");
    public static final Set<String> MARKS = Set.of("question", "risk", "suggest", "ok");
    public static final int MAX_ANNOTATIONS = 40;
    private static final Pattern ID = Pattern.compile("[A-Za-z0-9_-]{1,16}");

    private final SessionArtifactRepository artifacts;
    private final AnnotationRepository annotations;
    private final MessageRepository messages;
    private final ChatSessionRepository sessions;

    public ArtifactService(SessionArtifactRepository artifacts, AnnotationRepository annotations, MessageRepository messages, ChatSessionRepository sessions) {
        this.artifacts = artifacts; this.annotations = annotations; this.messages = messages; this.sessions = sessions;
    }

    // ---------------------------------------------------------------- seeding (internal init)
    /** Replace-all, idempotent: the same list twice leaves the same rows. Markups on items that disappear go with them. */
    @Transactional
    public void replaceAll(String sessionId, Object raw) {
        if (!(raw instanceof List<?> list)) throw bad("artifacts는 목록이어야 해요.");
        Map<String, SessionArtifact> existing = new HashMap<>();
        for (SessionArtifact a : artifacts.findBySessionIdOrderByOrdAsc(sessionId)) existing.put(a.artifactId, a);
        List<SessionArtifact> next = new ArrayList<>();
        Set<String> ids = new HashSet<>();
        for (Object o : list) {
            if (!(o instanceof Map<?, ?> m)) throw bad("과제 항목은 객체여야 해요.");
            String id = str(m.get("id"));
            if (id == null || !ID.matcher(id).matches()) throw bad("과제 id가 올바르지 않아요 (영문·숫자 16자 이내): " + id);
            if (!ids.add(id)) throw bad("과제 id가 겹쳐요: " + id);
            SessionArtifact a = existing.getOrDefault(id, new SessionArtifact());
            a.sessionId = sessionId;
            a.artifactId = id;
            a.ord = next.size();
            a.kind = oneOf(m.get("kind"), KINDS, "kind", id);
            a.owner = oneOf(m.get("owner") == null ? "team" : m.get("owner"), OWNERS, "owner", id);
            a.title = text(m.get("title"), 80, true, "title", id);
            a.status = text(m.get("status"), 20, false, "status", id);
            a.summary = text(m.get("summary"), 160, false, "summary", id);
            a.lang = text(m.get("lang"), 20, false, "lang", id);
            a.body = Objects.requireNonNullElse(text(m.get("body"), 6000, false, "body", id), "");
            next.add(a);
        }
        for (SessionArtifact old : existing.values()) {
            if (ids.contains(old.artifactId)) continue;
            artifacts.delete(old);
            annotations.deleteAll(annotations.findBySessionIdOrderByIdAsc(sessionId).stream().filter(n -> n.artifactId.equals(old.artifactId)).toList());
        }
        artifacts.saveAll(next);
    }

    // ---------------------------------------------------------------- internal shapes (agent via business-mcp)
    /** Full items, in seeding order (state.artifacts). */
    public List<Map<String, Object>> internalList(String sessionId) {
        return artifacts.findBySessionIdOrderByOrdAsc(sessionId).stream().map(this::internal).toList();
    }

    /** Item table without bodies: GET /internal/sessions/{id}/artifacts. */
    public List<Map<String, Object>> summaries(String sessionId) {
        Map<String, Long> count = new HashMap<>();
        for (Annotation n : annotations.findBySessionIdOrderByIdAsc(sessionId)) count.merge(n.artifactId, 1L, Long::sum);
        return artifacts.findBySessionIdOrderByOrdAsc(sessionId).stream().map(a -> {
            Map<String, Object> m = header(a);
            m.put("line_count", a.lineCount());
            m.put("annotation_count", count.getOrDefault(a.artifactId, 0L));
            return m;
        }).toList();
    }

    /** One full item + its markups: GET /internal/sessions/{id}/artifacts/{artifactId}. */
    public Map<String, Object> internalOne(String sessionId, String artifactId) {
        SessionArtifact a = find(sessionId, artifactId);
        Map<String, Object> m = internal(a);
        m.put("annotations", annotations.findBySessionIdOrderByIdAsc(sessionId).stream().filter(n -> n.artifactId.equals(a.artifactId)).map(this::internal).toList());
        return m;
    }

    /** Markups with msg_idx >= sinceIdx, id asc (state.annotations uses 0). */
    public List<Map<String, Object>> internalAnnotations(String sessionId, int sinceIdx) {
        List<Annotation> all = sinceIdx <= 0 ? annotations.findBySessionIdOrderByIdAsc(sessionId)
                : annotations.findBySessionIdAndMsgIdxGreaterThanEqualOrderByIdAsc(sessionId, sinceIdx);
        return all.stream().map(this::internal).toList();
    }

    // ---------------------------------------------------------------- public shapes (browser)
    /** Items with their markups nested (candidate and admin session views). */
    public List<Map<String, Object>> publicList(String sessionId) {
        Map<String, List<Map<String, Object>>> byArtifact = new HashMap<>();
        for (Annotation n : annotations.findBySessionIdOrderByIdAsc(sessionId))
            byArtifact.computeIfAbsent(n.artifactId, k -> new ArrayList<>()).add(publicAnnotation(n));
        return artifacts.findBySessionIdOrderByOrdAsc(sessionId).stream().map(a -> {
            Map<String, Object> m = header(a);
            m.put("body", a.body);
            m.put("annotations", byArtifact.getOrDefault(a.artifactId, List.of()));
            return m;
        }).toList();
    }

    public Map<String, Object> publicAnnotation(Annotation n) {
        Map<String, Object> anchor = new LinkedHashMap<>();
        anchor.put("lineStart", n.lineStart); anchor.put("lineEnd", n.lineEnd); anchor.put("quote", n.quote);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", n.id); m.put("artifactId", n.artifactId); m.put("anchor", anchor); m.put("kind", n.kind); m.put("text", n.text);
        m.put("msgIdx", n.msgIdx); m.put("createdAt", n.createdAt);
        return m;
    }

    // ---------------------------------------------------------------- candidate markups (checked in contract order)
    @Transactional
    public Annotation annotate(ChatSession s, String artifactId, Integer lineStart, Integer lineEnd, String quote, String kind, String text) {
        if (!"active".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 종료된 세션이에요.");
        SessionArtifact a = find(s.id, artifactId);
        if (kind == null || !MARKS.contains(kind)) throw bad("마크업 종류는 질문·우려·제안·확인함 중에서 골라 주세요.");
        String note = text == null ? "" : text.strip();
        if (note.isEmpty() || note.length() > 500) throw bad("마크업 내용은 1~500자로 적어 주세요.");
        String q = quote == null || quote.isBlank() ? null : quote.strip();
        if (lineStart == null && lineEnd != null) throw bad("줄 범위는 시작 줄부터 정해 주세요.");
        if (lineStart == null && q == null) throw bad("표시할 줄 범위나 인용할 문장을 정해 주세요.");
        Integer end = lineStart == null ? null : Objects.requireNonNullElse(lineEnd, lineStart);
        if (lineStart != null && (lineStart < 1 || end < lineStart || end > a.lineCount()))
            throw bad("줄 범위가 올바르지 않아요 (1~" + a.lineCount() + "줄, 시작 ≤ 끝).");
        if (q != null && q.length() > 300) throw bad("인용은 300자까지 가능해요.");
        if (q != null && !a.body.contains(q)) throw bad("인용한 문장이 과제 본문에 없어요.");
        if (annotations.countBySessionId(s.id) >= MAX_ANNOTATIONS)
            throw new ResponseStatusException(HttpStatus.CONFLICT, "마크업은 세션마다 " + MAX_ANNOTATIONS + "개까지 남길 수 있어요.");
        Annotation n = new Annotation();
        n.sessionId = s.id; n.artifactId = a.artifactId; n.lineStart = lineStart; n.lineEnd = end; n.quote = q;
        n.kind = kind; n.text = note; n.msgIdx = (int) messages.countBySessionId(s.id);
        Annotation saved = annotations.save(n);
        sessions.bumpRev(s.id);
        return saved;
    }

    @Transactional
    public void deleteAnnotation(ChatSession s, Long annotationId) {
        Annotation n = annotations.findByIdAndSessionId(annotationId, s.id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "마크업을 찾을 수 없어요."));
        if (!"active".equals(s.status)) throw new ResponseStatusException(HttpStatus.CONFLICT, "이미 종료된 세션이에요.");
        annotations.delete(n);
        sessions.bumpRev(s.id);
    }

    // ---------------------------------------------------------------- helpers
    private SessionArtifact find(String sessionId, String artifactId) {
        return artifacts.findBySessionIdAndArtifactId(sessionId, artifactId == null ? "" : artifactId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "과제를 찾을 수 없어요."));
    }

    private Map<String, Object> header(SessionArtifact a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", a.artifactId); m.put("kind", a.kind); m.put("title", a.title); m.put("owner", a.owner);
        m.put("status", a.status); m.put("summary", a.summary); m.put("lang", a.lang);
        return m;
    }

    private Map<String, Object> internal(SessionArtifact a) {
        Map<String, Object> m = header(a);
        m.put("body", a.body);
        return m;
    }

    private Map<String, Object> internal(Annotation n) {
        Map<String, Object> anchor = new LinkedHashMap<>();
        anchor.put("line_start", n.lineStart); anchor.put("line_end", n.lineEnd); anchor.put("quote", n.quote);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", n.id); m.put("artifact_id", n.artifactId); m.put("anchor", anchor); m.put("kind", n.kind); m.put("text", n.text);
        m.put("msg_idx", n.msgIdx); m.put("created_at", epoch(n.createdAt));
        return m;
    }

    private static String oneOf(Object v, Set<String> allowed, String field, String id) {
        String s = str(v);
        if (s == null || !allowed.contains(s)) throw bad("과제 " + id + "의 " + field + " 값이 올바르지 않아요: " + s);
        return s;
    }

    private static String text(Object v, int max, boolean required, String field, String id) {
        String s = str(v);
        if (s != null && s.isBlank() && !"body".equals(field)) s = null;
        if (required && s == null) throw bad("과제 " + id + "에 " + field + "가 필요해요.");
        if (s != null && s.length() > max) throw bad("과제 " + id + "의 " + field + "는 " + max + "자까지예요 (" + s.length() + "자).");
        return s;
    }

    private static ResponseStatusException bad(String msg) { return new ResponseStatusException(HttpStatus.BAD_REQUEST, msg); }
    private static String str(Object o) { return o == null ? null : String.valueOf(o); }
    private static double epoch(OffsetDateTime t) { return t.toInstant().toEpochMilli() / 1000.0; }
}
