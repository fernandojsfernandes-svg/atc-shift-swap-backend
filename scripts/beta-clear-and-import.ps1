<#
.SYNOPSIS
  Limpa todas as escalas/dados de trocas na API e corre import a partir das pastas PDF do servidor.

.PARAMETER ApiBase
  URL base da API (sem barra no fim), ex.: https://teu-backend.onrender.com

.PARAMETER ClearSchedulesSecret
  Valor igual ao da variável CLEAR_SCHEDULES_SECRET no servidor. Opcional se o segredo não estiver definido.

.EXAMPLE
  .\scripts\beta-clear-and-import.ps1 -ApiBase "https://teu-backend.onrender.com"
  .\scripts\beta-clear-and-import.ps1 -ApiBase "https://teu-backend.onrender.com" -ClearSchedulesSecret "meu-segredo"
#>
param(
    [Parameter(Mandatory = $true)]
    [string] $ApiBase,

    [Parameter(Mandatory = $false)]
    [string] $ClearSchedulesSecret = ""
)

$ErrorActionPreference = "Stop"
$base = $ApiBase.TrimEnd("/")

$clearHeaders = @{
    "Content-Type" = "application/json"
}
if ($ClearSchedulesSecret) {
    $clearHeaders["X-Clear-Schedules-Secret"] = $ClearSchedulesSecret
}

Write-Host "1/2 POST /import/clear-schedules ..." -ForegroundColor Cyan
$clearBody = '{"confirm":"APAGAR_TODAS_AS_ESCALAS"}'
$clearUri = "$base/import/clear-schedules"
try {
    $r1 = Invoke-RestMethod -Uri $clearUri -Method Post -Headers $clearHeaders -Body $clearBody
    $r1 | ConvertTo-Json -Depth 6
} catch {
    Write-Host "Erro no clear: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd()
    }
    exit 1
}

Write-Host "2/2 POST /import/schedules ..." -ForegroundColor Cyan
$importUri = "$base/import/schedules"
try {
    $r2 = Invoke-RestMethod -Uri $importUri -Method Post
    $r2 | ConvertTo-Json -Depth 6
} catch {
    Write-Host "Erro no import: $_" -ForegroundColor Red
    if ($_.Exception.Response) {
        $reader = [System.IO.StreamReader]::new($_.Exception.Response.GetResponseStream())
        Write-Host $reader.ReadToEnd()
    }
    exit 1
}

Write-Host "Concluído." -ForegroundColor Green
