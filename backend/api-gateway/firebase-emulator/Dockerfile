FROM eclipse-temurin:21-jre AS jre
FROM node:20-slim

# Copy JDK 21 from Temurin image
COPY --from=jre /opt/java/openjdk /opt/java/openjdk
ENV JAVA_HOME=/opt/java/openjdk
ENV PATH="${JAVA_HOME}/bin:${PATH}"

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN npm install -g firebase-tools

# Create a minimal firebase.json that enables only the Auth emulator
WORKDIR /app
RUN echo '{ \
  "storage": { \
    "rules": "storage.rules" \
  }, \
  "emulators": { \
    "auth": { \
      "host": "0.0.0.0", \
      "port": 9099 \
    }, \
    "storage": { \
      "host": "0.0.0.0", \
      "port": 9199 \
    }, \
    "ui": { \
      "enabled": true, \
      "host": "0.0.0.0", \
      "port": 4000 \
    } \
  } \
}' > firebase.json

COPY storage.rules /app/storage.rules

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 9099 9199 4000

CMD ["/app/start.sh"]
