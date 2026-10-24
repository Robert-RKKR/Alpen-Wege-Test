#!/usr/bin/env python3
"""Copy the result of a migration run from a scratch copy into the real repo, in one go.

    python deliver.py WORK_COPY REPO BASE [--dry-run]

BASE is the copy the repo must still equal (D1: the untouched copy `old/`; D2: a snapshot of `work/` taken at D1,
or the backup_after_phase1 archive extracted). The script refuses to run when someone changed, added or deleted a
file in app/ or tests/ of the repo since BASE (it would overwrite or delete that work), when one of the three
folders has no app/main.py (wrong folder), and when deleting is not allowed in the repo (it tests this first,
so it cannot stop half way). After copying it checks that app/ and tests/ are identical to the work copy.

- app/ and tests/: made identical to the work copy (new files copied, changed files overwritten,
  files that no longer exist in the work copy are deleted from the repo).
- scripts/: files that are new or changed in the work copy are copied; nothing in scripts/ is deleted
  (the repo keeps its own scripts/sql/ and others).
- __pycache__ folders and route_dumps/ are ignored. README.md and Routing/ are not touched.

Always run with --dry-run first and read the list. Deleting needs the delete permission of the folder.
"""
import filecmp
import shutil
import sys
from pathlib import Path

SYNC_DIRS = ("app", "tests")        # mirrored, with deletes
ADD_ONLY_DIRS = ("scripts",)        # copy new and changed files only


def files_under(root: Path, sub: str) -> dict[str, Path]:
    base = root / sub
    return {
        str(p.relative_to(root)): p
        for p in base.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
    }


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) != 3:
        print(__doc__)
        return 2
    work, repo, base = Path(args[0]).resolve(), Path(args[1]).resolve(), Path(args[2]).resolve()
    if not (work / "app" / "main.py").exists() or not (base / "app" / "main.py").exists() or not (repo / "app" / "main.py").exists():
        print("STOP: app/main.py is missing in WORK_COPY, REPO or BASE: wrong folder?")
        return 2
    foreign = []
    for sub in SYNC_DIRS:                                   # app/ and tests/ must still equal BASE
        have, was = files_under(repo, sub), files_under(base, sub)
        foreign += [f"changed in repo: {r}" for r in sorted(have.keys() & was.keys()) if not filecmp.cmp(have[r], was[r], shallow=False)]
        foreign += [f"added in repo:   {r}" for r in sorted(have.keys() - was.keys())]
        foreign += [f"deleted in repo: {r}" for r in sorted(was.keys() - have.keys())]
    for r, p in files_under(work, "scripts").items():       # scripts/ is add-only: only files we would overwrite matter
        t = repo / r
        if t.exists() and not filecmp.cmp(p, t, shallow=False) and (base / r).exists() and not filecmp.cmp(t, base / r, shallow=False):
            foreign.append(f"changed in repo: {r}")
    if foreign:
        print("STOP: the repo is not in the state BASE describes (someone edited it after the scratch copy was made):")
        print("\n".join("  " + f for f in foreign))
        return 3
    if not dry:                                              # can we delete here? (fails now, not half-way)
        probe = repo / "app" / ".deliver_probe"
        probe.write_text("x")
        probe.unlink()
    added, changed, deleted = [], [], []
    for sub in SYNC_DIRS + ADD_ONLY_DIRS:
        src, dst = files_under(work, sub), files_under(repo, sub)
        for rel, path in sorted(src.items()):
            target = repo / rel
            if rel not in dst:
                added.append(rel)
            elif not filecmp.cmp(path, target, shallow=False):
                changed.append(rel)
            else:
                continue
            if not dry:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        if sub in SYNC_DIRS:
            for rel in sorted(set(dst) - set(src)):
                deleted.append(rel)
                if not dry:
                    (repo / rel).unlink()
    if not dry:
        for sub in SYNC_DIRS:   # remove folders that are now empty (for example app/.../routes/track.py leftovers)
            for d in sorted((repo / sub).rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
    if not dry:
        for sub in SYNC_DIRS:
            a, b = files_under(work, sub), files_under(repo, sub)
            if a.keys() != b.keys() or any(not filecmp.cmp(a[r], b[r], shallow=False) for r in a):
                print(f"STOP: {sub}/ in the repo is NOT identical to the work copy after delivery")
                return 4
    for label, items in (("ADD", added), ("CHANGE", changed), ("DELETE", deleted)):
        for rel in items:
            print(f"{label:7}{rel}")
    print(f"{'DRY RUN: ' if dry else ''}{len(added)} added, {len(changed)} changed, {len(deleted)} deleted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
