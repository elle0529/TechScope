$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$RepoName = "TechScope"
$Owner = "elle0529"
$Remote = "https://github.com/$Owner/$RepoName.git"

Write-Host ""
Write-Host "TechScope GitHub Snapshot v1"
Write-Host "Target: $Owner/$RepoName (private)"
Write-Host ""

if(-not (Test-Path $RepoRoot)){
    throw "TECHSCOPE_ROOT_NOT_FOUND=$RepoRoot"
}
Set-Location $RepoRoot

# ------------------------------------------------------------
# 1. Ensure Git
# ------------------------------------------------------------
if(-not (Get-Command git.exe -ErrorAction SilentlyContinue)){
    throw "GIT_NOT_FOUND"
}
Write-Host ("GIT_VERSION=" + ((git --version) -join " "))

# ------------------------------------------------------------
# 2. Ensure GitHub CLI
# ------------------------------------------------------------
if(-not (Get-Command gh.exe -ErrorAction SilentlyContinue)){
    Write-Host "GH_CLI=NOT_FOUND"
    if(Get-Command winget.exe -ErrorAction SilentlyContinue){
        Write-Host "GH_CLI_INSTALL=START"
        winget install --id GitHub.cli --exact --accept-package-agreements --accept-source-agreements
        if($LASTEXITCODE -ne 0){
            throw "GH_CLI_INSTALL=FAIL"
        }

        $possible = @(
            "$env:ProgramFiles\GitHub CLI",
            "$env:LOCALAPPDATA\Programs\GitHub CLI"
        )
        foreach($p in $possible){
            if(Test-Path (Join-Path $p "gh.exe")){
                $env:Path = "$p;$env:Path"
            }
        }
    } else {
        throw "GH_CLI_NOT_FOUND_AND_WINGET_UNAVAILABLE"
    }
}
Write-Host ("GH_VERSION=" + ((gh --version | Select-Object -First 1) -join " "))

# ------------------------------------------------------------
# 3. GitHub auth
# ------------------------------------------------------------
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
gh auth status *> $null
$ghAuth = $LASTEXITCODE
$ErrorActionPreference = $oldEA

if($ghAuth -ne 0){
    Write-Host "GH_AUTH=REQUIRED"
    Write-Host "A browser/device authentication prompt may appear once."
    gh auth login --hostname github.com --git-protocol https --web
    if($LASTEXITCODE -ne 0){
        throw "GH_AUTH_LOGIN=FAIL"
    }
}
Write-Host "GH_AUTH=PASS"

$login = (gh api user --jq ".login").Trim()
if($LASTEXITCODE -ne 0){ throw "GH_USER_LOOKUP=FAIL" }
Write-Host ("GH_USER=" + $login)
if($login -ne $Owner){
    throw "GH_USER_MISMATCH expected=$Owner actual=$login"
}

# ------------------------------------------------------------
# 4. Safe .gitignore
# ------------------------------------------------------------
$gitignore = @'
# --- Secrets / authentication ---
.env
.env.*
!.env.example
*.pem
*.pfx
*.p12
*.key
*.crt
*.cer
.azure/
**/.azure/
.databrickscfg
**/.databrickscfg
**/*credentials*
**/*credential*
**/*secret*
**/*token*
secrets/
.credentials/

# --- Local bootstrap/runtime state that may contain machine/auth context ---
results/bootstrap-state.json
results/**/bootstrap-state.json
**/azureProfile.json
**/TokenCache.dat
**/msal_token_cache*
**/.identity/
**/.ssh/

# --- Python / Node / IDE caches ---
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.venv/
venv/
node_modules/
.vscode/
.idea/
.DS_Store
Thumbs.db

# --- Build/temp/log ---
*.log
*.tmp
*.temp
*.bak
*.swp
dist/
build/
.cache/
tmp/
temp/

# --- Power BI generated/binary caches ---
*.pbix
*.pbit
**/.pbi/
**/.cache/
**/LocalCache/
**/DataMashup/
**/DataModel/

# --- Local packages / archives ---
*.zip
*.7z
*.rar

