param(
  [ValidateSet('Start','Verify','SmokeTest','Report','Stop','Clean','All')] [string]$Command='All',
  [string]$RepoPath,
  [switch]$IncludeSlackBot,
  [switch]$EnableAdapter,
  [int]$TimeoutSec=90,
  [switch]$KeepRunning
)
$ErrorActionPreference='Stop'
if(-not $RepoPath){$RepoPath=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path}
$RepoPath=(Resolve-Path $RepoPath).Path
if(-not $PSBoundParameters.ContainsKey('EnableAdapter')){$EnableAdapter=$true}
$ts=Get-Date -Format 'yyyyMMdd-HHmmss'
$Artifacts=Join-Path $RepoPath "artifacts\readiness\$ts";New-Item -ItemType Directory -Force -Path $Artifacts|Out-Null
$StatePath=Join-Path $Artifacts 'state.json'; $ReportPath=Join-Path $Artifacts 'readiness_report.json'
$script:Checks=@(); $script:Commands=@()
function Add-Check($id,$cat,$status,$sev,$evidence,$rem,$cmd,$code='none'){$script:Checks+=[pscustomobject]@{check_id=$id;category=$cat;status=$status;severity=$sev;evidence=$evidence;remediation=$rem;commands_run=$cmd;failure_code=$code}}
function Read-Env($p){$h=@{}; if(Test-Path $p){Get-Content $p|%{if($_ -match '^[^#=]+=(.*)$'){ $k,$v=$_ -split '=',2; $h[$k.Trim()]=$v.Trim()}}};$h}
function Wait-Health($url,$t){$s=Get-Date; while(((Get-Date)-$s).TotalSeconds -lt $t){try{return (Invoke-RestMethod -Uri $url -TimeoutSec 5)}catch{Start-Sleep 2}}; return $null}
function Ollama-Exe{ $c=Get-Command ollama -ErrorAction SilentlyContinue; if($c){$c.Source}else{ $f=Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'; if(Test-Path $f){$f}else{$null}} }
function Save-State($o){$o|ConvertTo-Json -Depth 6|Set-Content -Encoding utf8 $StatePath}
function Load-State{
  if(Test-Path $StatePath){
    $o=Get-Content -Raw $StatePath|ConvertFrom-Json
    $h=@{}
    $o.PSObject.Properties | ForEach-Object { $h[$_.Name]=$_.Value }
    $h
  } else {
    @{}
  }
}
function Resolve-Code{ $f=$script:Checks|? status -eq 'FAIL'; if(-not $f){0}elseif($f.failure_code -contains 'prereq'){10}elseif($f.failure_code -contains 'start'){20}elseif($f.failure_code -contains 'health'){30}elseif($f.failure_code -contains 'smoke'){40}elseif($f.failure_code -contains 'security'){50}else{60}}
function Start-Stack{
  $runAll=Join-Path $RepoPath 'scripts\run_all.ps1'; if(-not(Test-Path $runAll)){Add-Check 'REPO_RUNALL' 'repo' 'FAIL' 'critical' 'scripts/run_all.ps1 missing' 'restore script' 'Test-Path' 'prereq'; return}
  Add-Check 'REPO_RUNALL' 'repo' 'PASS' 'critical' 'run_all.ps1 present' 'none' 'Test-Path'
  $envf=Read-Env (Join-Path $RepoPath '.env')
  $gh=if($envf['LLM_GATEWAY_HOST']){$envf['LLM_GATEWAY_HOST']}else{'127.0.0.1'}
  $gp=if($envf['LLM_GATEWAY_PORT']){[int]$envf['LLM_GATEWAY_PORT']}else{8080}
  $ah=if($envf['OPENCLAW_HOST']){$envf['OPENCLAW_HOST']}else{'127.0.0.1'}
  $ap=if($envf['OPENCLAW_PORT']){[int]$envf['OPENCLAW_PORT']}else{8081}
  $dm=if($envf['OLLAMA_DEFAULT_MODEL']){$envf['OLLAMA_DEFAULT_MODEL']}else{'qwen2.5-coder:7b'}
  $args="-ExecutionPolicy Bypass -File `"$runAll`""; if(-not $IncludeSlackBot){$args+=' -NoSlackBot'}; $args+=' -NoOpenClawAdapter'
  $p=Start-Process powershell -ArgumentList $args -WorkingDirectory $RepoPath -PassThru
  $st=@{run_all_pid=$p.Id;gateway_host=$gh;gateway_port=$gp;adapter_host=$ah;adapter_port=$ap;default_model=$dm}; Save-State $st
  $g=Wait-Health "http://$gh`:$gp/health" $TimeoutSec
  if($g){Add-Check 'API_GATEWAY_HEALTH' 'service' 'PASS' 'critical' "status=$($g.status) readiness=$($g.readiness)" 'none' 'GET /health'}else{Add-Check 'API_GATEWAY_HEALTH' 'service' 'FAIL' 'critical' 'gateway health timeout' 'check logs' 'GET /health' 'start'}
  if($EnableAdapter){
    $py=Join-Path $RepoPath '.venv\Scripts\python.exe'; $app=Join-Path $RepoPath 'services\openclaw_adapter\app.py'
    if((Test-Path $py) -and (Test-Path $app)){
      $oe=$env:OPENCLAW_ENABLED; $od=$env:OPENCLAW_DRY_RUN; $env:OPENCLAW_ENABLED='true'; $env:OPENCLAW_DRY_RUN='true'
      $aproc=Start-Process -FilePath $py -ArgumentList 'services/openclaw_adapter/app.py' -WorkingDirectory $RepoPath -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RepoPath 'logs\openclaw_adapter.log') -RedirectStandardError (Join-Path $RepoPath 'logs\openclaw_adapter.err.log')
      $env:OPENCLAW_ENABLED=$oe; $env:OPENCLAW_DRY_RUN=$od; $st.adapter_pid=$aproc.Id; Save-State $st
      $a=Wait-Health "http://$ah`:$ap/health" $TimeoutSec
      if($a){Add-Check 'OPENCLAW_ADAPTER_HEALTH' 'service' 'PASS' 'high' "status=$($a.status) mode=$($a.mode)" 'none' 'GET /health'}else{Add-Check 'OPENCLAW_ADAPTER_HEALTH' 'service' 'FAIL' 'high' 'adapter health timeout' 'check adapter logs' 'GET /health' 'start'}
    } else { Add-Check 'OPENCLAW_ADAPTER_HEALTH' 'service' 'UNKNOWN' 'high' 'adapter files missing' 'ensure .venv and adapter app exist' 'Test-Path' }
  } else { Add-Check 'OPENCLAW_ADAPTER_HEALTH' 'service' 'UNKNOWN' 'high' 'adapter disabled by parameter' 'enable adapter checks' 'parameter' }
}
function Verify-Stack{
  if(Get-Command python -ErrorAction SilentlyContinue){Add-Check 'PYTHON_VERSION' 'deps' 'PASS' 'critical' (python --version 2>&1) 'none' 'python --version'} else {Add-Check 'PYTHON_VERSION' 'deps' 'FAIL' 'critical' 'python missing' 'install python 3.12+' 'python --version' 'prereq'}
  $ox=Ollama-Exe; if($ox){$ov=& $ox --version 2>&1; Add-Check 'OLLAMA_VERSION' 'deps' 'PASS' 'critical' $ov 'none' 'ollama --version'; $st=Load-State; $m=if($st.default_model){$st.default_model}else{'qwen2.5-coder:7b'}; $list=& $ox list 2>&1; if($list -match [regex]::Escape($m)){Add-Check 'MODEL_AVAILABLE' 'model' 'PASS' 'critical' "model $m present" 'none' 'ollama list'} else {Add-Check 'MODEL_AVAILABLE' 'model' 'FAIL' 'critical' "model $m missing" "run download_model.ps1 -Model `"$m`" -Force" 'ollama list' 'health'}} else {Add-Check 'OLLAMA_VERSION' 'deps' 'FAIL' 'critical' 'ollama missing' 'install ollama' 'ollama --version' 'prereq'}
  $envf=Read-Env (Join-Path $RepoPath '.env'); $bot=$envf['SLACK_BOT_TOKEN']; $app=$envf['SLACK_APP_TOKEN']; if($bot -match '^xoxb-' -and $app -match '^xapp-' -and $bot -notmatch 'your-' -and $app -notmatch 'your-'){Add-Check 'SLACK_CREDS_READY' 'integration' 'PASS' 'high' 'tokens configured' 'none' 'parse .env'} else {Add-Check 'SLACK_CREDS_READY' 'integration' 'UNKNOWN' 'high' 'tokens not configured (offline mode)' 'configure for live integration later' 'parse .env'}
  $st=Load-State; foreach($x in @(@{id='GATEWAY_BIND_LOCALHOST';h=$st.gateway_host;p=$st.gateway_port},@{id='ADAPTER_BIND_LOCALHOST';h=$st.adapter_host;p=$st.adapter_port})){ if(-not $x.h){Add-Check $x.id 'network' 'UNKNOWN' 'high' 'unknown host/port' 'run Start first' 'state'} elseif($x.h -in @('127.0.0.1','localhost','::1')){Add-Check $x.id 'security' 'PASS' 'critical' "bind $($x.h):$($x.p)" 'none' 'config/env'} else {Add-Check $x.id 'security' 'FAIL' 'critical' "non-local bind $($x.h):$($x.p)" 'bind localhost by default' 'config/env' 'security'}}
}
function Smoke-Stack{
  $st=Load-State; if($st.gateway_host){
    $u="http://$($st.gateway_host):$($st.gateway_port)/chat"; $b=@{model=$st.default_model;messages=@(@{role='user';content='Reply with exactly: BRIGHTMIND_OK'});stream=$false;temperature=0;max_tokens=30}|ConvertTo-Json -Depth 6
    try{$sw=[Diagnostics.Stopwatch]::StartNew();$r=Invoke-RestMethod -Uri $u -Method POST -ContentType 'application/json' -Body $b -TimeoutSec 120; $sw.Stop(); if($r.message.content.Trim() -eq 'BRIGHTMIND_OK'){Add-Check 'SMOKE_GATEWAY_CHAT' 'smoke' 'PASS' 'critical' "deterministic ok in $([math]::Round($sw.Elapsed.TotalSeconds,2))s" 'none' 'POST /chat'} else {Add-Check 'SMOKE_GATEWAY_CHAT' 'smoke' 'FAIL' 'critical' "unexpected response: $($r.message.content)" 'check prompt/model' 'POST /chat' 'smoke'}; if($sw.Elapsed.TotalSeconds -le 60){Add-Check 'PERF_CHAT_LATENCY' 'performance' 'PASS' 'medium' "latency=$([math]::Round($sw.Elapsed.TotalSeconds,2))s" 'none' 'POST /chat latency'} else {Add-Check 'PERF_CHAT_LATENCY' 'performance' 'FAIL' 'medium' "latency=$([math]::Round($sw.Elapsed.TotalSeconds,2))s" 'use smaller model or lower load' 'POST /chat latency' 'health'}} catch {Add-Check 'SMOKE_GATEWAY_CHAT' 'smoke' 'FAIL' 'critical' $_.Exception.Message 'check gateway/model/logs' 'POST /chat' 'smoke'}
  } else {Add-Check 'SMOKE_GATEWAY_CHAT' 'smoke' 'UNKNOWN' 'critical' 'gateway unknown' 'run Start first' 'state'}
  if($EnableAdapter -and $st.adapter_host){
    $u2="http://$($st.adapter_host):$($st.adapter_port)/v1/chat/completions"; $b2=@{model=$st.default_model;messages=@(@{role='user';content='ping'})}|ConvertTo-Json -Depth 6
    try{$r2=Invoke-RestMethod -Uri $u2 -Method POST -ContentType 'application/json' -Body $b2 -TimeoutSec 60; $msg=$r2.choices[0].message.content; if($msg -like '*OPENCLAW_DRY_RUN*'){Add-Check 'SMOKE_ADAPTER_DRY_RUN' 'smoke' 'PASS' 'high' 'dry-run marker found' 'none' 'POST /v1/chat/completions'} else {Add-Check 'SMOKE_ADAPTER_DRY_RUN' 'smoke' 'UNKNOWN' 'high' "response=$msg" 'if live mode, validate creds' 'POST /v1/chat/completions'}} catch {Add-Check 'SMOKE_ADAPTER_DRY_RUN' 'smoke' 'FAIL' 'high' $_.Exception.Message 'check adapter health/logs' 'POST /v1/chat/completions' 'smoke'}
  } else {Add-Check 'SMOKE_ADAPTER_DRY_RUN' 'smoke' 'UNKNOWN' 'high' 'adapter not enabled/unknown' 'enable adapter checks' 'state/param'}
}
function Stop-Stack{ $st=Load-State; if($st.adapter_pid){Get-Process -Id ([int]$st.adapter_pid) -ErrorAction SilentlyContinue|Stop-Process -Force -ErrorAction SilentlyContinue}; $runAll=Join-Path $RepoPath 'scripts\run_all.ps1'; if(Test-Path $runAll){ & powershell -ExecutionPolicy Bypass -File $runAll -Stop | Out-Null }}
function Clean-Stack{ Stop-Stack; $esc=[regex]::Escape($RepoPath); Get-CimInstance Win32_Process -Filter "Name='python.exe'" | ? { $_.CommandLine -match $esc } | % { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }
function Write-Report{
  $st=Load-State; $ox=Ollama-Exe; $ov='unknown'; $mods=@(); if($ox){$ov=(& $ox --version 2>&1).ToString(); $mods=((& $ox list 2>&1)|Select-Object -Skip 1|%{$_.ToString().Trim()}|?{$_})}
  $pass=@($script:Checks|? status -eq 'PASS').Count; $fail=@($script:Checks|? status -eq 'FAIL').Count; $unk=@($script:Checks|? status -eq 'UNKNOWN').Count
  $criticalFail=($script:Checks|?{ $_.status -eq 'FAIL' -and $_.severity -eq 'critical'}).Count
  $sl=$script:Checks|? check_id -eq 'SLACK_CREDS_READY'|Select-Object -First 1
  $rep=[ordered]@{title='Brightmind Local Stack Readiness Report';version='1.0';generated_at=(Get-Date).ToString('s');repo_path=$RepoPath;artifacts_path=$Artifacts;verdict=[ordered]@{local_mode_go=($criticalFail -eq 0);live_integration_go=(($criticalFail -eq 0) -and $sl -and $sl.status -eq 'PASS');pass_count=$pass;fail_count=$fail;unknown_count=$unk};environment=[ordered]@{python_version=(python --version 2>&1).ToString();ollama_version=$ov;models=$mods;gateway=[ordered]@{host=$st.gateway_host;port=$st.gateway_port};adapter=[ordered]@{host=$st.adapter_host;port=$st.adapter_port}};checks=$script:Checks;commands_run=$script:Commands}
  $rep|ConvertTo-Json -Depth 10|Set-Content -Encoding utf8 $ReportPath
  $latest=Join-Path (Join-Path $RepoPath 'artifacts\readiness') 'readiness_report.json'; $rep|ConvertTo-Json -Depth 10|Set-Content -Encoding utf8 $latest
  Write-Host "Report: $ReportPath" -ForegroundColor Cyan
}

switch($Command){
  'Start' {Start-Stack; Write-Report; exit (Resolve-Code)}
  'Verify' {Verify-Stack; Write-Report; exit (Resolve-Code)}
  'SmokeTest' {Smoke-Stack; Write-Report; exit (Resolve-Code)}
  'Report' {Write-Report; exit 0}
  'Stop' {Stop-Stack; exit 0}
  'Clean' {Clean-Stack; exit 0}
  'All' {
    try{Start-Stack; Verify-Stack; Smoke-Stack; Write-Report; $c=Resolve-Code; if(-not $KeepRunning){Stop-Stack}; exit $c}
    catch{Add-Check 'UNHANDLED_EXCEPTION' 'runner' 'FAIL' 'critical' $_.Exception.Message 'inspect script/logs' 'runtime' 'start'; Write-Report; if(-not $KeepRunning){Stop-Stack}; exit 99}
  }
}

