#!/bin/sh
# Start the emulator in the background, wait for it to be ready,
# then seed test phone numbers.

firebase emulators:start --only auth,storage --project fervora-local &
EMULATOR_PID=$!

# Wait for emulator to be ready
echo "Waiting for Auth emulator..."
until curl -sf http://localhost:9099/ > /dev/null 2>&1; do
  sleep 1
done
echo "Auth emulator is ready."

# Seed test phone numbers (+13609695450 through +13609695459, code: 123456)
curl -s -X PATCH \
  'http://localhost:9099/emulator/v1/projects/fervora-local/config' \
  -H 'Content-Type: application/json' \
  -d '{
    "signIn": { "allowDuplicateEmails": false },
    "phoneAuth": {
      "testPhoneNumbers": {
        "+13609695450": "123456",
        "+13609695451": "123456",
        "+13609695452": "123456",
        "+13609695453": "123456",
        "+13609695454": "123456",
        "+13609695455": "123456",
        "+13609695456": "123456",
        "+13609695457": "123456",
        "+13609695458": "123456",
        "+13609695459": "123456"
      }
    }
  }'

echo ""
echo "Test phone numbers seeded."

# Keep the emulator running in the foreground
wait $EMULATOR_PID
