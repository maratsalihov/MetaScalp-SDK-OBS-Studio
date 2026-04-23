import threading
import time

def patched_connect(self):
    import websocket
    import json
    import socket
    import logging
    
    LOG = logging.getLogger(__name__)
    
    try:
        # Create WebSocket without SSL context fix
        if hasattr(websocket, 'WebSocket'):
            self.ws = websocket.WebSocket(skip_utf8_validation=True)
        else:
            self.ws = websocket.create_connection("")
        
        url = f"ws://{self.host}:{self.port}"
        LOG.info(f"Connecting to {url}...")
        
        # Set longer timeout
        self.ws.settimeout(10)
        self.ws.connect(url)
        LOG.info("Connected!")
        
        # FIXED: Read the Hello message first
        LOG.debug("Waiting for Hello...")
        result = self.ws.recv()
        LOG.debug(f"Got Hello: {result}")
        
        if not result:
            raise Exception("Empty response to Hello")
        
        result_json = json.loads(result)
        
        if result_json.get('op') != 0:
            raise Exception(f"Invalid Hello message op: {result_json.get('op')}")
        
        self.server_version = result_json['d'].get('obsWebSocketVersion')
        
        # Build authentication
        if result_json['d'].get('authentication'):
            auth = self._build_auth_string(
                result_json['d']['authentication']['salt'],
                result_json['d']['authentication']['challenge']
            )
        else:
            auth = ''
        
        # Send Identify
        ident = {
            "op": 1,
            "d": {
                "rpcVersion": 1,
                "authentication": auth,
                "eventSubscriptions": 1023
            }
        }
        LOG.debug(f"Sending Identify: {ident}")
        self.ws.send(json.dumps(ident))
        
        # FIXED: Wait for response
        LOG.debug("Waiting for Identified...")
        result = self.ws.recv()
        LOG.debug(f"Got Identified: {result}")
        
        if not result:
            raise Exception("Empty response to Identify, password may be incorrect")
        
        result_json = json.loads(result)
        if result_json.get('op') != 2:
            raise Exception(result_json.get('error', "Invalid Identified message"))
        
        self.connected = True
        self._identify_success = True
        LOG.info("Authentication successful!")
        
    except Exception as e:
        self.connected = False
        raise e