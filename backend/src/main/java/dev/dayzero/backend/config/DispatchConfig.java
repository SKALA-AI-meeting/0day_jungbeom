package dev.dayzero.backend.config;

import dev.dayzero.backend.service.AgentClient;
import dev.dayzero.backend.service.Json;
import dev.dayzero.backend.service.TaskDispatcher;
import java.util.Map;
import org.springframework.amqp.core.*;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DispatchConfig {
    public static final String EXCHANGE = "dayzero.tasks";
    public static final String QUEUE = "agent.tasks";
    public static final String DLX = "dayzero.tasks.dlx";
    public static final String DLQ = "agent.tasks.dlq";

    @Bean
    @ConditionalOnProperty(name = "dayzero.dispatch", havingValue = "http", matchIfMissing = true)
    TaskDispatcher httpDispatcher(AgentClient agent) {
        return agent::submit;
    }

    @Bean
    @ConditionalOnProperty(name = "dayzero.dispatch", havingValue = "none")
    TaskDispatcher recordingDispatcher() {
        return new TaskDispatcher.Recording();
    }

    /** Bonus (대기열): tasks go through RabbitMQ; the agent retries and dead-letters failures. */
    @Configuration
    @ConditionalOnProperty(name = "dayzero.dispatch", havingValue = "rabbit")
    static class Rabbit {
        @Bean DirectExchange tasksExchange() { return new DirectExchange(EXCHANGE, true, false); }
        @Bean DirectExchange deadLetterExchange() { return new DirectExchange(DLX, true, false); }
        @Bean Queue tasksQueue() { return QueueBuilder.durable(QUEUE).withArgument("x-dead-letter-exchange", DLX).withArgument("x-dead-letter-routing-key", DLQ).build(); }
        @Bean Queue deadLetterQueue() { return QueueBuilder.durable(DLQ).build(); }
        @Bean Binding tasksBinding() { return BindingBuilder.bind(tasksQueue()).to(tasksExchange()).with(QUEUE); }
        @Bean Binding dlqBinding() { return BindingBuilder.bind(deadLetterQueue()).to(deadLetterExchange()).with(DLQ); }

        @Bean
        TaskDispatcher rabbitDispatcher(RabbitTemplate rabbit, Json json) {
            return m -> rabbit.convertAndSend(EXCHANGE, QUEUE, json.write(m), msg -> {
                msg.getMessageProperties().setContentType("application/json");
                msg.getMessageProperties().setHeader("x-attempt", 1);
                return msg;
            });
        }
    }
}
