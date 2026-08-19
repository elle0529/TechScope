param(
    [string]$RepoRoot = "C:\TechScope",
    [string]$CommitMessage = "Integrate Dynamic Architecture exporter with GitHub"
)

$ErrorActionPreference = "Stop"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)

    & git @Args
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Args -join ' ') failed with exit code $LASTEXITCODE"
    }
}

Write-Host "DYNAMIC_ARCHITECTURE_GITHUB_SYNC=START"
Write-Host "REPO_ROOT=$RepoRoot"

if (-not (Test-Path -LiteralPath $RepoRoot)) {
    throw "Repository root not found: $RepoRoot"
}

$git = Get-Command git -ErrorAction SilentlyContinue
if (-not $git) {
    throw "Git was not found in PATH."
}

Push-Location $RepoRoot
try {
    if (-not (Test-Path -LiteralPath ".git")) {
        throw "$RepoRoot is not a Git repository."
    }

    $runner = Join-Path $RepoRoot "RUN_DYNAMIC_ARCHITECTURE_EXPORT.ps1"
    if (-not (Test-Path -LiteralPath $runner)) {
        throw "Dynamic Architecture exporter runner missing: $runner"
    }

    # Fail-safe: never mix unrelated pre-staged user changes into this commit.
    $preStaged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect staged Git changes."
    }

    if ($preStaged.Count -gt 0) {
        Write-Host "PREEXISTING_STAGED_CHANGES=FAIL"
        $preStaged | ForEach-Object { Write-Host "  $_" }
        throw "Unrelated staged changes already exist. Unstage or commit them before GitHub sync."
    }
    Write-Host "PREEXISTING_STAGED_CHANGES=NONE"

    # Generate and verify the latest portfolio before staging.
    & $runner
    if ($LASTEXITCODE -ne 0) {
        throw "Dynamic Architecture export failed."
    }
    Write-Host "LOCAL_EXPORT_AND_VERIFY=PASS"

    $branch = (& git branch --show-current).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($branch)) {
        throw "Current Git branch could not be resolved or is detached."
    }
    Write-Host "GIT_BRANCH=$branch"

    $origin = (& git remote get-url origin).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($origin)) {
        throw "Git remote 'origin' is not configured."
    }
    Write-Host "GIT_ORIGIN=$origin"

    # Fetch is read-only and lets us fail safely if the remote branch moved.
    Invoke-Git fetch origin $branch

    $remoteBranchExists = $false
    & git show-ref --verify --quiet "refs/remotes/origin/$branch"
    if ($LASTEXITCODE -eq 0) {
        $remoteBranchExists = $true
    }

    if ($remoteBranchExists) {
        $behindText = (& git rev-list --count "HEAD..origin/$branch").Trim()
        if ($LASTEXITCODE -ne 0) {
            throw "Could not calculate remote-ahead state."
        }

        $behind = [int]$behindText
        Write-Host "REMOTE_AHEAD_COMMITS=$behind"

        if ($behind -gt 0) {
            throw "origin/$branch is ahead by $behind commit(s). Pull/rebase first; sync stopped before staging."
        }
    }
    else {
        Write-Host "REMOTE_BRANCH_EXISTS=NO"
    }

    # Exact allowlist only. Runtime/demo CSV changes are intentionally excluded.
    $targets = @(
        ".github/workflows/dynamic-architecture-export.yml",
        "RUN_DYNAMIC_ARCHITECTURE_GITHUB_SYNC.ps1",
        "RUN_DYNAMIC_ARCHITECTURE_EXPORT.ps1",
        "tools/export_dynamic_architecture_portfolio.py",
        "tools/verify_dynamic_architecture_export.py",
        "docs/dynamic-architecture-exporter.md",
        "docs/dynamic-architecture-github-integration.md",
        "docs/portfolio/TechScope_Dynamic_Architecture_Portfolio.md",
        "docs/portfolio/diagrams/01_dynamic_architecture_3layer.mmd",
        "docs/portfolio/diagrams/02_current_as_built_architecture.mmd",
        "docs/portfolio/diagrams/03_ai_operations_feedback_loop.mmd",
        "results/latest/dynamic-architecture-export.json"
    )

    $existingTargets = @()
    foreach ($rel in $targets) {
        if (Test-Path -LiteralPath (Join-Path $RepoRoot $rel)) {
            $existingTargets += $rel
        }
        else {
            # Include tracked deletions if any, but ignore never-existing optional files.
            & git ls-files --error-unmatch -- $rel *> $null
            if ($LASTEXITCODE -eq 0) {
                $existingTargets += $rel
            }
        }
    }

    if ($existingTargets.Count -eq 0) {
        throw "No GitHub integration/export files were found to stage."
    }

    & git add -- $existingTargets
    if ($LASTEXITCODE -ne 0) {
        throw "git add failed."
    }

    $staged = @(& git diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect staged files after git add."
    }

    $allowed = @{}
    foreach ($rel in $targets) {
        $allowed[$rel.Replace("\","/")] = $true
    }

    $unexpected = @()
    foreach ($rel in $staged) {
        $normalized = $rel.Replace("\","/")
        if (-not $allowed.ContainsKey($normalized)) {
            $unexpected += $normalized
        }
    }

    if ($unexpected.Count -gt 0) {
        Write-Host "UNEXPECTED_STAGED_FILES=FAIL"
        $unexpected | ForEach-Object { Write-Host "  $_" }
        & git reset -- $unexpected
        throw "Unexpected files entered the staging area. They were unstaged; sync stopped."
    }

    Write-Host "STAGED_ALLOWLIST_VERIFY=PASS"
    foreach ($rel in $staged) {
        Write-Host "STAGED=$rel"
    }

    & git diff --cached --quiet
    $hasChanges = ($LASTEXITCODE -ne 0)

    if ($hasChanges) {
        Invoke-Git commit -m $CommitMessage
        Write-Host "GIT_COMMIT=PASS"
    }
    else {
        Write-Host "GIT_COMMIT=SKIP_NO_CHANGES"
    }

    $localSha = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not resolve local HEAD."
    }

    if ($remoteBranchExists) {
        Invoke-Git push origin $branch
    }
    else {
        Invoke-Git push -u origin $branch
    }
    Write-Host "GIT_PUSH=PASS"

    $remoteLine = (& git ls-remote origin "refs/heads/$branch" | Select-Object -First 1)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remoteLine)) {
        throw "Remote branch verification failed."
    }

    $remoteSha = ($remoteLine -split "\s+")[0].Trim()
    Write-Host "LOCAL_HEAD=$localSha"
    Write-Host "REMOTE_HEAD=$remoteSha"

    if ($remoteSha -ne $localSha) {
        throw "Remote SHA does not match local HEAD after push."
    }

    # Report other dirty files but do not touch them.
    $remainingDirty = @(& git status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect final Git status."
    }

    if ($remainingDirty.Count -gt 0) {
        Write-Host "NON_TARGET_DIRTY_FILES_PRESERVED=YES"
        $remainingDirty | ForEach-Object { Write-Host "DIRTY_PRESERVED=$_" }
    }
    else {
        Write-Host "NON_TARGET_DIRTY_FILES_PRESERVED=NONE"
    }

    Write-Host "GITHUB_WORKFLOW=.github/workflows/dynamic-architecture-export.yml"
    Write-Host "GITHUB_DYNAMIC_ARCHITECTURE_SYNC=PASS"
}
finally {
    Pop-Location
}
