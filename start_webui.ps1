$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RootDir

if (-not $env:OPEN_NOTEBOOK_VENV) { $env:OPEN_NOTEBOOK_VENV = ".venv311" }
if (-not $env:PIP_INDEX_URL) { $env:PIP_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple" }
if (-not $env:OPEN_NOTEBOOK_HOST) { $env:OPEN_NOTEBOOK_HOST = "127.0.0.1" }
if (-not $env:OPEN_NOTEBOOK_PORT) { $env:OPEN_NOTEBOOK_PORT = "8017" }

function Test-Python311($Command, [string[]]$CommandArgs = @()) {
  try {
    & $Command @CommandArgs -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)" *> $null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  }
}

function Find-Python311 {
  if ($env:PYTHON_BIN) {
    if (Test-Python311 $env:PYTHON_BIN) { return @($env:PYTHON_BIN) }
    throw "PYTHON_BIN is set but is not Python 3.11: $env:PYTHON_BIN"
  }
  if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python311 "py" @("-3.11")) { return @("py", "-3.11") }
  }
  foreach ($candidate in @("python3.11", "python3", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
      if (Test-Python311 $candidate) { return @($candidate) }
    }
  }
  throw "Python 3.11 was not found. Install Python 3.11 first, or set PYTHON_BIN."
}

$VenvPython = Join-Path $env:OPEN_NOTEBOOK_VENV "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  $PythonCmd = Find-Python311
  Write-Host "[Open_Notebook] Creating virtual environment: $env:OPEN_NOTEBOOK_VENV"
  & $PythonCmd[0] $PythonCmd[1..($PythonCmd.Count - 1)] -m venv $env:OPEN_NOTEBOOK_VENV
}

& $VenvPython -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) {
  throw "$env:OPEN_NOTEBOOK_VENV is not a Python 3.11 environment. Remove it or set OPEN_NOTEBOOK_VENV to a Python 3.11 venv."
}

& $VenvPython -c "import fastapi, uvicorn, open_notebook" *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host "[Open_Notebook] Installing Python dependencies with Tsinghua mirror..."
  & $VenvPython -m pip install -U pip -i $env:PIP_INDEX_URL
  & $VenvPython -m pip install -e ".[local-u1]" -i $env:PIP_INDEX_URL
}

if (-not $env:OPEN_NOTEBOOK_DATA_DIR) { $env:OPEN_NOTEBOOK_DATA_DIR = "data" }
if (-not $env:SENSENOVA_U1_MODEL_PATH) { $env:SENSENOVA_U1_MODEL_PATH = "models/Full" }
if (-not $env:SENSENOVA_U1_SOURCE_ROOT) { $env:SENSENOVA_U1_SOURCE_ROOT = "../SenseNova-U1-main/src" }
if (-not $env:SENSENOVA_U1_DEVICE) { $env:SENSENOVA_U1_DEVICE = "cuda" }
if (-not $env:SENSENOVA_U1_DTYPE) { $env:SENSENOVA_U1_DTYPE = "bfloat16" }
if (-not $env:SENSENOVA_U1_NUM_STEPS) { $env:SENSENOVA_U1_NUM_STEPS = "50" }
if (-not $env:SENSENOVA_U1_CFG_SCALE) { $env:SENSENOVA_U1_CFG_SCALE = "4.0" }
if (-not $env:SENSENOVA_U1_CFG_NORM) { $env:SENSENOVA_U1_CFG_NORM = "none" }
if (-not $env:SENSENOVA_U1_TIMESTEP_SHIFT) { $env:SENSENOVA_U1_TIMESTEP_SHIFT = "3.0" }
if (-not $env:SENSENOVA_U1_CFG_INTERVAL) { $env:SENSENOVA_U1_CFG_INTERVAL = "0.0,1.0" }
if (-not $env:SENSENOVA_U1_BATCH_SIZE) { $env:SENSENOVA_U1_BATCH_SIZE = "1" }
if (-not $env:SENSENOVA_U1_SEED) { $env:SENSENOVA_U1_SEED = "42" }

$StartArgs = @("--host", $env:OPEN_NOTEBOOK_HOST, "--port", $env:OPEN_NOTEBOOK_PORT)
if ($env:OPEN_NOTEBOOK_NO_OPEN -eq "1" -or $args -contains "--no-open") { $StartArgs += "--no-open" }
if ($env:OPEN_NOTEBOOK_FAKE_IMAGE -eq "1" -or $args -contains "--fake-image") {
  $StartArgs += "--fake-image"
} elseif ($args -contains "--api-image") {
  $StartArgs += "--api-image"
} elseif ((Test-Path (Join-Path $env:SENSENOVA_U1_MODEL_PATH "config.json")) -and (Test-Path (Join-Path $env:SENSENOVA_U1_MODEL_PATH "model.safetensors.index.json"))) {
  $StartArgs += "--local-u1"
}

Write-Host "[Open_Notebook] Web UI: http://$env:OPEN_NOTEBOOK_HOST`:$env:OPEN_NOTEBOOK_PORT"
Write-Host "[Open_Notebook] Model path: $env:SENSENOVA_U1_MODEL_PATH"
Write-Host "[Open_Notebook] U1 source:   $env:SENSENOVA_U1_SOURCE_ROOT"
& $VenvPython start.py @StartArgs
