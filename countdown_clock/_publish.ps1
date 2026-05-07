$ErrorActionPreference = "Stop"
$line = Get-Content C:\Users\cagon\.openclaw\workspace\.env | Where-Object { $_ -match "^NEXUS_GITHUB_TOKEN=" }
$token = ($line -replace "^NEXUS_GITHUB_TOKEN=","").Trim('"').Trim("'")
$repo = "blueagentnexus/countdown-timer"
$apiBase = "https://api.github.com/repos/$repo"
$headers = @{ Authorization = "Bearer $token"; "User-Agent" = "nexus3"; Accept = "application/vnd.github+json" }

$version = "1.8.0"
$tag = "v$version"
$exeName = "CountdownClock-v$version.exe"
$exePath = "C:\Users\cagon\.openclaw\workspace\countdown_clock\dist\$exeName"

function Put-File($localPath, $repoPath, $msg) {
    $bytes = [IO.File]::ReadAllBytes($localPath)
    $b64 = [Convert]::ToBase64String($bytes)
    $sha = $null
    try {
        $existing = Invoke-RestMethod -Uri "$apiBase/contents/$repoPath" -Headers $headers
        $sha = $existing.sha
    } catch {}
    $body = @{ message = $msg; content = $b64 }
    if ($sha) { $body.sha = $sha }
    $json = $body | ConvertTo-Json -Compress
    Invoke-RestMethod -Uri "$apiBase/contents/$repoPath" -Headers $headers -Method PUT -Body $json -ContentType "application/json" | Out-Null
    Write-Host "uploaded: $repoPath"
}

Put-File "C:\Users\cagon\.openclaw\workspace\countdown_clock\countdown_clock.py" "countdown_clock.py" "v${version}: proportional scaling + snap-to-fill"
Put-File "C:\Users\cagon\.openclaw\workspace\countdown_clock\README.md" "README.md" "v${version}: update README for proportional scaling"
Put-File "C:\Users\cagon\.openclaw\workspace\countdown_clock\CountdownClock.spec" "CountdownClock.spec" "v${version}: update for v1.8.0"

# Create release
$relBody = @{
    tag_name = $tag
    name = "v${version} - Proportional Scaling + Snap-to-Fill"
    body = "Changes:`n- Proportional scaling + snap-to-fill: Enforced locked aspect ratio during resize so proportions remain consistent.`n- Replaced magic-number font scaling with a robust binary search measurement loop (_calculate_fit_size) that finds the largest font that fits the window without clipping.`n- Improved default sizing: Set default font size for new timers to 20 and default window size to 300x120.`n- EXE is now named CountdownClock-v${version}.exe.`n`nPrebuilt Windows EXE attached: ${exeName}"
    draft = $false
    prerelease = $false
} | ConvertTo-Json -Compress

try {
    $rel = Invoke-RestMethod -Uri "$apiBase/releases" -Headers $headers -Method POST -Body $relBody -ContentType "application/json"
} catch {
    $rel = Invoke-RestMethod -Uri "$apiBase/releases/tags/$tag" -Headers $headers
}
Write-Host "release id: $($rel.id)"

$uploadUrl = "https://uploads.github.com/repos/$repo/releases/$($rel.id)/assets?name=$exeName"
$exeBytes = [IO.File]::ReadAllBytes($exePath)
$assetHeaders = @{ Authorization = "Bearer $token"; "User-Agent" = "nexus3"; Accept = "application/vnd.github+json" }
try {
    Invoke-RestMethod -Uri $uploadUrl -Headers $assetHeaders -Method POST -Body $exeBytes -ContentType "application/octet-stream" | Out-Null
    Write-Host "asset uploaded: $exeName"
} catch {
    Write-Host "asset upload error: $($_.Exception.Message)"
}

Write-Host "DONE: https://github.com/$repo/releases/tag/$tag"
