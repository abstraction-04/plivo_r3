import os
import json
import time
import urllib.request
from queue import Queue
from flask import Flask, request, Response, jsonify, send_from_directory
from dotenv import load_dotenv
import plivo

# Load environment configurations
load_dotenv()

app = Flask(__name__, static_folder='public')
PORT = int(os.environ.get('PORT', 5005))

# Initialize Plivo REST Client
client = plivo.RestClient(
    os.environ.get('PLIVO_AUTH_ID'),
    os.environ.get('PLIVO_AUTH_TOKEN')
)

# Active Server-Sent Events client queues
sse_queues = []

def send_event(event_type, data):
  """Broadcasts an event message to all connected SSE clients."""
  print(f"[Event] {event_type}: {data}")
  payload = {
      'type': event_type,
      'data': data,
      'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S.000Z', time.gmtime())
  }
  message = f"data: {json.dumps(payload)}\n\n"
  
  # Broadcast to all listeners
  for q in list(sse_queues):
    try:
      q.put(message)
    except Exception:
      if q in sse_queues:
        sse_queues.remove(q)

def get_public_url():
  """Auto-discovers the public ngrok tunnel URL or falls back to env variable."""
  public_url = os.environ.get('PUBLIC_URL')
  if public_url:
    return public_url
  try:
    req = urllib.request.Request('http://127.0.0.1:4040/api/tunnels')
    with urllib.request.urlopen(req, timeout=2) as response:
      data = json.loads(response.read().decode())
      for tunnel in data.get('tunnels', []):
        if tunnel.get('public_url', '').startswith('https'):
          return tunnel.get('public_url')
  except Exception:
    pass
  return None

# Serve Frontend static assets
@app.route('/')
def serve_index():
  return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
  return send_from_directory(app.static_folder, path)

# SSE Connection endpoint
@app.route('/api/events')
def events_stream():
  q = Queue()
  sse_queues.append(q)
  
  def stream():
    try:
      yield ":\n\n"  # Keep-alive padding
      while True:
        msg = q.get()
        yield msg
    except GeneratorExit:
      pass
    finally:
      if q in sse_queues:
        sse_queues.remove(q)
        
  return Response(stream(), mimetype='text/event-stream')

# Tunnel status checker endpoint
@app.route('/api/tunnel-status', methods=['GET'])
def tunnel_status():
  url = get_public_url()
  return jsonify({'publicUrl': url or None})

# Trigger outbound call
@app.post('/api/make-call')
def make_call():
  data = request.json or {}
  phone_number = data.get('phoneNumber')
  if not phone_number:
    return jsonify({'error': 'Phone number is required.'}), 400

  public_url = get_public_url()
  if not public_url:
    err_msg = 'Public tunnel URL (ngrok) not detected. Make sure ngrok is running (e.g. "ngrok http 5005")'
    send_event('call_error', {'error': err_msg})
    return jsonify({'error': err_msg}), 400

  source_number = os.environ.get('PLIVO_SOURCE_NUMBER')
  answer_url = f"{public_url}/plivo/answer"

  send_event('call_initiating', {'from': source_number, 'to': phone_number, 'answerUrl': answer_url})

  try:
    response = client.calls.create(
        from_=source_number,
        to_=phone_number,
        answer_url=answer_url,
        answer_method='POST'
    )
    call_uuid = getattr(response, 'call_uuid', None) or getattr(response, 'callUuid', None)
    if not call_uuid and hasattr(response, 'get'):
      call_uuid = response.get('call_uuid')
      
    request_uuid = getattr(response, 'api_id', None) or (response.get('api_id') if hasattr(response, 'get') else None)
    
    send_event('call_initiated', {'callUuid': call_uuid, 'requestUuid': request_uuid, 'to': phone_number})
    return jsonify({'success': True, 'callUuid': call_uuid})
  except Exception as err:
    print('Plivo call error:', err)
    send_event('call_error', {'error': str(err), 'to': phone_number})
    return jsonify({'error': str(err)}), 500

# Webhook: Call Answered
@app.post('/plivo/answer')
def plivo_answer():
  call_uuid = request.values.get('CallUUID')
  caller = request.values.get('From')
  to_number = request.values.get('To')
  
  send_event('call_answered', {'callUuid': call_uuid, 'from': caller, 'to': to_number})
  
  public_url = get_public_url()
  xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/verify-otp" method="POST" inputType="dtmf" numDigits="4" timeout="10" retries="1">
        <Speak>Welcome to Inspire Works. Please enter your four digit security code to proceed.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/answer</Redirect>
</Response>"""
  return Response(xml, mimetype='application/xml')

# Webhook: Verify 4-digit PIN
@app.post('/plivo/verify-otp')
def plivo_verify_otp():
  call_uuid = request.values.get('CallUUID')
  digits = request.values.get('Digits')
  
  send_event('otp_received', {'callUuid': call_uuid, 'digits': digits or 'none'})
  
  public_url = get_public_url()
  
  # Correct Hardcoded OTP is '1912' (DDMM birthdate)
  if digits == '1912':
    send_event('otp_success', {'callUuid': call_uuid})
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/select-language" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>Code verified successfully. For English, press 1. Para Español, presione 2.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-language</Redirect>
</Response>"""
  else:
    send_event('otp_failed', {'callUuid': call_uuid, 'digits': digits or 'none'})
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/verify-otp" method="POST" inputType="dtmf" numDigits="4" timeout="10" retries="1">
        <Speak>Incorrect security code. Please enter the correct four digit security code.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/answer</Redirect>
