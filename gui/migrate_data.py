"""Runs the data migration on request, without starting the app.

    python gui/migrate_data.py --check                 # report only, writes nothing
    python gui/migrate_data.py                         # migrate the real data folder (same as the app's first start)
    python gui/migrate_data.py --data-dir <folder>     # convert the schema of another folder (e.g. a copy)
    python gui/migrate_data.py --data-dir <folder> --check
    python gui/migrate_data.py --redo       # an older app version changed the old files after the
                                            # conversion: set the new files aside and convert again
    python gui/migrate_data.py --keep-new   # ...or keep the new files and stop the warning

Close the app before converting. What the app does on its first start is exactly the same (see migration.py): old files are only
read, new files are written next to them, verified record by record, and a marker prevents a second
run. The report shows file names, sizes, record counts and SHA-256 hashes, never the data itself.
Exit code: 0 = OK / nothing to do, 1 = migration failed (the old files are untouched), 2 = bad usage.
"""
import argparse
import sys
from pathlib import Path

import migration


def _print_files(directory: Path) -> None:
    rows = migration.describe(directory)
    if not rows:
        print("  (no data files)")
    for row in rows:
        records = "?" if row["records"] is None else row["records"]
        print(f"  schema {row['schema']}  {row['file']:<26} {row['size']:>9} bytes  {records:>5} records  sha256 {row['sha256']}")
    for name in (migration.LEGACY_RELOCATION_MARKER, migration.RELOCATION_MARKER, migration.SCHEMA_MARKER):
        if (directory / name).exists():
            print(f"  marker   {name}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, help="folder to convert (default: the app's data folder, "
                                                  "including the one-time copy from the old location)")
    ap.add_argument("--check", action="store_true", help="only report what is there; write nothing")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--redo", action="store_true",
                       help="rename the new files and the marker to *.before-redo-<time>, then convert the old files again")
    group.add_argument("--keep-new", action="store_true",
                       help="keep the new files; record that the old files changed so the warning stops")
    args = ap.parse_args(argv)
    if args.check and (args.redo or args.keep_new):
        ap.error("--check cannot be combined with --redo / --keep-new")

    if args.data_dir is not None:
        directory = args.data_dir
        if not directory.is_dir():
            print(f"Not a folder: {directory}", file=sys.stderr)
            return 2
    else:
        directory = migration.data_dir_from_env() or migration.user_data_dir()

    print(f"Data folder: {directory}")
    if directory.is_dir():
        _print_files(directory)
    done = (directory / migration.SCHEMA_MARKER).exists()
    changed = migration.old_files_changed_since_conversion(directory) if done else []
    if args.check:
        legacy = any((directory / n).exists() for n in migration.LEGACY_FILE_NAMES)
        if done:
            print("Schema migration: already done (marker present).")
            if changed:
                print(f"WARNING: old files changed after the conversion: {', '.join(changed)} "
                      "(use --redo to convert them again, or --keep-new).")
        elif legacy:
            print("Schema migration: pending (old files found; run without --check to convert).")
        else:
            print("Schema migration: nothing to convert.")
        return 0

    if args.redo or args.keep_new:
        if not done:
            print("No conversion has been done in this folder yet; run without --redo / --keep-new.", file=sys.stderr)
            return 2
        if args.keep_new:
            kept = migration.accept_new_files(directory)
            print(f"Kept the new files; acknowledged old-file changes: {', '.join(kept) or 'none'}.")
            return 0
        result = migration.redo_conversion(directory)
        print(f"Schema migration (redo): {result.status}")
        if result.status == "error":
            print(result.error, file=sys.stderr)
            return 1
        print("Files now:")
        _print_files(directory)
        return 0

    if args.data_dir is not None:
        result = migration.convert_schema(directory)
    else:
        relocation = migration.prepare_data_dir()
        print(f"Relocation: {relocation.status}")
        result = relocation.schema_result or relocation
    print(f"Schema migration: {result.status}")
    if result.status == "error":
        print(result.error, file=sys.stderr)
        return 1
    print("Files now:")
    _print_files(result.directory)
    return 0


if __name__ == "__main__":
    sys.exit(main())
