FROM node:20-alpine

RUN apk add --no-cache openjdk21-jre-headless && \
    npm install -g firebase-tools

WORKDIR /firebase

COPY firebase.json .
COPY storage.rules .

EXPOSE 4000 9099 9199

CMD ["firebase", "emulators:start", "--project", "fervora-local"]
