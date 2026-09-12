"""Read-only external Qdrant readiness probe with machine-readable output."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from src.reliability.qdrant_probe import probe_qdrant


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    args = parser.parse_args()
    load_dotenv(args.env_file) if args.env_file else load_dotenv()
    result = probe_qdrant()
    print(json.dumps(result))
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
