"""Capture D4 reports after image decode and two browser compositor frames.

Usage: python scripts/capture_d4_reports.py QA_DIRECTORY SCREENSHOT_DIRECTORY
Uses headless macOS Chrome with a temporary profile and a localhost DevTools port.
"""
import base64, json, os, signal, socket, struct, subprocess, tempfile, time, sys
from pathlib import Path
from urllib.request import urlopen

class CDP:
 def __init__(self,url):
  from urllib.parse import urlsplit
  u=urlsplit(url);self.sock=socket.create_connection((u.hostname,u.port),timeout=10);self.counter=0
  key=base64.b64encode(os.urandom(16)).decode()
  self.sock.sendall(f'GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n'.encode())
  header=b''
  while not header.endswith(b'\r\n\r\n'):header+=self.sock.recv(1)
  assert header.split(b'\r\n', 1)[0].split()[1] == b'101', header
 def read(self,n):
  data=b''
  while len(data)<n:
   more=self.sock.recv(n-len(data))
   if not more:raise EOFError
   data+=more
  return data
 def recv(self):
  a,b=self.read(2);length=b&127
  if length==126:length=struct.unpack('>H',self.read(2))[0]
  if length==127:length=struct.unpack('>Q',self.read(8))[0]
  mask=self.read(4) if b&128 else None
  payload=self.read(length)
  if mask:payload=bytes(c^mask[i%4] for i,c in enumerate(payload))
  return json.loads(payload)
 def call(self,method,params=None):
  self.counter+=1;number=self.counter;payload=json.dumps({'id':number,'method':method,'params':params or {}}).encode();length=len(payload)
  frame=bytes([0x81,0x80|length]) if length<126 else bytes([0x81,0xFE])+struct.pack('>H',length)
  mask=os.urandom(4);self.sock.sendall(frame+mask+bytes(c^mask[i%4] for i,c in enumerate(payload)))
  while True:
   response=self.recv()
   if response.get('id')==number:
    assert 'error' not in response,response
    return response.get('result',{})

qa=json.loads((Path(sys.argv[1]) / 'qa.json').read_text())
output = Path(sys.argv[2]).resolve()
output.mkdir(parents=True, exist_ok=True)
chrome='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
with tempfile.TemporaryDirectory(prefix='qc-d4-cdp-',dir='/private/tmp') as profile:
 with tempfile.TemporaryFile() as log:
  process=subprocess.Popen([chrome,'--headless','--disable-gpu','--disable-background-networking','--no-first-run','--no-default-browser-check','--use-mock-keychain','--password-store=basic','--allow-file-access-from-files','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],stdout=log,stderr=log,start_new_session=True)
  try:
   portfile=Path(profile)/'DevToolsActivePort';deadline=time.monotonic()+30
   while not portfile.is_file() and time.monotonic()<deadline:time.sleep(.1)
   port=int(portfile.read_text().splitlines()[0])
   tabs=json.load(urlopen(f'http://127.0.0.1:{port}/json',timeout=10));page=next(tab for tab in tabs if tab['type']=='page');cdp=CDP(page['webSocketDebuggerUrl'])
   cdp.call('Page.enable');cdp.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1500,'deviceScaleFactor':1,'mobile':False})
   for label,url in [('nominal',qa['nominal']['archive']),('partial',qa['partial']['archive']),('reused',qa['live']),('archive',qa['reused']['archive'])]:
    cdp.call('Page.navigate',{'url':Path(url).as_uri()});deadline=time.monotonic()+20
    while time.monotonic()<deadline:
     answer=cdp.call('Runtime.evaluate',{'expression':"document.readyState === 'complete' && [...document.images].every(image => image.complete && image.naturalWidth > 0)", 'returnByValue':True})
     if answer.get('result',{}).get('value') is True:break
     time.sleep(.1)
    else:raise RuntimeError('Incomplete images '+label)
    cdp.call('Runtime.evaluate',{'expression':'window.scrollTo(0,0)'})
    cdp.call('Runtime.evaluate',{'expression':'new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve(true))))','awaitPromise':True})
    shot=cdp.call('Page.captureScreenshot',{'format':'png','fromSurface':True,'captureBeyondViewport':False})
    (output / ('d4-report-'+label+'.png')).write_bytes(base64.b64decode(shot['data']))
    print(label,'decoded images and compositor frames verified',flush=True)
   cdp.sock.close()
  finally:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=5)
