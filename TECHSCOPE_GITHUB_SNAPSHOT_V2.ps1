$ErrorActionPreference = "Stop"

$RepoRoot = "C:\TechScope"
$RepoName = "TechScope"
$Owner = "elle0529"
$Remote = "https://github.com/$Owner/$RepoName.git"

Write-Host ""
Write-Host "TechScope GitHub Snapshot v2"
Write-Host "Security fix: sanitize SQL password before push"
Write-Host ""

if(-not (Test-Path $RepoRoot)){ throw "TECHSCOPE_ROOT_NOT_FOUND" }

Copy-Item `
    (Join-Path $PSScriptRoot "_techscope_payload\tools\sanitize_p1d_sql_verify.py") `
    (Join-Path $RepoRoot "tools\sanitize_p1d_sql_verify.py") `
    -Force

python.exe (Join-Path $RepoRoot "tools\sanitize_p1d_sql_verify.py")
if($LASTEXITCODE-ne 0){ throw "SQL_PASSWORD_SANITIZE=FAIL" }

Set-Location $RepoRoot

if(-not (Get-Command git.exe -ErrorAction SilentlyContinue)){ throw "GIT_NOT_FOUND" }

if(-not (Get-Command gh.exe -ErrorAction SilentlyContinue)){
    if(Get-Command winget.exe -ErrorAction SilentlyContinue){
        Write-Host "GH_CLI_INSTALL=START"
        winget install --id GitHub.cli --exact --accept-package-agreements --accept-source-agreements
        if($LASTEXITCODE-ne 0){ throw "GH_CLI_INSTALL=FAIL" }
        $possible=@(
            "$env:ProgramFiles\GitHub CLI",
            "$env:LOCALAPPDATA\Programs\GitHub CLI"
        )
        foreach($p in $possible){
            if(Test-Path (Join-Path $p "gh.exe")){ $env:Path="$p;$env:Path" }
        }
    } else {
        throw "GH_CLI_NOT_FOUND"
    }
}

$oldEA=$ErrorActionPreference
$ErrorActionPreference="Continue"
gh auth status *> $null
$auth=$LASTEXITCODE
$ErrorActionPreference=$oldEA

if($auth-ne 0){
    Write-Host "GH_AUTH=REQUIRED"
    gh auth login --hostname github.com --git-protocol https --web
    if($LASTEXITCODE-ne 0){ throw "GH_AUTH_LOGIN=FAIL" }
}
Write-Host "GH_AUTH=PASS"

$login=(gh api user --jq ".login").Trim()
if($login-ne $Owner){ throw "GH_USER_MISMATCH expected=$Owner actual=$login" }
Write-Host ("GH_USER="+$login)

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

Write-Host "SECRET_SCAN=START"

$excludeDirs=@(".git",".azure","node_modules",".venv","venv","__pycache__",".cache",".pbi","LocalCache")
$extensions=@(".py",".ps1",".cmd",".bat",".sh",".md",".txt",".json",".yaml",".yml",".toml",".ini",".cfg",".conf",".sql",".bicep",".js",".ts",".tsx",".jsx",".csv",".xml",".tmdl",".pbip")

$literalPasswordRule='(?i)\b(?:[A-Za-z_][A-Za-z0-9_]*PASSWORD[A-Za-z0-9_]*|PASSWORD)\s*=\s*["''][^"'']{4,}["'']'
$databricksPatRule='dapi[a-zA-Z0-9]{20,}'
$openaiRule='sk-[A-Za-z0-9_-]{16,}'
$privateKeyRule='-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'
$secretLiteralRule='(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|refresh[_-]?token)\s*[:=]\s*["''][^"'']{8,}["'']'

$hits=New-Object System.Collections.Generic.List[object]

Get-ChildItem $RepoRoot -Recurse -File -Force | ForEach-Object {
    $file=$_
    $rel=$file.FullName.Substring($RepoRoot.Length).TrimStart("\")
    $parts=$rel -split '[\\/]'
    if($parts | Where-Object { $excludeDirs -contains $_ }){ return }
    if($extensions -notcontains $file.Extension.ToLowerInvariant()){ return }

    try{
        $lineNo=0
        Get-Content -LiteralPath $file.FullName -ErrorAction Stop | ForEach-Object {
            $lineNo++
            $line=$_
            $rules=@()
            if($line-match $literalPasswordRule){ $rules+="PASSWORD_LITERAL" }
            if($line-match $databricksPatRule){ $rules+="DATABRICKS_PAT" }
            if($line-match $openaiRule){ $rules+="OPENAI_STYLE_KEY" }
            if($line-match $privateKeyRule){ $rules+="PRIVATE_KEY" }
            if($line-match $secretLiteralRule){ $rules+="SECRET_LITERAL" }

            foreach($r in $rules){
                $hits.Add([PSCustomObject]@{File=$rel;Line=$lineNo;Rule=$r})
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

if(-not (Test-Path ".git")){
    git init
    if($LASTEXITCODE-ne 0){ throw "GIT_INIT=FAIL" }
    git branch -M main
    Write-Host "GIT_INIT=PASS"
}else{
    Write-Host "GIT_INIT=REUSED"
    git branch -M main
}

if([string]::IsNullOrWhiteSpace((git config user.name 2>$null))){
    git config user.name $Owner
}
if([string]::IsNullOrWhiteSpace((git config user.email 2>$null))){
    $uid=(gh api user --jq ".id").Trim()
    git config user.email "$uid+$Owner@users.noreply.github.com"
}
Write-Host "GIT_IDENTITY=PASS"

git add -A
if($LASTEXITCODE-ne 0){ throw "GIT_ADD=FAIL" }

$staged=[int]((git diff --cached --name-only | Measure-Object -Line).Lines)
Write-Host ("STAGED_FILES="+$staged)

$tracked=git ls-files
$forbidden=$tracked | Where-Object {
    $_ -match '(^|/)\.azure/' -or
    $_ -match '(^|/)\.databrickscfg$' -or
    $_ -match '(^|/)\.env($|\.)' -or
    $_ -match '(^|/)secrets?/'
}
if($forbidden){
    $forbidden | ForEach-Object { Write-Host ("FORBIDDEN_TRACKED_PATH="+$_) }
    throw "TRACKED_SECRET_PATH_BLOCKED"
}
Write-Host "TRACKED_SECRET_PATH_CHECK=PASS"

$oldEA=$ErrorActionPreference
$ErrorActionPreference="Continue"
gh repo view "$Owner/$RepoName" *> $null
$exists=($LASTEXITCODE-eq 0)
$ErrorActionPreference=$oldEA

if(-not $exists){
    Write-Host "GITHUB_REPO=CREATE_PRIVATE"
    gh repo create "$Owner/$RepoName" --private --description "TechScope - Data & AI Knowledge Ops PoC" --source "." --remote origin
    if($LASTEXITCODE-ne 0){ throw "GITHUB_REPO_CREATE=FAIL" }
}else{
    Write-Host "GITHUB_REPO=REUSED"
    $remotes=git remote
    if($remotes-notcontains "origin"){ git remote add origin $Remote }
    else{ git remote set-url origin $Remote }
}
Write-Host "GITHUB_REPO=PASS"

if($staged-gt 0){
    git commit -m "chore: checkpoint TechScope implementation before P1E relation repair"
    if($LASTEXITCODE-ne 0){ throw "GIT_COMMIT=FAIL" }
    Write-Host "GIT_COMMIT=PASS"
}else{
    Write-Host "GIT_COMMIT=NO_CHANGES"
}

$commit=(git rev-parse HEAD).Trim()
Write-Host ("COMMIT_SHA="+$commit)

Write-Host "GIT_PUSH=START"
git push -u origin main
if($LASTEXITCODE-ne 0){ throw "GIT_PUSH=FAIL" }
Write-Host "GIT_PUSH=PASS"

$remoteSha=(gh api "repos/$Owner/$RepoName/commits/main" --jq ".sha").Trim()
Write-Host ("REMOTE_MAIN_SHA="+$remoteSha)

if($remoteSha-ne $commit){
    throw "REMOTE_SHA_MISMATCH local=$commit remote=$remoteSha"
}

Write-Host "REMOTE_VERIFY=PASS"
Write-Host ("GITHUB_REPO_URL=https://github.com/$Owner/$RepoName")
Write-Host "REPOSITORY_VISIBILITY=PRIVATE"
Write-Host "CHECKPOINT=PASS"
Write-Host "NEXT_ACTION=VERIFY_GITHUB_THEN_RESUME_P1E_RELATION"
