$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$assets = Split-Path -Parent $MyInvocation.MyCommand.Path
$inputPath = Join-Path $assets 'narration.txt'
$outputPath = Join-Path $assets 'voiceover.wav'
$paragraphs = (Get-Content -LiteralPath $inputPath -Raw -Encoding utf8).Trim() -split "`r?`n\s*`r?`n"
$parts = foreach ($p in $paragraphs) {
    $escaped = [System.Security.SecurityElement]::Escape($p.Trim())
    "<p><s>$escaped</s></p><break time='450ms'/>"
}
$ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='zh-CN'><voice name='Microsoft Huihui Desktop'><prosody rate='-5%'>$($parts -join '')</prosody></voice></speak>"
$synth = [System.Speech.Synthesis.SpeechSynthesizer]::new()
$synth.SelectVoice('Microsoft Huihui Desktop')
$synth.SetOutputToWaveFile($outputPath)
$synth.SpeakSsml($ssml)
$synth.Dispose()
Write-Output "Generated $outputPath using offline Windows voice Microsoft Huihui Desktop"