# --- OS / container-local state ---
.wslconfig
docker-data/
'@

Set-Content -Path ".gitignore" -Value $gitignore -Encoding UTF8
Write-Host "GITIGNORE=PASS"

# ------------------------------------------------------------
# 5. Secret-pattern scan BEFORE git add
#    Never print secret values, only file:line + rule.
# ------------------------------------------------------------
Write-Host "SECRET_SCAN=START"

$excludeDirs = @(
    ".git", ".azure", "node_modules", ".venv", "venv",
    "__pycache__", ".cache", ".pbi", "LocalCache"
)

$rules = @(
    @{ Name="DATABRICKS_PAT"; Pattern='dapi[a-zA-Z0-9]{20,}' },
    @{ Name="OPENAI_STYLE_KEY"; Pattern='sk-[A-Za-z0-9_-]{16,}' },
    @{ Name="PASSWORD_ASSIGNMENT"; Pattern='(?i)(password|passwd|pwd)\s*[:=]\s*["'']?[^"''\s]{6,}' },
    @{ Name="SECRET_ASSIGNMENT"; Pattern='(?i)(api[_-]?key|secret|client[_-]?secret|access[_-]?token|refresh[_-]?token)\s*[:=]\s*["'']?[^"''\s]{8,}' },
    @{ Name="CONNECTION_STRING_PASSWORD"; Pattern='(?i)Password\s*=\s*[^;]{4,}' },
    @{ Name="PRIVATE_KEY"; Pattern='-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' }
)

$extensions = @(
    ".py",".ps1",".cmd",".bat",".sh",".md",".txt",".json",".yaml",".yml",
    ".toml",".ini",".cfg",".conf",".sql",".bicep",".js",".ts",".tsx",".jsx",
    ".csv",".xml",".tmdl",".pbip"
)

$hits = New-Object System.Collections.Generic.List[object]

