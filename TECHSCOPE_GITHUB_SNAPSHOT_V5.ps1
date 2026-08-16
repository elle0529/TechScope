$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$RepoName = "TechScope"
$Owner = "elle0529"
$Remote = "https://github.com/$Owner/$RepoName.git"

Write-Host ""
Write-Host "TechScope GitHub Snapshot v5"
Write-Host "Fix: allow verified .env.example template"
Write-Host ""

if(-not (Test-Path $RepoRoot)){ throw "TECHSCOPE_ROOT_NOT_FOUND" }
Set-Location $RepoRoot

# ------------------------------------------------------------
# 1. Verify SQL password sanitization from v3
# ------------------------------------------------------------
$SqlVerify = Join-Path $RepoRoot "tools\p1d_sql_verify.py"
if(-not (Test-Path $SqlVerify)){ throw "P1D_SQL_VERIFY_NOT_FOUND" }

$sqlText = Get-Content -LiteralPath $SqlVerify -Raw
if(
    $sqlText -notmatch 'TECHSCOPE_SQL_ADMIN_PASSWORD' -or
    $sqlText -notmatch 'os\.environ'
){
    throw "SQL_PASSWORD_SANITIZE_VERIFY=FAIL"
}
Write-Host "SQL_PASSWORD_SANITIZE_VERIFY=PASS"

# ------------------------------------------------------------
# 2. Locate Git + already-installed GitHub CLI
# ------------------------------------------------------------
$GitExe = $null
try { $GitExe = (Get-Command git.exe -ErrorAction Stop).Source } catch {}
if(-not $GitExe){ throw "GIT_NOT_FOUND" }
Write-Host ("GIT_EXE=" + $GitExe)

$GhExe = $null
try {
    $cmd = Get-Command gh.exe -ErrorAction Stop
    if($cmd.Source -and (Test-Path $cmd.Source)){ $GhExe = $cmd.Source }
} catch {}

if(-not $GhExe){
    try {
        $where = & where.exe gh.exe 2>$null
        if($LASTEXITCODE -eq 0){
            foreach($candidate in $where){
                if(Test-Path $candidate){
                    $GhExe = $candidate
                    break
                }
            }
        }
    } catch {}
}

