import websocket
import json

ws = websocket.WebSocket(skip_utf8_validation=True)
ws.settimeout(10)
url = "ws://100.101.91.69:4455"
ws.connect(url)

# Hello
hello = ws.recv()
data = json.loads(hello)
print(f"Hello: {data['d']['obsStudioVersion']}")

# No password authentication
identify = {"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 1023}}
ws.send(json.dumps(identify))

import time
time.sleep(1)
result = ws.recv()
print(f"Result: {result}")

ws.close()