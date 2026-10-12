import socket
import threading
from trust_engine import TrustEngine
from trust_layer.hl7_ingest import parse_hl7_message, validate_hl7_structure

# MLLP Constants
MLLP_START_BLOCK = b'\x0b'
MLLP_END_BLOCK = b'\x1c\x0d'

class MLLPListener:
    def __init__(self, host='0.0.0.0', port=6661, engine=None):
        self.host = host
        self.port = port
        self.engine = engine or TrustEngine()
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"[MLLP] Listening on {self.host}:{self.port}...")

    def start(self):
        while True:
            client_socket, addr = self.server_socket.accept()
            print(f"[MLLP] Connection from {addr}")
            # Handle each connection in a separate thread
            threading.Thread(target=self._handle_client, args=(client_socket,), daemon=True).start()

    def _handle_client(self, client_socket):
        try:
            data = b''
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk
                # Check if we have a complete MLLP message
                if MLLP_END_BLOCK in data:
                    break
            
            if not data:
                return

            # Strip MLLP wrapper
            message = data.replace(MLLP_START_BLOCK, b'').replace(MLLP_END_BLOCK, b'').decode('utf-8').strip()
            print(f"[MLLP] Received message: {message[:50]}...")

            # Extract Message Control ID (MSH-10) for the ACK
            msh_segment = message.split('\r')[0]
            msh_fields = msh_segment.split('|')
            control_id = msh_fields[9] if len(msh_fields) > 9 else 'UNKNOWN'

            # 1. Validate structure
            is_valid, issues = validate_hl7_structure(message)
            if not is_valid:
                print(f"[MLLP] Invalid HL7: {issues}")
                self._send_ack(client_socket, control_id, 'AE', f"Invalid structure: {issues}")
                return

            # 2. Parse message to dictionary
            parsed = parse_hl7_message(message)
            record_dict = {
                'emirates_id': parsed.get('emirates_id'),
                'given_name': parsed.get('given_name', ''),
                'family_name': parsed.get('family_name', ''),
                'date_of_birth': parsed.get('date_of_birth', ''),
                'gender': parsed.get('gender', ''),
                'nationality': parsed.get('nationality', ''),
                'source_facility': parsed.get('source_facility', ''),
                'registration_date': parsed.get('registration_date', ''),
                'canonical_id': parsed.get('canonical_id', 'UNKNOWN'),
            }

            # 3. Run through the Trust Engine
            result = self.engine.assess_record(record_dict)
            decision = result['decision']
            reason = result['explanation']

            # 4. Send ACK back (AA = Accepted, AE = Error)
            # If it's quarantined, we still ACK the message (so the sender knows we got it), 
            # but the decision is logged.
            print(f"[MLLP] Decision: {decision} - {reason}")
            self._send_ack(client_socket, control_id, 'AA', f"Processed: {decision}")

        except Exception as e:
            print(f"[MLLP] Error: {e}")
        finally:
            client_socket.close()

    def _send_ack(self, client_socket, control_id, code, text):
        # Standard HL7 ACK structure
        ack = (
            f"MSH|^~\\&|TRUST_GATE|HOSPITAL|MIRTH|HOSPITAL|{self._get_timestamp()}||ACK^A01|{control_id}|P|2.5\r"
            f"MSA|{code}|{control_id}|{text}\r"
        )
        mllp_ack = MLLP_START_BLOCK + ack.encode('utf-8') + MLLP_END_BLOCK
        client_socket.sendall(mllp_ack)

    def _get_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime('%Y%m%d%H%M%S')

if __name__ == '__main__':
    engine = TrustEngine(region_profile='UAE (DOH)')
    listener = MLLPListener(host='0.0.0.0', port=6661, engine=engine)
    listener.start()
