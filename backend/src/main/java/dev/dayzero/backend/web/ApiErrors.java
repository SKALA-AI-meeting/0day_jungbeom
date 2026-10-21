package dev.dayzero.backend.web;

import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

/** Errors as {"detail": "..."} so the UI can show what went wrong and how to fix it. */
@RestControllerAdvice
public class ApiErrors {
    @ExceptionHandler(ResponseStatusException.class)
    ResponseEntity<Map<String, Object>> status(ResponseStatusException e) {
        return ResponseEntity.status(e.getStatusCode()).body(Map.of("detail", e.getReason() == null ? "요청을 처리하지 못했어요." : e.getReason()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<Map<String, Object>> invalid(MethodArgumentNotValidException e) {
        var f = e.getBindingResult().getFieldError();
        return ResponseEntity.badRequest().body(Map.of("detail", f == null ? "입력값을 확인해 주세요." : f.getField() + ": " + f.getDefaultMessage()));
    }
}