$candidates = @(
    (Join-Path $env:ProgramFiles "GitHub CLI\gh.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "GitHub CLI\gh.exe"),
    (Join-Path $env:LOCALAPPDATA "Programs\GitHub CLI\gh.exe"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links\gh.exe"),
    (Join-Path $env:USERPROFILE "AppData\Local\Microsoft\WinGet\Links\gh.exe")
) | Where-Object { $_ -and $_.Trim() -ne "" }

if(-not $GhExe){
    foreach($candidate in $candidates){
        if(Test-Path $candidate){
            $GhExe = $candidate
            break
        }
    }
}

if(-not $GhExe){
    $roots = @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)},
        (Join-Path $env:LOCALAPPDATA "Programs"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet")
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach($r in $roots){
        try{
            $found = Get-ChildItem -Path $r -Filter gh.exe -File -Recurse -ErrorAction SilentlyContinue |
                     Select-Object -First 1
            if($found){
                $GhExe = $found.FullName
                break
            }
        }catch{}
    }
}

if(-not $GhExe){ throw "GH_CLI_EXE_NOT_FOUND" }

$GhDir = Split-Path -Parent $GhExe
if(($env:Path -split ';') -notcontains $GhDir){
    $env:Path = "$GhDir;$env:Path"
}
Write-Host ("GH_EXE=" + $GhExe)
Write-Host "GH_CLI=PASS_FOUND"

# ------------------------------------------------------------
# 3. GitHub auth
# ------------------------------------------------------------
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $GhExe auth status --hostname github.com *> $null
$auth = $LASTEXITCODE
$ErrorActionPreference = $oldEA

if($auth -ne 0){
    Write-Host "GH_AUTH=REQUIRED"
    & $GhExe auth login --hostname github.com --git-protocol https --web
    if($LASTEXITCODE -ne 0){ throw "GH_AUTH_LOGIN=FAIL" }
}

$login = (& $GhExe api user --jq ".login").Trim()
if($LASTEXITCODE -ne 0){ throw "GH_USER_LOOKUP=FAIL" }
if($login -ne $Owner){ throw "GH_USER_MISMATCH expected=$Owner actual=$login" }

Write-Host "GH_AUTH=PASS"
Write-Host ("GH_USER="+$login)

# ------------------------------------------------------------
# 4. .env.example template safety check
# ------------------------------------------------------------
Write-Host "ENV_EXAMPLE_SCAN=START"

$envExamples = Get-ChildItem -Path $RepoRoot -Recurse -File -Force |
    Where-Object { $_.Name -eq ".env.example" }

$unsafeEnv = New-Object System.Collections.Generic.List[object]

$placeholderPattern = '^(|<[^>]+>|\$\{[^}]+\}|CHANGE_ME|CHANGEME|REPLACE_ME|YOUR_[A-Z0-9_]+|EXAMPLE|PLACEHOLDER|TODO|dummy|test|sample)$'

foreach($file in $envExamples){
    $lineNo = 0
    Get-Content -LiteralPath $file.FullName | ForEach-Object {
        $lineNo++
        $line = $_.Trim()

        if(
            [string]::IsNullOrWhiteSpace($line) -or
            $line.StartsWith("#") -or
            $line -notmatch '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$'
        ){
            return
        }

        $key = $Matches[1]
        $value = $Matches[2].Trim().Trim('"').Trim("'")

        if($key -match '(?i)(PASSWORD|PASSWD|PWD|SECRET|TOKEN|API_KEY|APIKEY|PRIVATE_KEY)'){
            if($value -notmatch $placeholderPattern){
                $rel = $file.FullName.Substring($RepoRoot.Length).TrimStart("\")
                $unsafeEnv.Add([PSCustomObject]@{
                    File=$rel
                    Line=$lineNo
                    Key=$key
                })
            }
        }
    }
}

if($unsafeEnv.Count -gt 0){
    Write-Host "ENV_EXAMPLE_SCAN=FAIL"
    $unsafeEnv | ForEach-Object {
        Write-Host ("ENV_EXAMPLE_SECRET_CANDIDATE="+$_.File+":"+$_.Line+" KEY="+$_.Key)
    }
    throw "ENV_EXAMPLE_SECRET_BLOCKED"
}
Write-Host "ENV_EXAMPLE_SCAN=PASS"

# ------------------------------------------------------------
# 5. General secret scan
# ------------------------------------------------------------
Write-Host "SECRET_SCAN=START"

$excludeDirs=@(
    ".git",".azure","node_modules",".venv","venv",
    "__pycache__",".cache",".pbi","LocalCache"
)

$extensions=@(
    ".py",".ps1",".cmd",".bat",".sh",".md",".txt",".json",
    ".yaml",".yml",".toml",".ini",".cfg",".conf",".sql",
    ".bicep",".js",".ts",".tsx",".jsx",".csv",".xml",".tmdl",".pbip"
)

$rules=@(
    @{Name="DATABRICKS_PAT";Pattern='dapi[a-zA-Z0-9]{20,}'},
    @{Name="OPENAI_STYLE_KEY";Pattern='sk-[A-Za-z0-9_-]{16,}'},
    @{Name="PRIVATE_KEY";Pattern='-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'},
    @{Name="PASSWORD_LITERAL";Pattern='(?i)\b(?:password|passwd|pwd)\s*=\s*["''][^"'']{4,}["'']'},
    @{Name="SECRET_LITERAL";Pattern='(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token)\s*[:=]\s*["''][^"'']{8,}["'']'}
)

$hits=New-Object System.Collections.Generic.List[object]

Get-ChildItem $RepoRoot -Recurse -File -Force | ForEach-Object {
    $file=$_
    $rel=$file.FullName.Substring($RepoRoot.Length).TrimStart("\")
    $parts=$rel -split '[\\/]'

    if($parts | Where-Object { $excludeDirs -contains $_ }){ return }
    if($extensions -notcontains $file.Extension.ToLowerInvariant()){ return }

    try{
        $n=0
        Get-Content -LiteralPath $file.FullName -ErrorAction Stop | ForEach-Object {
            $n++
            $line=$_

            $envReference = (
                $line -match 'os\.environ' -or
                $line -match 'os\.getenv' -or
                $line -match '\$env:'
            )

            foreach($rule in $rules){
                if($line-match $rule.Pattern){
                    if($envReference -and $rule.Name -in @("PASSWORD_LITERAL","SECRET_LITERAL")){
                        continue
                    }

                    $hits.Add([PSCustomObject]@{
                        File=$rel
                        Line=$n
                        Rule=$rule.Name
                    })
                }
            }
        }
    }catch{}
}

if($hits.Count -gt 0){
    Write-Host "SECRET_SCAN=FAIL"
    $hits | Sort-Object File,Line,Rule -Unique | ForEach-Object {
        Write-Host ("SECRET_CANDIDATE="+$_.File+":"+$_.Line+" RULE="+$_.Rule)
    }
    throw "SECRET_SCAN_BLOCKED_PUSH"
}
Write-Host "SECRET_SCAN=PASS"

# ------------------------------------------------------------
# 6. Reuse/init git and restage current tree
# ------------------------------------------------------------
if(-not (Test-Path ".git")){
    & $GitExe init
    if($LASTEXITCODE-ne 0){ throw "GIT_INIT=FAIL" }
    & $GitExe branch -M main
    Write-Host "GIT_INIT=PASS"
}else{
    Write-Host "GIT_INIT=REUSED"
    & $GitExe branch -M main
}

if([string]::IsNullOrWhiteSpace((& $GitExe config user.name 2>$null))){
    & $GitExe config user.name $Owner
}
if([string]::IsNullOrWhiteSpace((& $GitExe config user.email 2>$null))){
    $uid = (& $GhExe api user --jq ".id").Trim()
    & $GitExe config user.email "$uid+$Owner@users.noreply.github.com"
}
Write-Host "GIT_IDENTITY=PASS"

& $GitExe add -A
if($LASTEXITCODE-ne 0){ throw "GIT_ADD=FAIL" }

$staged=[int]((& $GitExe diff --cached --name-only | Measure-Object -Line).Lines)
Write-Host ("STAGED_FILES="+$staged)

# ------------------------------------------------------------
# 7. Tracked secret path policy
#    .env.example is explicitly allowed only because ENV_EXAMPLE_SCAN passed.
# ------------------------------------------------------------
$tracked = & $GitExe ls-files

$forbidden = $tracked | Where-Object {
    $path = $_

    if($path -match '(^|/)\.env\.example$'){
        return $false
    }

    return (
        $path -match '(^|/)\.azure/' -or
        $path -match '(^|/)\.databrickscfg$' -or
        $path -match '(^|/)\.env($|\.)' -or
        $path -match '(^|/)secrets?/'
    )
}

if($forbidden){
    $forbidden | ForEach-Object {
        Write-Host ("FORBIDDEN_TRACKED_PATH="+$_)
    }
    throw "TRACKED_SECRET_PATH_BLOCKED"
}

Write-Host "TRACKED_SECRET_PATH_CHECK=PASS"
Write-Host "ENV_EXAMPLE_TRACKING=ALLOWED_VERIFIED_TEMPLATE"

# ------------------------------------------------------------
# 8. Create/reuse private GitHub repository
# ------------------------------------------------------------
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $GhExe repo view "$Owner/$RepoName" *> $null
$repoExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $oldEA

if(-not $repoExists){
    Write-Host "GITHUB_REPO=CREATE_PRIVATE"

    & $GhExe repo create "$Owner/$RepoName" `
        --private `
        --description "TechScope - Data & AI Knowledge Ops PoC" `
        --source "." `
        --remote origin

    if($LASTEXITCODE -ne 0){ throw "GITHUB_REPO_CREATE=FAIL" }
}else{
    Write-Host "GITHUB_REPO=REUSED"

    $remotes = & $GitExe remote
    if($remotes -notcontains "origin"){
        & $GitExe remote add origin $Remote
    }else{
        & $GitExe remote set-url origin $Remote
    }
}

Write-Host "GITHUB_REPO=PASS"

# ------------------------------------------------------------
# 9. Commit
# ------------------------------------------------------------
if($staged -gt 0){
    & $GitExe commit -m "chore: checkpoint TechScope implementation before P1E relation repair"
    if($LASTEXITCODE -ne 0){ throw "GIT_COMMIT=FAIL" }

    Write-Host "GIT_COMMIT=PASS"
}else{
    Write-Host "GIT_COMMIT=NO_CHANGES"
}

$commit = (& $GitExe rev-parse HEAD).Trim()
if([string]::IsNullOrWhiteSpace($commit)){ throw "LOCAL_COMMIT_SHA_EMPTY" }
Write-Host ("COMMIT_SHA="+$commit)

# ------------------------------------------------------------
# 10. Push and verify
# ------------------------------------------------------------
Write-Host "GIT_PUSH=START"
& $GitExe push -u origin main
if($LASTEXITCODE -ne 0){ throw "GIT_PUSH=FAIL" }

Write-Host "GIT_PUSH=PASS"

$remoteSha = (& $GhExe api "repos/$Owner/$RepoName/commits/main" --jq ".sha").Trim()
if($LASTEXITCODE -ne 0){ throw "REMOTE_VERIFY=FAIL" }

Write-Host ("REMOTE_MAIN_SHA="+$remoteSha)

if($remoteSha -ne $commit){
    throw "REMOTE_SHA_MISMATCH local=$commit remote=$remoteSha"
}

Write-Host "REMOTE_VERIFY=PASS"
Write-Host ("GITHUB_REPO_URL=https://github.com/$Owner/$RepoName")
Write-Host "REPOSITORY_VISIBILITY=PRIVATE"
Write-Host "CHECKPOINT=PASS"
Write-Host "NEXT_ACTION=VERIFY_GITHUB_THEN_RESUME_P1E_RELATION"
