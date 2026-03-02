FROM node:20-slim

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
RUN npm install -g firebase-tools

# Create a minimal firebase.json that enables only the Auth emulator
WORKDIR /app
RUN echo '{ \
  "emulators": { \
    "auth": { \
      "host": "0.0.0.0", \
      "port": 9099 \
    }, \
    "ui": { \
      "enabled": true, \
      "host": "0.0.0.0", \
      "port": 4000 \
    } \
  } \
}' > firebase.json

COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

EXPOSE 9099 4000

CMD ["/app/start.sh"]
