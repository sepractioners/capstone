# GitHub Action: Repository Validation Setup

The `.github/workflows/repo-validation.yml` workflow automates repository validation and runs:
- **On every push to master** 
- **On pull requests to master**
- **Nightly at 2 AM UTC** (scheduled)

## Features

### 1. **Automated Validation** (Always Enabled)
- README structure and completeness checks
- Setup script verification (linux, mac, windows)
- Agent code existence validation
- Agent test execution (pytest with coverage)
- Documentation link verification

### 2. **Multi-Platform Testing** (Always Enabled)
- Ubuntu (Linux)
- Windows
- macOS

Results are logged and artifacts uploaded automatically.

### 3. **Python Package Caching** (Always Enabled)
Speeds up subsequent runs by caching `.venv` directory.

### 4. **Coverage Reports** (Always Enabled)
- XML reports for CI/CD integration
- HTML reports for manual review
- Uploaded as artifacts

### 5. **Test Results Publishing** (Requires no setup)
Results automatically posted to GitHub workflow summary.

### 6. **Pull Request Comments** (Enabled for PRs, requires no setup)
Validation status posted automatically as a comment on PRs.

### 7. **Email Notifications** (Requires GitHub Secrets setup)

To enable email notifications on failures, add these secrets to your GitHub repository:

**Repository Settings → Secrets and variables → Actions**

```
EMAIL_SERVER        = your-smtp-server.com
EMAIL_PORT          = 587
EMAIL_USERNAME      = your-email@example.com
EMAIL_PASSWORD      = your-email-password (or app-specific password)
EMAIL_RECIPIENT     = recipient@example.com
```

**Recommended providers:**
- **Gmail**: 
  - Server: `smtp.gmail.com`
  - Port: `587`
  - Use [App Password](https://support.google.com/accounts/answer/185833) instead of regular password
  
- **Outlook**:
  - Server: `smtp-mail.outlook.com`
  - Port: `587`
  
- **Office 365**:
  - Server: `smtp.office365.com`
  - Port: `587`

### 8. **Codecov Integration** (Optional, requires no setup)
Coverage data automatically uploaded to Codecov (if repo is public or Codecov token configured).

**To enable Codecov tokens:**
1. Go to [codecov.io](https://codecov.io)
2. Connect GitHub repository
3. Add token to repo secrets as `CODECOV_TOKEN` (optional for public repos)

## Workflow Execution Timeline

### On Push to Master
1. ✅ Validate documentation structure
2. ✅ Run tests with coverage on 3 platforms (3-5 minutes)
3. ✅ Post summary to workflow summary
4. 📧 Send email if validation fails
5. 📊 Upload coverage reports
6. 🧪 Publish test results

### On Pull Request
1. ✅ Validate documentation structure
2. ✅ Run tests with coverage on 3 platforms
3. 💬 Post validation status as PR comment
4. 📊 Upload coverage reports
5. 🧪 Publish test results

### Nightly (2 AM UTC)
1. ✅ Full validation on 3 platforms
2. 📊 Generate coverage baseline
3. 🧪 Archive results for comparison

## Viewing Results

### Workflow Results
1. Go to **Actions** tab → **Repository Validation**
2. Click the latest run
3. View logs for each platform

### Artifacts
1. Click **Artifacts** dropdown
2. Download:
   - `validation-reports` — Markdown reports per platform
   - `coverage-reports` — HTML coverage dashboards
   - `test-results` — JUnit XML test results

### Test Results
- **Published to workflow summary** → View in action details
- **Published to PR** as inline comment (for pull requests)

### Coverage
- **Codecov.io** (if enabled) — Interactive dashboard
- **HTML reports** in artifacts → Open `coverage-report-*/index.html` in browser

## Troubleshooting

### Email not sending?
1. Check GitHub secrets are set correctly
2. Verify email credentials
3. Check if SMTP server requires authentication
4. Try with less restrictive email provider (test with Gmail first)

### Tests failing on specific platform?
1. Check platform-specific logs in workflow
2. Note Windows/macOS path differences
3. See test results in artifacts

### Coverage not uploading?
1. Check Codecov token (if using private repo)
2. Verify `pytest-cov` installed (automatic in workflow)
3. Review coverage report in artifacts

### PR comment not posting?
1. Verify workflow has `pull_request` trigger
2. Check GitHub token has permissions (automatic for GitHub Actions)
3. See comment history on PR

## Customization

### Change nightly schedule
Edit `.github/workflows/repo-validation.yml`:
```yaml
schedule:
  - cron: '0 2 * * *'  # Change 2 AM UTC to your preferred time
```

### Disable email notifications
Remove or comment out email step in `summary` job:
```yaml
# - name: Email notification on failure
#   if: failure() && github.event_name == 'push'
```

### Change coverage thresholds
Update pytest command in `Run agent tests with coverage` step.

### Add more test platforms
Add to `strategy.matrix.os`:
```yaml
os: [ubuntu-latest, windows-latest, macos-latest, ubuntu-20.04]
```

## Cost & Performance

- **GitHub Actions**: Free for public repos, included in GitHub Teams
- **Duration**: ~3-5 minutes per run (faster on subsequent runs due to caching)
- **Artifacts**: Stored for 90 days (default GitHub retention)
- **Codecov**: Free tier available

## Security Notes

- **Secrets**: Never commit email passwords to repo; use GitHub Secrets
- **Artifact retention**: Coverage and test results expire after 90 days
- **Email logs**: GitHub Actions logs are visible to repo members; avoid sensitive data in logs
- **Codecov**: Public coverage data is viewable; consider if this is acceptable

---

**Questions?** See the workflow file: `.github/workflows/repo-validation.yml`
