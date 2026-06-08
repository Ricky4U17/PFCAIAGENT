"""
app/magnetics/tools/validate.py
CLI validator for the magnetics database.

Usage:
  python3 -m app.magnetics.tools.validate
  python3 -m app.magnetics.tools.validate --material 3C95
  python3 -m app.magnetics.tools.validate --pending
"""
import sys, argparse
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent.parent.parent))

def main():
    parser = argparse.ArgumentParser(description="Validate MagneticsDB material files")
    parser.add_argument("--material", default=None, help="Validate single material key")
    parser.add_argument("--pending",  action="store_true", help="Validate pending materials only")
    parser.add_argument("--fix",      action="store_true", help="Auto-fill loss tables from Steinmetz")
    args = parser.parse_args()

    from app.magnetics.db import MagneticsDB
    db = MagneticsDB()
    stat = db.status()

    print(f"\n{'='*60}")
    print(f"MagneticsDB Validation Report")
    print(f"{'='*60}")
    print(f"  Materials loaded:  {stat['total_materials']} ({stat['ferrite_grades']} ferrite, {stat['powder_grades']} powder)")
    print(f"  Pending review:    {stat['pending_review']}")
    print(f"  Core entries:      {stat['ferroxcube_cores']} FC + {stat['tdk_cores']} TDK + {stat['magnetics_toroids']} Mag")
    print(f"  Wire entries:      {stat['wire_entries']}")
    print(f"  Load time:         {stat['load_time_ms']:.0f} ms")

    if args.material:
        keys = [args.material]
    elif args.pending:
        keys = [k for k in db._materials if k.startswith("pending:")]
    else:
        keys = [k for k in db._materials if not k.startswith("pending:")]

    print(f"\n{'─'*60}")
    print(f"Validating {len(keys)} materials...\n")

    pass_count = fail_count = 0
    for key in sorted(keys):
        d = db._materials.get(key, {})
        errors = db.validate_material_dict(d)
        if errors:
            fail_count += 1
            print(f"  ✗ {key}")
            for e in errors:
                print(f"      → {e}")
        else:
            pass_count += 1
            print(f"  ✓ {key}")

    print(f"\n{'─'*60}")
    print(f"Result: {pass_count} PASS  {fail_count} FAIL")

    if stat["load_errors"]:
        print(f"\nLoad errors:")
        for e in stat["load_errors"]:
            print(f"  ✗ {e}")

    sys.exit(0 if fail_count == 0 else 1)

if __name__ == "__main__":
    main()
