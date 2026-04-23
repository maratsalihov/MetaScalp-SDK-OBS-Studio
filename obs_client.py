import websocket
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


class OBSWebSocket:
    """Simple WebSocket client for OBS Studio v5+"""
    
    def __init__(self, host: str = "localhost", port: int = 4455, password: str = "", timeout: int = 10):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.ws: Optional[websocket.WebSocket] = None
        self.connected = False
    
    def connect(self) -> bool:
        """Connect to OBS WebSocket"""
        try:
            self.ws = websocket.WebSocket(skip_utf8_validation=True)
            self.ws.settimeout(self.timeout)
            url = f"ws://{self.host}:{self.port}"
            logger.info(f"Connecting to {url}...")
            self.ws.connect(url)
            
            # Receive Hello
            print("Waiting for Hello...")
            hello = self.ws.recv()
            print(f"Hello: {repr(hello[:200])}")
            
            if not hello:
                logger.error("Empty Hello response")
                return False
            
            data = json.loads(hello)
            if data.get('op') != 0:
                logger.error(f"Invalid Hello: {data}")
                return False
            
            # Build auth string
            auth = ''
            if data['d'].get('authentication'):
                auth = self._build_auth_string(
                    data['d']['authentication']['salt'],
                    data['d']['authentication']['challenge']
                )
            
            # Send Identify
            identify = {"op": 1, "d": {"rpcVersion": 1, "authentication": auth, "eventSubscriptions": 1023}}
            print(f"Sending Identify: {identify}")
            self.ws.send(json.dumps(identify))
            
            # Small delay before receiving
            time.sleep(0.5)
            
            # Receive Identified
            print("Waiting for Identified...")
            result = self.ws.recv()
            print(f"Identified: {repr(result[:200])}")
            
            if not result:
                logger.error("Empty Identified response")
                return False
            
            result_data = json.loads(result)
            if result_data.get('op') == 0 and result_data.get('t') == 'Identified':
                self.connected = True
                logger.info("Connected to OBS!")
                return True
            else:
                logger.error(f"Identify failed: {result_data}")
                return False
                
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.connected = False
            return False
    
    def _build_auth_string(self, salt: str, challenge: str) -> str:
        """Build authentication string"""
        import hashlib
        import hmac
        import base64
        
        secret = hashlib.pbkdf2_hmac('sha256', self.password.encode(), base64.b64decode(salt), 60000)
        auth = hmac.new(base64.b64decode(challenge), secret, hashlib.sha256).digest()
        return base64.b64encode(auth).decode()
    
    def call(self, request_type: str, **kwargs) -> dict:
        """Send request to OBS"""
        if not self.connected:
            raise Exception("Not connected")
        
        request = {"op": 6, "d": {"requestType": request_type, "requestId": "1", "requestData": kwargs}}
        self.ws.send(json.dumps(request))
        response = self.ws.recv()
        return json.loads(response)
    
    def disconnect(self):
        """Disconnect from OBS"""
        if self.ws:
            self.ws.close()
        self.connected = False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    ws = OBSWebSocket("100.101.91.69", 4455, "k8q9Tpt9oQIAVLU5")
    
    if ws.connect():
        print("Testing GetVersion...")
        result = ws.call("GetVersion")
        print(f"GetVersion: {result}")
        
        print("\nTesting GetRecordStatus...")
        result = ws.call("GetRecordStatus")
        print(f"GetRecordStatus: {result}")
        
        ws.disconnect()
    else:
        print("Failed to connect")