package dev.dayzero.backend.config;

import dev.dayzero.backend.security.AuthFilters;
import dev.dayzero.backend.security.JwtService;
import jakarta.servlet.DispatcherType;
import org.apache.catalina.connector.Connector;
import org.springframework.boot.web.embedded.tomcat.TomcatServletWebServerFactory;
import org.springframework.boot.web.server.WebServerFactoryCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain chain(HttpSecurity http, AppProperties props, JwtService jwt) throws Exception {
        http.csrf(c -> c.disable())
            .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .httpBasic(b -> b.disable()).formLogin(f -> f.disable())
            .exceptionHandling(e -> e.authenticationEntryPoint(new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .authorizeHttpRequests(a -> a
                .dispatcherTypeMatchers(DispatcherType.ASYNC, DispatcherType.ERROR).permitAll()
                .requestMatchers("/actuator/health", "/error").permitAll()
                .requestMatchers("/api/auth/signup", "/api/auth/login", "/api/meta", "/api/scenarios/**", "/api/invites/**").permitAll()
                .requestMatchers("/internal/**").hasRole("INTERNAL")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .addFilterBefore(new AuthFilters.PortGuard(props), UsernamePasswordAuthenticationFilter.class)
            .addFilterBefore(new AuthFilters.InternalKey(props), UsernamePasswordAuthenticationFilter.class)
            .addFilterBefore(new AuthFilters.Bearer(jwt), UsernamePasswordAuthenticationFilter.class);
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() { return new BCryptPasswordEncoder(); }

    /** Second connector for /internal/** — published only inside the docker network. */
    @Bean
    WebServerFactoryCustomizer<TomcatServletWebServerFactory> internalConnector(AppProperties props) {
        return f -> {
            Connector c = new Connector(TomcatServletWebServerFactory.DEFAULT_PROTOCOL);
            c.setPort(props.internalPort());
            f.addAdditionalTomcatConnectors(c);
        };
    }
}
