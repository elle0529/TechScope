$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$RepoName = "TechScope"
$Owner = "elle0529"
$Remote = "https://github.com/$Owner/$RepoName.git"

Write-Host ""
Write-Host "TechScope GitHub Snapshot v4"
Write-Host "Resume after PATH-only GitHub CLI detection failure"
Write-Host ""

if(-not (Test-Path $RepoRoot)){ throw "TECHSCOPE_ROOT_NOT_FOUND" }
Set-Location $RepoRoot

# ------------------------------------------------------------
# 1. Verify prior password sanitization is already in place
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
# 2. Git preflight
# ------------------------------------------------------------
$GitExe = $null
try {
    $GitExe = (Get-Command git.exe -ErrorAction Stop).Source
} catch {}
if(-not $GitExe){ throw "GIT_NOT_FOUND" }

Write-Host ("GIT_EXE=" + $GitExe)
& $GitExe --version | Out-Host

# ------------------------------------------------------------
# 3. Locate already-installed GitHub CLI robustly
# ------------------------------------------------------------
$GhExe = $null

# A. Current PATH
try {
    $cmd = Get-Command gh.exe -ErrorAction Stop
    if($cmd.Source -and (Test-Path $cmd.Source)){ $GhExe = $cmd.Source }
} catch {}

# B. where.exe
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

# C. Common GitHub CLI / WinGet locations
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

# D. Targeted recursive search only if still missing
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

if(-not $GhExe){
    throw "GH_CLI_INSTALLED_BUT_EXE_NOT_FOUND"
}

Write-Host ("GH_EXE=" + $GhExe)
& $GhExe --version | Select-Object -First 1 | Out-Host
Write-Host "GH_CLI=PASS_FOUND"

# Add containing directory for any subprocesses git/gh may launch.
$GhDir = Split-Path -Parent $GhExe
if(($env:Path -split ';') -notcontains $GhDir){
    $env:Path = "$GhDir;$env:Path"
}
Write-Host "GH_PATH_SESSION=PASS"

# ------------------------------------------------------------
# 4. Local GitHub authentication
# ------------------------------------------------------------
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $GhExe auth status --hostname github.com *> $null
$auth = $LASTEXITCODE
$ErrorActionPreference = $oldEA

if($auth -ne 0){
    Write-Host "GH_AUTH=REQUIRED"
    Write-Host "Browser/device authentication may appear once."
    & $GhExe auth login --hostname github.com --git-protocol https --web
    if($LASTEXITCODE -ne 0){ throw "GH_AUTH_LOGIN=FAIL" }
}

Write-Host "GH_AUTH=PASS"

$login = (& $GhExe api user --jq ".login").Trim()
if($LASTEXITCODE -ne 0){ throw "GH_USER_LOOKUP=FAIL" }
Write-Host ("GH_USER=" + $login)

if($login -ne $Owner){
    throw "GH_USER_MISMATCH expected=$Owner actual=$login"
}

# ------------------------------------------------------------
# 5. Conservative .gitignore
# ------------------------------------------------------------
$gitignore=@'
# Secrets / authentication
.env
.env.*
!.env.example
*.pem
*.pfx
*.p12
*.key
.azure/
**/.azure/
.databrickscfg
**/.databrickscfg
secrets/
.credentials/

# Local auth/runtime state
results/bootstrap-state.json
results/**/bootstrap-state.json
**/TokenCache.dat
**/msal_token_cache*
**/.identity/
**/.ssh/

# Caches / dependencies
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.venv/
venv/
node_modules/
.vscode/
.idea/
.cache/
tmp/
temp/
*.log
*.tmp
*.bak

# Power BI binary/cache
*.pbix
*.pbit
**/.pbi/
**/LocalCache/
**/DataMashup/
**/DataModel/

# Archives
*.zip
*.7z
*.rar
'@
Set-Content ".gitignore" $gitignore -Encoding UTF8
Write-Host "GITIGNORE=PASS"

# ------------------------------------------------------------
# 6. Secret scan before any git add / push
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

            # Environment variable references are not literal secrets.
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

if($hits.Count-gt 0){
    Write-Host "SECRET_SCAN=FAIL"
    $hits | Sort-Object File,Line,Rule -Unique | ForEach-Object {
        Write-Host ("SECRET_CANDIDATE="+$_.File+":"+$_.Line+" RULE="+$_.Rule)
    }
    throw "SECRET_SCAN_BLOCKED_PUSH"
}

Write-Host "SECRET_SCAN=PASS"

# ------------------------------------------------------------
# 7. Git repository initialization/reuse
# ------------------------------------------------------------
if(-not (Test-Path ".git")){
    & $GitExe init
    if($LASTEXITCODE -ne 0){ throw "GIT_INIT=FAIL" }
    & $GitExe branch -M main
    Write-Host "GIT_INIT=PASS"
}else{
    Write-Host "GIT_INIT=REUSED"
    & $GitExe branch -M main
}

$gitName = (& $GitExe config user.name 2>$null)
$gitEmail = (& $GitExe config user.email 2>$null)

if([string]::IsNullOrWhiteSpace($gitName)){
    & $GitExe config user.name $Owner
}
if([string]::IsNullOrWhiteSpace($gitEmail)){
    $uid = (& $GhExe api user --jq ".id").Trim()
    & $GitExe config user.email "$uid+$Owner@users.noreply.github.com"
}
Write-Host "GIT_IDENTITY=PASS"

& $GitExe add -A
if($LASTEXITCODE -ne 0){ throw "GIT_ADD=FAIL" }

$staged=[int]((& $GitExe diff --cached --name-only | Measure-Object -Line).Lines)
Write-Host ("STAGED_FILES="+$staged)

$tracked = & $GitExe ls-files
$forbidden = $tracked | Where-Object {
    $_ -match '(^|/)\.azure/' -or
    $_ -match '(^|/)\.databrickscfg$' -or
    $_ -match '(^|/)\.env($|\.)' -or
    $_ -match '(^|/)secrets?/'
}

if($forbidden){
    $forbidden | ForEach-Object {
        Write-Host ("FORBIDDEN_TRACKED_PATH="+$_)
    }
    throw "TRACKED_SECRET_PATH_BLOCKED"
}
Write-Host "TRACKED_SECRET_PATH_CHECK=PASS"

# ------------------------------------------------------------
# 8. Create or reuse private GitHub repository
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

    if($LASTEXITCODE -ne 0){
        throw "GITHUB_REPO_CREATE=FAIL"
    }
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
Write-Host ("COMMIT_SHA="+$commit)

# ------------------------------------------------------------
# 10. Push
# ------------------------------------------------------------
Write-Host "GIT_PUSH=START"
& $GitExe push -u origin main
if($LASTEXITCODE -ne 0){ throw "GIT_PUSH=FAIL" }
Write-Host "GIT_PUSH=PASS"

# ------------------------------------------------------------
# 11. Verify remote main SHA
# ------------------------------------------------------------
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
