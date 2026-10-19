$ErrorActionPreference = 'Stop'
try {
    $desktopPython = Join-Path $PSScriptRoot 'runtime\python\pythonw.exe'
    if (-not (Test-Path -LiteralPath $desktopPython -PathType Leaf)) {
        throw '没有找到Python运行环境，请检查软件文件。'
    }
    $entryPath = Join-Path $PSScriptRoot 'bootstrap.py'
    $quotedEntry = '"' + $entryPath + '"'
    $env:PYTHONIOENCODING = 'utf-8'
    Start-Process -FilePath $desktopPython -ArgumentList @('-E', '-s', '-B', $quotedEntry) -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
} catch {
    $startupFailure = $_.Exception
    try {
        $logRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'RyoGeese\logs'
        [System.IO.Directory]::CreateDirectory($logRoot) | Out-Null
        $stamp = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('yyyy-MM-dd_HH-mm-ss_ffffff')
        $runId = [guid]::NewGuid().ToString('N').Substring(0,8)
        $errorPath = Join-Path $logRoot ('报错_'+$stamp+'_'+$runId+'_0001.txt')
        $errorText = $startupFailure.ToString()
        if ($errorText.Length -gt 8192) { $errorText = $errorText.Substring(0,8192) }
        $errorRecord = [ordered]@{
            '时间' = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8)).ToString('o')
            kind = 'launcher_error'
            message = $errorText
        }
        $errorJson = ConvertTo-Json -InputObject $errorRecord -Depth 4 -Compress
        [System.IO.File]::WriteAllText($errorPath, ($errorJson + [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))
    } catch {}
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show($startupFailure.Message, 'RyoGeese未能打开') | Out-Null
    exit 1
}