</Response>"""
  return Response(xml, mimetype='application/xml')

# Webhook Helper: Re-prompt Language selection
@app.post('/plivo/prompt-language')
def plivo_prompt_language():
  public_url = get_public_url()
  xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/select-language" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>For English, press 1. Para Español, presione 2.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-language</Redirect>
</Response>"""
  return Response(xml, mimetype='application/xml')

# Webhook: Handle Language Selection
@app.post('/plivo/select-language')
def plivo_select_language():
  call_uuid = request.values.get('CallUUID')
  digits = request.values.get('Digits')
  
  send_event('language_selected', {'callUuid': call_uuid, 'digits': digits or 'none'})
  
  public_url = get_public_url()
  
  if digits == '1':
    send_event('language_confirmed', {'callUuid': call_uuid, 'lang': 'en'})
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/handle-level2?lang=en" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>You have selected English. Press 1 to play a short audio message. Press 2 to connect to a live associate.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-level2?lang=en</Redirect>
</Response>"""
  elif digits == '2':
    send_event('language_confirmed', {'callUuid': call_uuid, 'lang': 'es'})
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/handle-level2?lang=es" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>Ha seleccionado Español. Presione 1 para reproducir un mensaje de audio. Presione 2 para comunicarse con un asociado.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-level2?lang=es</Redirect>
</Response>"""
  else:
    send_event('language_invalid', {'callUuid': call_uuid, 'digits': digits or 'none'})
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/select-language" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>Invalid option. For English, press 1. Para Español, presione 2.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-language</Redirect>
</Response>"""
  return Response(xml, mimetype='application/xml')

# Webhook Helper: Re-prompt Level 2 options
@app.post('/plivo/prompt-level2')
def plivo_prompt_level2():
  public_url = get_public_url()
  lang = request.args.get('lang', 'en')
  
  if lang == 'es':
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/handle-level2?lang=es" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>Presione 1 para reproducir un mensaje de audio. Presione 2 para comunicarse con un asociado.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-level2?lang=es</Redirect>
</Response>"""
  else:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/handle-level2?lang=en" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>Press 1 to play a short audio message. Press 2 to connect to a live associate.</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-level2?lang=en</Redirect>
</Response>"""
  return Response(xml, mimetype='application/xml')

# Webhook: Handle Level 2 branching
@app.post('/plivo/handle-level2')
def plivo_handle_level2():
  call_uuid = request.values.get('CallUUID')
  digits = request.values.get('Digits')
  lang = request.args.get('lang', 'en')
  
  send_event('level2_selected', {'callUuid': call_uuid, 'digits': digits or 'none', 'lang': lang})
  
  public_url = get_public_url()
  
  if digits == '1':
    send_event('playing_audio', {'callUuid': call_uuid, 'lang': lang})
    msg = 'Reproduciendo audio de demostración.' if lang == 'es' else 'Playing demo audio file.'
    end_msg = 'Gracias por escuchar. Adiós.' if lang == 'es' else 'Thank you for listening. Goodbye.'
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>{msg}</Speak>
    <Play>https://s3.amazonaws.com/static.plivo.com/music.mp3</Play>
    <Speak>{end_msg}</Speak>
    <Hangup/>
</Response>"""
  elif digits == '2':
    associate = os.environ.get('ASSOCIATE_NUMBER')
    source_num = os.environ.get('PLIVO_SOURCE_NUMBER')
    send_event('connecting_associate', {'callUuid': call_uuid, 'associate': associate, 'lang': lang})
    
    msg = 'Conectando con un asociado. Por favor espere.' if lang == 'es' else 'Connecting to a live associate. Please wait.'
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Speak>{msg}</Speak>
    <Dial callerId="{source_num}">
        <Number>{associate}</Number>
    </Dial>
</Response>"""
  else:
    send_event('level2_invalid', {'call_uuid': call_uuid, 'digits': digits or 'none', 'lang': lang})
    prompt_text = 'Opción inválida. Presione 1 para reproducir un mensaje de audio. Presione 2 para comunicarse con un asociado.' if lang == 'es' else 'Invalid option. Press 1 to play a short audio message. Press 2 to connect to a live associate.'
    
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <GetInput action="{public_url}/plivo/handle-level2?lang={lang}" method="POST" inputType="dtmf" numDigits="1" timeout="10" retries="1">
        <Speak>{prompt_text}</Speak>
    </GetInput>
    <Redirect method="POST">{public_url}/plivo/prompt-level2?lang={lang}</Redirect>
</Response>"""
    
  return Response(xml, mimetype='application/xml')

# Webhook: Call Status Update
@app.post('/plivo/status')
def plivo_status():
  call_uuid = request.values.get('CallUUID')
  status = request.values.get('CallStatus')
  send_event('call_status', {'callUuid': call_uuid, 'status': status})
  return 'OK', 200

if __name__ == '__main__':
  print(f"Flask Server starting on port {PORT}...")
  app.run(host='0.0.0.0', port=PORT, debug=True)