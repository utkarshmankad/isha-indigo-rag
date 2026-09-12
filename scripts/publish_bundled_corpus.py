"""Backfill visibility only for exact matches of the public bundled corpus."""
import argparse
import contextlib
import io
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from src.ingestion.chunker import ingest_all
from src.reliability.public_corpus import migrate_public_corpus


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--apply', action='store_true')
    p.add_argument('--env-file', type=Path)
    args=p.parse_args()
    load_dotenv(args.env_file) if args.env_file else load_dotenv()
    from data.indigo_documents import DOCUMENTS as a
    from data.air_india_documents import DOCUMENTS as b
    from data.spicejet_documents import DOCUMENTS as c
    from data.dgca_documents import DOCUMENTS as d
    with contextlib.redirect_stdout(io.StringIO()):
        chunks=ingest_all(a+b+c+d)
    client=QdrantClient(url=os.environ['QDRANT_URL'],api_key=os.environ['QDRANT_API_KEY'],timeout=15)
    try:
        print(json.dumps(migrate_public_corpus(client,os.environ.get('QDRANT_COLLECTION','airline_kb'),chunks,apply=args.apply)))
    finally:
        client.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Publication failed ({type(exc).__name__}); no reset was attempted.',file=sys.stderr)
        sys.exit(1)
