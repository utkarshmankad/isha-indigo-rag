"""Backup and restore ISHA without deleting or replacing an existing collection."""
import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from src.reliability.backup import digest, export_collection, restore_collection, verify_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['backup', 'verify', 'restore'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--collection', default='airline_kb')
    parser.add_argument('--target', help='New collection name, required for restore')
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--local-path', help='Local Qdrant directory for an isolated restore drill')
    args = parser.parse_args()
    os.umask(0o077)
    if args.action == 'verify':
        manifest = verify_export(args.directory)
        snapshot_manifest = args.directory / 'snapshot.json'
        if snapshot_manifest.exists():
            expected = json.loads(snapshot_manifest.read_text())
            if digest(args.directory / 'collection.snapshot') != expected['sha256']:
                raise ValueError('Snapshot checksum mismatch')
        print(json.dumps({'status': 'verified', 'points': manifest['points']}))
        return
    load_dotenv(args.env_file) if args.env_file else load_dotenv()
    if args.action == 'restore' and not args.target:
        parser.error('--target is required for restore')
    if args.local_path:
        if args.action != 'restore':
            parser.error('--local-path is only supported for restore drills')
        client = QdrantClient(path=args.local_path)
    else:
        url, key = os.environ.get('QDRANT_URL'), os.environ.get('QDRANT_API_KEY')
        if not url or not key:
            parser.error('QDRANT_URL and QDRANT_API_KEY are required')
        client = QdrantClient(url=url, api_key=key, timeout=60)
    try:
        if args.action == 'restore':
            count = restore_collection(client, args.directory, args.target)
            print(json.dumps({'status': 'restored', 'points': count, 'target': args.target}))
            return
        from data.indigo_documents import DOCUMENTS as indigo
        from data.air_india_documents import DOCUMENTS as air_india
        from data.spicejet_documents import DOCUMENTS as spicejet
        from data.dgca_documents import DOCUMENTS as dgca
        manifest = export_collection(client, args.collection, args.directory,
                                     indigo + air_india + spicejet + dgca)
        # Keep the native snapshot outside Qdrant as well as the portable export.
        import httpx
        snapshot = client.create_snapshot(args.collection, wait=True)
        endpoint = (url.rstrip('/') + '/collections/' + quote(args.collection, safe='')
                    + '/snapshots/' + quote(snapshot.name, safe=''))
        part = args.directory / 'collection.snapshot.part'
        with httpx.stream('GET', endpoint, headers={'api-key': key}, timeout=120,
                          follow_redirects=False) as response:
            response.raise_for_status()
            with part.open('xb') as stream:
                for block in response.iter_bytes():
                    stream.write(block)
        part.rename(args.directory / 'collection.snapshot')
        (args.directory / 'snapshot.json').write_text(json.dumps({
            'name': snapshot.name, 'sha256': digest(args.directory / 'collection.snapshot')}))
        print(json.dumps({'status': 'backed_up', 'points': manifest['points']}))
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Provider exception strings can contain connection URLs; keep output redacted.
        print(f'Operation failed ({type(exc).__name__}); inspect connectivity and backup integrity.', file=sys.stderr)
        sys.exit(1)
