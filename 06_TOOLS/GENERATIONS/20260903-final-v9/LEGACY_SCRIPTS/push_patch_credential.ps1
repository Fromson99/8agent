param(
    [ValidateSet("Set", "Get", "Delete")]
    [string]$Mode = "Set",
    [string]$Target = "8-AGENT Gmail SMTP"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Runtime.InteropServices.ComTypes;

public static class CredentialNative {
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct Credential {
        public UInt32 Flags;
        public UInt32 Type;
        public string TargetName;
        public string Comment;
        public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public UInt32 CredentialBlobSize;
        public IntPtr CredentialBlob;
        public UInt32 Persist;
        public UInt32 AttributeCount;
        public IntPtr Attributes;
        public string TargetAlias;
        public string UserName;
    }

    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredRead(string target, UInt32 type, UInt32 flags, out IntPtr credential);

    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredWrite([In] ref Credential credential, UInt32 flags);

    [DllImport("advapi32.dll", EntryPoint = "CredDeleteW", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CredDelete(string target, UInt32 type, UInt32 flags);

    [DllImport("advapi32.dll", SetLastError = false)]
    public static extern void CredFree(IntPtr buffer);
}
"@

function Get-PlainText([Security.SecureString]$SecureValue) {
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureValue)
    try {
        [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
}

if ($Mode -eq "Set") {
    $username = Read-Host "Gmail address"
    if ([string]::IsNullOrWhiteSpace($username) -or -not $username.Contains("@")) {
        throw "Gmail address is invalid."
    }
    $securePassword = Read-Host "Gmail app password (not your normal password)" -AsSecureString
    $password = Get-PlainText $securePassword
    if ([string]::IsNullOrWhiteSpace($password)) {
        throw "Gmail app password is empty."
    }

    $bytes = [Text.Encoding]::Unicode.GetBytes($password.Replace(" ", ""))
    $blob = [Runtime.InteropServices.Marshal]::AllocHGlobal($bytes.Length)
    try {
        [Runtime.InteropServices.Marshal]::Copy($bytes, 0, $blob, $bytes.Length)
        $credential = New-Object CredentialNative+Credential
        $credential.Type = 1
        $credential.TargetName = $Target
        $credential.CredentialBlobSize = $bytes.Length
        $credential.CredentialBlob = $blob
        $credential.Persist = 2
        $credential.UserName = $username.Trim()
        if (-not [CredentialNative]::CredWrite([ref]$credential, 0)) {
            throw "CredWrite failed: $([Runtime.InteropServices.Marshal]::GetLastWin32Error())"
        }
    }
    finally {
        for ($index = 0; $index -lt $bytes.Length; $index++) {
            $bytes[$index] = 0
            [Runtime.InteropServices.Marshal]::WriteByte($blob, $index, 0)
        }
        [Runtime.InteropServices.Marshal]::FreeHGlobal($blob)
        $password = $null
    }
    Write-Output "Saved Gmail app password in Windows Credential Manager."
    exit 0
}

if ($Mode -eq "Delete") {
    if (-not [CredentialNative]::CredDelete($Target, 1, 0)) {
        $errorCode = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
        if ($errorCode -ne 1168) {
            throw "CredDelete failed: $errorCode"
        }
    }
    Write-Output "Deleted Gmail credential from Windows Credential Manager."
    exit 0
}

$pointer = [IntPtr]::Zero
if (-not [CredentialNative]::CredRead($Target, 1, 0, [ref]$pointer)) {
    throw "Gmail credential was not found in Windows Credential Manager. Run this script with -Mode Set."
}
try {
    $credential = [Runtime.InteropServices.Marshal]::PtrToStructure(
        $pointer, [type][CredentialNative+Credential]
    )
    $password = [Runtime.InteropServices.Marshal]::PtrToStringUni(
        $credential.CredentialBlob, [int]($credential.CredentialBlobSize / 2)
    )
    [ordered]@{
        username = $credential.UserName
        password = $password
    } | ConvertTo-Json -Compress
}
finally {
    [CredentialNative]::CredFree($pointer)
}
