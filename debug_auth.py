import hashlib
import hmac
import base64
import json

# Test authentication algorithm
password = 'k8q9Tpt9oQIAVLU5'
salt = 'KqjnCfhCebthnzC3lQvHZj7obduP5iVZJpi9vSLZ2FI='
challenge = 'RTu343Vxyi+QsxjiG2idwVSqjLS94sycpU6/IeFEMUA='

print("=== OBS WebSocket Authentication Test ===")
print(f"Password: {password}")
print(f"Salt: {salt}")
print(f"Challenge: {challenge}")

# Step 1: Decode salt and challenge
salt_bytes = base64.b64decode(salt)
challenge_bytes = base64.b64decode(challenge)

print(f"\nDecoded salt ({len(salt_bytes)} bytes): {salt_bytes.hex()}")
print(f"Decoded challenge ({len(challenge_bytes)} bytes): {challenge_bytes.hex()}")

# Step 2: Generate secret using PBKDF2-HMAC-SHA256
# Using password as input, salt as salt, 60000 iterations
secret = hashlib.pbkdf2_hmac('sha256', password.encode(), salt_bytes, 60000)
print(f"\nSecret (PBKDF2): {secret.hex()} ({len(secret)} bytes)")

# Step 3: Generate authentication string using HMAC-SHA256
# key = challenge, data = secret
auth = hmac.new(challenge_bytes, secret, hashlib.sha256).digest()
auth_string = base64.b64encode(auth).decode()

print(f"\nAuth string: {auth_string}")
print(f"Auth (HMAC): {auth}")

print("\n=== Full Python test ===")

import websocket

ws = websocket.WebSocket(skip_utf8_validation=True)
ws.settimeout(10)
ws.connect("ws://100.101.91.69:4455")

# Get Hello
hello = json.loads(ws.recv())
auth_data = hello['d'].get('authentication', {})
print(f"Server version: {hello['d']['obsStudioVersion']}")

# Build auth with received salt/challenge
new_salt = auth_data['salt']
new_challenge = auth_data['challenge']

new_secret = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(new_salt), 60000)
new_auth = hmac.new(base64.b64decode(new_challenge), new_secret, hashlib.sha256).digest()
new_auth_string = base64.b64encode(new_auth).decode()

print(f"New auth: {new_auth_string}")

# Send Identify
identify = {"op": 1, "d": {"rpcVersion": 1, "authentication": new_auth_string, "eventSubscriptions": 1023}}
ws.send(json.dumps(identify))

import time
time.sleep(0.2)

# Read any pending data
ws.settimeout(0.5)
try:
    result = ws.recv()
    print(f"Response: {result}")
except:
    print("No response")

ws.close()