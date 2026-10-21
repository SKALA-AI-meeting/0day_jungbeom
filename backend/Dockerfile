FROM eclipse-temurin:21-jdk AS build
WORKDIR /src
COPY gradlew settings.gradle build.gradle ./
COPY gradle gradle
RUN ./gradlew --no-daemon -q dependencies > /dev/null
COPY src src
RUN ./gradlew --no-daemon -q bootJar -x test

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/build/libs/*.jar app.jar
# 8080 public API, 8081 internal API (/internal/**) — compose publishes only 8080
EXPOSE 8080 8081
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
