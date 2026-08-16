param(
    [string]$Url = "http://127.0.0.1:8501",
    [int]$TimeoutSeconds = 45
)

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
while ((Get-Date) -lt $deadline) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$Url/_stcore/health" -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Start-Process $Url
            exit 0
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}

exit 1
