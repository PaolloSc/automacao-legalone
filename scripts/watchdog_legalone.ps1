# Watchdog: mata a automacao se ela travar (viva mas sem trabalhar).
# O supervisor do iniciar_automacao.bat sobe de novo em 30s.
#
# Heartbeat = mtime de outlook_monitor.log (o monitor escreve a cada ciclo de 300s).
# NAO usar automacao_legalone.log: ele so registra eventos e fica horas parado
# com a automacao saudavel.
#
# Uso: powershell -ExecutionPolicy Bypass -File watchdog_legalone.ps1 [-MaxIdleMin 30] [-DryRun]
param(
    [double]$MaxIdleMin = 30,   # cadastro em andamento segura o monitor; 30min da folga
    [switch]$DryRun
)

$raiz = Split-Path -Parent $PSScriptRoot
$heartbeat = Join-Path $raiz 'outlook_monitor.log'
$agora = Get-Date

if (-not (Test-Path $heartbeat)) {
    Write-Output "[$agora] sem heartbeat ($heartbeat) - nada a fazer"
    exit 0
}

$idle = ($agora - (Get-Item $heartbeat).LastWriteTime).TotalMinutes
$procs = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
           Where-Object { $_.CommandLine -like '*automacao_legalone_completa.py*' })

if ($idle -le $MaxIdleMin) {
    Write-Output ("[{0}] ok - heartbeat ha {1:N1} min, {2} processo(s)" -f $agora, $idle, $procs.Count)
    exit 0
}

Write-Output ("[{0}] TRAVADO - heartbeat ha {1:N1} min (limite {2}), matando {3} processo(s)" -f $agora, $idle, $MaxIdleMin, $procs.Count)
foreach ($p in $procs) {
    if ($DryRun) {
        Write-Output "  [dry-run] mataria PID $($p.ProcessId)"
    } else {
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
        Write-Output "  morto PID $($p.ProcessId)"
    }
}

# Se o proprio .bat supervisor tiver morrido (nada pra ressuscitar os python),
# religa a tarefa. Com MultipleInstances=IgnoreNew isso e no-op se ele estiver vivo.
if (-not $DryRun) {
    Start-ScheduledTask -TaskName 'LegalOne Automacao' -ErrorAction SilentlyContinue
    Write-Output "  Start-ScheduledTask 'LegalOne Automacao' disparado"
}
