param(
    [Parameter(Mandatory=$true)][string]$Path,
    [string]$Thumbprint,
    [string]$TimestampServer
)
$ErrorActionPreference = 'Stop'
if ($Thumbprint) {
    $certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$Thumbprint"
    if (-not $certificate.HasPrivateKey -or
        -not ($certificate.EnhancedKeyUsageList.ObjectId -contains '1.3.6.1.5.5.7.3.3')) {
        throw 'The certificate must have a private key and code-signing usage.'
    }
    $parameters = @{LiteralPath=$Path; Certificate=$certificate; HashAlgorithm='SHA256'}
    if ($TimestampServer) {
        if ($TimestampServer -notmatch '^https://') { throw 'Use an HTTPS timestamp server.' }
        $parameters.TimestampServer = $TimestampServer
    }
    $signature = Set-AuthenticodeSignature @parameters
    if ($signature.Status -ne 'Valid') { throw 'Authenticode signing did not produce a valid signature.' }
} else {
    $signature = Get-AuthenticodeSignature -LiteralPath $Path
}
@{status=$signature.Status.ToString()} | ConvertTo-Json -Compress
