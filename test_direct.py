import websocket
import json

ws = websocket.WebSocket(skip_utf8_validation=True)
ws.settimeout(10)
ws.connect("ws://100.101.91.69:4455")

# Hello
hello = json.loads(ws.recv())
print(f"Hello: {hello['d']['obsStudioVersion']}")

# Build auth
import hashlib
import hmac
import base64
password = 'k8q9Tpt9oQIAVLU5'
salt = hello['d']['authentication']['salt']
challenge = hello['d']['authentication']['challenge']

secret = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), 60000)
auth = hmac.new(base64.b64decode(challenge), secret, hashlib.sha256).digest()
auth_str = base64.b64encode(auth).decode()

# Identify
ws.send(json.dumps({
    "op": 1, 
    "d": {"rpcVersion": 1, "authentication": auth_str, "eventSubscriptions": 1023}
}))

# Skip waiting and try request directly
request = {"op": 6, "d": {"requestType": "GetVersion", "requestId": "1"}}
ws.send(json.dumps(request))

import time
time.sleep(1)
response = ws.recv()
print(f"Response: {response}")

ws.close()