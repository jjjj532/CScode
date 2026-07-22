# P6-2: Desktop CI/CD 完善

## Problem
Desktop builds have known Windows issues (PDB collision, icon.ico missing)
and the GitHub Actions workflow needs hardening. This iteration fixes the
identified pain points and adds CI reliability improvements.

## Requirements
1. Fix Windows PDB filename collision — rename lib target to avoid `.pdb` conflict
2. Ensure `icons/icon.ico` exists for Windows resource embedding
3. Add CI workflow validation (dry-run parsable checks)
4. Improve build script robustness

## Acceptance Criteria
- [ ] lib target renamed from `cscode_desktop` to `cscode_app` in Cargo.toml
- [ ] `main.rs` updated to use new lib name (`cscode_app::run()`)
- [ ] `icon.ico` can be generated from existing 128x128 PNG
- [ ] CI workflow validated (no syntax errors in `.github/workflows/build.yml`)
- [ ] Build script handles edge cases (missing env, cleanup)

## Implementation Plan
1. Fix Cargo.toml lib name + main.rs reference
2. Generate icon.ico from existing icons
3. Validate CI workflow file
4. Test locally (compile check, script dry-run)
