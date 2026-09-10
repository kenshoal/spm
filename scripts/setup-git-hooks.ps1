$ErrorActionPreference = "Stop"

$repositoryRoot = git rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0) {
    throw "Run this script from inside the Git repository."
}

git -C $repositoryRoot config core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) {
    throw "Could not configure Git hooks."
}

Write-Host "Git hooks enabled for $repositoryRoot"
