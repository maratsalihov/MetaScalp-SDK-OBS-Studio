import websocket
import json
import time

host = "127.0.0.1"
port = 4455

ws = websocket.WebSocket(skip_utf8_validation=True)
ws.settimeout(5)

try:
    ws.connect(f"ws://{host}:{port}")
    hello = json.loads(ws.recv())
    print(f"OBS: {hello['d'].get('obsStudioVersion')}")
    
    # Identify (no auth needed now)
    ws.send(json.dumps({'op': 1, 'd': {'rpcVersion': 1}}))
    
    identified = ws.recv()
    data = json.loads(identified)
    print(f"Identified: {data}")
    
    # Check if we got op:2 (Identified event) - success!
    if data.get('op') == 2:
        print("IDENTIFY SUCCESS!")
        
        # StartRecord
        ws.send(json.dumps({'op': 6, 'd': {'requestType': 'StartRecord', 'requestId': '1'}}))
        resp = ws.recv()
        print(f"StartRecord: {resp}")
        
        rdata = json.loads(resp)
        result = rdata.get('d', {}).get('requestStatus', {}).get('result', False)
        print(f"StartRecord result: {result}")
        
        time.sleep(2)
        
        ws.send(json.dumps({'op': 6, 'd': {'requestType': 'StopRecord', 'requestId': '2'}}))
        resp = ws.recv()
        print(f"StopRecord: {resp}")
        
        print("SUCCESS!")
    
    ws.close()
    
except Exception as e:
    print(f"ERROR: {e}")