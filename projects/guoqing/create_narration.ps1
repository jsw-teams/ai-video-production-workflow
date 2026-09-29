param([string]$TextPath = (Join-Path $PSScriptRoot 'narration.txt'), [string]$OutputPath = (Join-Path $PSScriptRoot 'assets\audio\narration.wav'))
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $synth.SelectVoice('Microsoft Zira Desktop')
} catch {
    $synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female, [System.Speech.Synthesis.VoiceAge]::Adult, 0, [System.Globalization.CultureInfo]::GetCultureInfo('en-US'))
}
$synth.Rate = -1
$synth.Volume = 90
New-Item -ItemType Directory -Force -Path (Split-Path $OutputPath) | Out-Null
$synth.SetOutputToWaveFile($OutputPath)
$synth.Speak([System.IO.File]::ReadAllText($TextPath))
$synth.SetOutputToNull()
$synth.Dispose()
Write-Output $OutputPath