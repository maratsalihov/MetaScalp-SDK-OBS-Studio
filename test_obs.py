import websocket
import json
import logging
import time

logger = logging.getLogger(__name__)


def test_without_password():
    """Test connection without password"""
    ws = websocket.WebSocket(skip_utf8_validation=True)
    ws.settimeout(10)
    url = "ws://100.101.91.69:4455"
    print(f"Connecting to {url}...")
    ws.connect(url)
    
    # Hello
    hello = ws.recv()
    data = json.loads(hello)
    print(f"Hello: {data['d']['obsStudioVersion']}, {data['d']['obsWebSocketVersion']}")
    
    # Check if auth required
    auth_required = 'authentication' in data.get('d', {})
    print(f"Authentication required: {auth_required}")
    
    if auth_required:
        # Build auth
        import hashlib
        import hmac
        import base64
        
        password = 'k8q9Tpt9oQIAVLU5'
        salt = data['d']['authentication']['salt']
        challenge = data['d']['authentication']['challenge']
        
        secret = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), 60000)
        auth = hmac.new(base64.b64decode(challenge), secret, hashlib.sha256).digest()
        auth_str = base64.b64encode(auth).decode()
        
        print(f"Auth: {auth_str}")
        
        # Send Identify with empty password
        identify = {"op": 1, "d": {"rpcVersion": 1, "authentication": "", "eventSubscriptions": 1023}}
        ws.send(json.dumps(identify))
    else:
        identify = {"op": 1, "d": {"rpcVersion": 1, "eventSubscriptions": 1023}}
        ws.send(json.dumps(identify))
    
    time.sleep(0.5)
    result = ws.recv()
    print(f"Result: {repr(result)}")
    
    ws.close()


if __name__ == "__main__":
    test_without_password()