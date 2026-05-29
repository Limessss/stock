#Requires -Version 5.1
<#
.SYNOPSIS
  Restart backend and frontend dev servers.

.EXAMPLE
  .\scripts\restart.ps1
  .\scripts\restart.ps1 -BackendOnly
  .\scripts\restart.ps1 -FrontendOnly
#>
[CmdletBinding()]
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$NoReload,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
    $root = Split-Path -Parent $PSScriptRoot
    if (-not (Test-Path (Join-Path $root 'pyproject.toml'))) {
        throw 'Repo root not found (missing pyproject.toml).'
    }
    return $root
}

function Get-PortListenerIds {
    param([int]$Port)

    $procIds = @()
    try {
        $procIds = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)
    }
    catch {
        # fallback to netstat when Get-NetTCPConnection is unavailable
    }

    if (-not $procIds -or $procIds.Count -eq 0) {
        $pattern = ':' + [string]$Port + '\s'
        $lines = netstat -ano | Select-String -Pattern $pattern
        foreach ($line in $lines) {
            if ($line -match '\s(\d+)\s*$') {
                $procIds += [int]$Matches[1]
            }
        }
        $procIds = $procIds | Select-Object -Unique
    }

    return $procIds
}

function Stop-PortListener {
    param([int]$Port)

    foreach ($procId in (Get-PortListenerIds -Port $Port)) {
        if ($procId -le 0) { continue }
        try {
            $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
            if ($proc) {
                $msg = '  stop PID {0} ({1}) on port {2}' -f $procId, $proc.ProcessName, $Port
                Write-Host $msg -ForegroundColor Yellow
                Stop-Process -Id $procId -Force -ErrorAction Stop
            }
        }
        catch {
            $msg = '  failed to stop PID {0}: {1}' -f $procId, $_
            Write-Host $msg -ForegroundColor DarkYellow
        }
    }
}

function Stop-ProjectBackend {
    param([string]$Root, [int]$Port)

    $rootNorm = $Root.ToLower()
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {
        $cmd = $_.CommandLine
        if (-not $cmd) { return }
        $cmdLower = $cmd.ToLower()
        $isBackend = $cmdLower -like '*backend.app.main:app*' -and $cmdLower -like ('*' + $rootNorm + '*')
        $isUvicornPort = $cmdLower -like '*uvicorn*' -and $cmdLower -like ('*--port ' + [string]$Port + '*')
        $isOrphanWorker = $cmdLower -like '*multiprocessing-fork*' -and $cmdLower -like '*spawn_main*'
        if ($isBackend -or $isUvicornPort -or $isOrphanWorker) {
            $msg = '  stop backend process PID {0}' -f $_.ProcessId
            Write-Host $msg -ForegroundColor Yellow
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    }

    for ($try = 0; $try -lt 5; $try++) {
        Stop-PortListener -Port $Port
        Start-Sleep -Milliseconds 400
        if (-not (Get-PortListenerIds -Port $Port)) {
            break
        }
    }
}

function Assert-CommandExists {
    param([string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw ('Command not found: {0}. Please install it and add to PATH.' -f $Name)
    }
}

function Start-Backend {
    param([string]$Root, [int]$Port, [switch]$NoReload)

    Assert-CommandExists 'uv'
    $reloadFlag = if ($NoReload) { '' } else { ' --reload' }
    $cmd = 'Set-Location ''{0}''; uv run uvicorn backend.app.main:app{1} --port {2}' -f $Root, $reloadFlag, $Port
    Start-Process powershell -ArgumentList @('-NoExit', '-Command', $cmd) -WindowStyle Normal
    if ($NoReload) {
        Write-Host '  mode: no reload (parallel backtest friendly)' -ForegroundColor DarkGray
    }
    Write-Host ('  backend: http://localhost:{0}' -f $Port) -ForegroundColor Green
    Write-Host ('  api docs: http://localhost:{0}/docs' -f $Port) -ForegroundColor Green
}

function Start-Frontend {
    param([string]$Root, [int]$Port)

    $webDir = Join-Path $Root 'Web'
    if (-not (Test-Path $webDir)) {
        throw ('Web directory not found: {0}' -f $webDir)
    }

    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw 'npm not found. Please install Node.js first.'
    }

    $cmd = 'Set-Location ''{0}''; npm run dev -- --port {1} --host' -f $webDir, $Port
    Start-Process powershell -ArgumentList @('-NoExit', '-Command', $cmd) -WindowStyle Normal
    Write-Host ('  frontend: http://localhost:{0}' -f $Port) -ForegroundColor Green
}

$startBackend = -not $FrontendOnly
$startFrontend = -not $BackendOnly

Write-Host ''
Write-Host '=== Stockmodel restart ===' -ForegroundColor Cyan

$repoRoot = Get-RepoRoot
Write-Host ('repo: {0}' -f $repoRoot) -ForegroundColor DarkGray

if ($startBackend) {
    Write-Host ('[1/2] stop backend (port {0})...' -f $BackendPort) -ForegroundColor Cyan
    Stop-ProjectBackend -Root $repoRoot -Port $BackendPort
}

if ($startFrontend) {
    Write-Host ('[2/2] stop frontend (port {0})...' -f $FrontendPort) -ForegroundColor Cyan
    Stop-PortListener -Port $FrontendPort
}

Start-Sleep -Seconds 1

if ($startBackend) {
    Write-Host 'start backend...' -ForegroundColor Cyan
    Start-Backend -Root $repoRoot -Port $BackendPort -NoReload:$NoReload
}

if ($startFrontend) {
    Write-Host 'start frontend...' -ForegroundColor Cyan
    Start-Frontend -Root $repoRoot -Port $FrontendPort
}

Write-Host ''
Write-Host 'Done. Backend and frontend run in separate PowerShell windows.' -ForegroundColor Cyan
Write-Host 'Close a window to stop that service.' -ForegroundColor Cyan
Write-Host ''
