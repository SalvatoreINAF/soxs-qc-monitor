import importlib.util,json,os,pathlib,signal,subprocess,sys,tempfile,time
from qc_monitor.coordination import leases,CoordinationBusyError
repo=pathlib.Path(__file__).resolve().parents[2]
baseline=tempfile.TemporaryDirectory(prefix='qc-batch-baseline-')
baseline_path=pathlib.Path(baseline.name)/'batch.py'
baseline_path.write_bytes(subprocess.check_output(['git','show','0df371c:scripts/batch.py'],cwd=repo))
spec=importlib.util.spec_from_file_location('batch_audit',baseline_path)
batch=importlib.util.module_from_spec(spec);spec.loader.exec_module(batch)
results=[]
child="import os,signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print('child-ready',os.getpid(),flush=True); time.sleep(30)"
program="from qc_monitor.coordination import leases; import subprocess,sys,time\nwith leases([('resource',sys.argv[1],True)]) as fds:\n subprocess.Popen([sys.executable,'-c',sys.argv[2]],pass_fds=fds)\n time.sleep(30)\n"
with tempfile.TemporaryDirectory(prefix='qc-timeout-audit-') as temporary:
 root=pathlib.Path(temporary)
 for index in range(20):
  resource=str(root/f'resource-{index}')
  log=root/f'{index}.log'
  with log.open('w') as stream:
   try:batch.execute([sys.executable,'-c',program,resource,child],repo,stream,time.monotonic()+.3)
   except subprocess.TimeoutExpired:pass
  assert 'child-ready' in log.read_text(),log.read_text()
  start=time.monotonic();busy=0
  while True:
   try:
    with leases([('resource',resource,True)]):pass
    break
   except CoordinationBusyError:
    busy+=1
    if time.monotonic()-start>2:raise
    time.sleep(.001)
  results.append({'immediately_busy':bool(busy),'release_after_seconds':time.monotonic()-start})
 # Deterministic scheduling proof: defer delivery of SIGKILL until execute returns.
 resource=str(root/'deferred');log=root/'deferred.log';pending=[];real_killpg=os.killpg
 def defer(group, sig):
  if sig==signal.SIGKILL:pending.append(group)
  else:real_killpg(group,sig)
 os.killpg=defer
 try:
  with log.open('w') as stream:
   try:batch.execute([sys.executable,'-c',program,resource,child],repo,stream,time.monotonic()+.3)
   except subprocess.TimeoutExpired:pass
  assert pending and 'child-ready' in log.read_text()
  try:
   with leases([('resource',resource,True)]):pass
  except CoordinationBusyError:controlled=True
  else:controlled=False
 finally:
  os.killpg=real_killpg
  for group in pending:
   try:real_killpg(group,signal.SIGKILL)
   except ProcessLookupError:pass
 start=time.monotonic()
 while True:
  try:
   with leases([('resource',resource,True)]):pass
   break
  except CoordinationBusyError:
   if time.monotonic()-start>2:raise
   time.sleep(.001)
report={'host':sys.platform,'real_process_trials':results,'immediate_contentions':sum(item['immediately_busy'] for item in results),'controlled_deferred_kill_retains_lease_after_execute':controlled,'lease_released_after_actual_kill':True,'baseline_commit':'0df371c','runtime_platform':sys.platform}
(repo/'tests/results/d3-b-timeout-audit.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
