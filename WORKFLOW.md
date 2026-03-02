# Tennis-Sim Development Workflow

> **This applies to all developers — human or AI agent (GOB, etc.)**

---

## Branch Structure

```
main        ← stable tagged releases only. NEVER commit here directly.
dev         ← integration branch. default base for all work.
feature/*   ← new capabilities, branched from dev
fix/*       ← bug fixes, branched from dev
```

---

## The Daily Loop

```bash
# 1. Start from dev
git checkout dev
git pull origin dev

# 2. Create a branch for your work
git checkout -b feature/my-thing

# 3. Work. Commit small and often.
git add -p
git commit -m 'feat: description'

# 4. Test your change

# 5. Push to dev branch
git push origin feature/my-thing

# 6. Done — merge back to dev
git checkout dev
git merge --no-ff feature/my-thing
git push origin dev

# 7. Stable milestone? Merge to main and tag.
git checkout main
git merge --no-ff dev -m 'release: v0.2.0'
git tag -a v0.2.0 -m 'v0.2.0 — description'
git push origin main --tags
git checkout dev
```

---

## Commit Message Convention

```
feat:   new capability or behavior
fix:    bug fix
refac:  refactor — no behavior change
chore:  deps, config, tooling, cleanup
docs:   documentation only
```

---

## Pull Before Every Task

**Before starting any work, always pull the latest dev:**
```bash
git checkout dev && git pull origin dev
```

---

## Quick Reference

| Situation | Command |
|---|---|
| Start new work | `git co -b feature/name` |
| Check current state | `git lg` |
| Merge completed branch | `git merge --no-ff feature/name` |
| New release | tag on main |