Get-ChildItem -Path $RepoRoot -Recurse -File -Force | ForEach-Object {
    $file = $_
    $relative = $file.FullName.Substring($RepoRoot.Length).TrimStart("\")
    $parts = $relative -split '[\\/]'

    if($parts | Where-Object { $excludeDirs -contains $_ }){
        return
    }

    if($extensions -notcontains $file.Extension.ToLowerInvariant()){
        return
    }

    try{
        $lineNo = 0
        Get-Content -LiteralPath $file.FullName -ErrorAction Stop | ForEach-Object {
            $lineNo++
            $line = $_
            foreach($rule in $rules){
                if($line -match $rule.Pattern){
                    $hits.Add([PSCustomObject]@{
                        File = $relative
                        Line = $lineNo
                        Rule = $rule.Name
                    })
                }
            }
        }
    } catch {}
}

if($hits.Count -gt 0){
    Write-Host "SECRET_SCAN=FAIL"
    $hits | Sort-Object File,Line,Rule -Unique | ForEach-Object {
        Write-Host ("SECRET_CANDIDATE=" + $_.File + ":" + $_.Line + " RULE=" + $_.Rule)
    }
    throw "SECRET_SCAN_BLOCKED_PUSH"
}
Write-Host "SECRET_SCAN=PASS"

# ------------------------------------------------------------
# 6. Initialize git
# ------------------------------------------------------------
if(-not (Test-Path ".git")){
    git init
    if($LASTEXITCODE -ne 0){ throw "GIT_INIT=FAIL" }
    git branch -M main
    Write-Host "GIT_INIT=PASS"
} else {
    Write-Host "GIT_INIT=REUSED"
    $branch = (git branch --show-current).Trim()
    if([string]::IsNullOrWhiteSpace($branch)){
        git checkout -b main
    } elseif($branch -ne "main"){
        git branch -M main
    }
}

# Local identity only if missing.
$gitName = (git config user.name 2>$null)
$gitEmail = (git config user.email 2>$null)

if([string]::IsNullOrWhiteSpace($gitName)){
    git config user.name $Owner
}
if([string]::IsNullOrWhiteSpace($gitEmail)){
    $noreply = (gh api user --jq ".id").Trim() + "+$Owner@users.noreply.github.com"
    git config user.email $noreply
}
Write-Host "GIT_IDENTITY=PASS"

# ------------------------------------------------------------
# 7. Stage and inspect
# ------------------------------------------------------------
git add -A
if($LASTEXITCODE -ne 0){ throw "GIT_ADD=FAIL" }

$stagedCount = [int]((git diff --cached --name-only | Measure-Object -Line).Lines)
Write-Host ("STAGED_FILES=" + $stagedCount)
if($stagedCount -le 0){
    Write-Host "STAGED_FILES=0"
}

# Block accidental ignored/auth files if any somehow became tracked.
$tracked = git ls-files
$forbidden = $tracked | Where-Object {
    $_ -match '(^|/)\.azure/' -or
    $_ -match '(^|/)\.databrickscfg$' -or
    $_ -match '(^|/)\.env($|\.)' -or
    $_ -match 'credentials?' -or
    $_ -match '(^|/)secrets?/'
}
if($forbidden){
    Write-Host "TRACKED_SECRET_PATH_CHECK=FAIL"
    $forbidden | ForEach-Object { Write-Host ("FORBIDDEN_TRACKED_PATH=" + $_) }
    throw "TRACKED_SECRET_PATH_BLOCKED"
}
Write-Host "TRACKED_SECRET_PATH_CHECK=PASS"

# ------------------------------------------------------------
# 8. Create private GitHub repo if absent
# ------------------------------------------------------------
$oldEA = $ErrorActionPreference
$ErrorActionPreference = "Continue"
gh repo view "$Owner/$RepoName" *> $null
$repoExists = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $oldEA

if(-not $repoExists){
    Write-Host "GITHUB_REPO=CREATE_PRIVATE"
    gh repo create "$Owner/$RepoName" `
        --private `
        --description "TechScope - Data & AI Knowledge Ops PoC" `
        --source "." `
        --remote origin
    if($LASTEXITCODE -ne 0){ throw "GITHUB_REPO_CREATE=FAIL" }
} else {
    Write-Host "GITHUB_REPO=REUSED"
    $remotes = git remote
    if($remotes -notcontains "origin"){
        git remote add origin $Remote
    } else {
        git remote set-url origin $Remote
    }
}
Write-Host "GITHUB_REPO=PASS"

# ------------------------------------------------------------
# 9. Commit snapshot
# ------------------------------------------------------------
if($stagedCount -gt 0){
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm K"
    git commit -m "chore: checkpoint TechScope implementation before P1E relation repair ($stamp)"
    if($LASTEXITCODE -ne 0){ throw "GIT_COMMIT=FAIL" }
    Write-Host "GIT_COMMIT=PASS"
} else {
    Write-Host "GIT_COMMIT=NO_CHANGES"
}

$commit = (git rev-parse HEAD).Trim()
Write-Host ("COMMIT_SHA=" + $commit)

# ------------------------------------------------------------
# 10. Push
# ------------------------------------------------------------
Write-Host "GIT_PUSH=START"
git push -u origin main
if($LASTEXITCODE -ne 0){ throw "GIT_PUSH=FAIL" }
Write-Host "GIT_PUSH=PASS"

# ------------------------------------------------------------
# 11. Verify remote commit
# ------------------------------------------------------------
$remoteSha = (gh api "repos/$Owner/$RepoName/commits/main" --jq ".sha").Trim()
if($LASTEXITCODE -ne 0){ throw "REMOTE_VERIFY=FAIL" }

Write-Host ("REMOTE_MAIN_SHA=" + $remoteSha)
if($remoteSha -ne $commit){
    throw "REMOTE_SHA_MISMATCH local=$commit remote=$remoteSha"
}

Write-Host "REMOTE_VERIFY=PASS"
Write-Host ("GITHUB_REPO_URL=https://github.com/$Owner/$RepoName")
Write-Host "REPOSITORY_VISIBILITY=PRIVATE"
Write-Host "CHECKPOINT=PASS"
Write-Host "NEXT_ACTION=VERIFY_GITHUB_THEN_RESUME_P1E_RELATION"
