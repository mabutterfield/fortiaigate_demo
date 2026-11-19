"""Print one validated catalog view; no network access or writes."""
import argparse
import json
from pathlib import Path
import sys
from .loader import build_views, load
from .mcp_compile import compile_registry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('view', choices=('models', 'mcp', 'student', 'faig', 'mcp-runtime'))
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--source-commit', help='Optional deployment source revision metadata')
    args = parser.parse_args()
    catalog, errors = load(args.root)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    view = compile_registry(catalog) if args.view == 'mcp-runtime' else build_views(catalog, source_commit=args.source_commit)[args.view]
    print(json.dumps(view, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
