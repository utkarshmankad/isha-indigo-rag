import re

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
MIN_CHUNK_SIZE = 100


def clean_text(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[^\S\n]+', ' ', text)
    return text.strip()


def split_into_chunks(text: str, chunk_size: int, overlap: int) -> list[str]:
    def _split_by(text: str, sep: str) -> list[str]:
        parts = text.split(sep)
        return [p + sep for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])

    def _merge_segments(segments: list[str]) -> list[str]:
        chunks = []
        current = ""
        for seg in segments:
            if len(current) + len(seg) <= chunk_size:
                current += seg
            else:
                if current.strip():
                    chunks.append(current)
                # seg itself may exceed chunk_size — handled below
                current = seg
        if current.strip():
            chunks.append(current)
        return chunks

    def _refine(chunks: list[str]) -> list[str]:
        """Break any chunk still over chunk_size at word boundary."""
        result = []
        for chunk in chunks:
            if len(chunk) <= chunk_size:
                result.append(chunk)
                continue
            # try sentence boundary first, then word boundary
            for sep in ('. ', ' '):
                parts = chunk.split(sep)
                sub, buf = [], ""
                for p in parts:
                    token = p + sep
                    if len(buf) + len(token) <= chunk_size:
                        buf += token
                    else:
                        if buf.strip():
                            sub.append(buf)
                        buf = token
                if buf.strip():
                    sub.append(buf)
                if all(len(s) <= chunk_size for s in sub):
                    result.extend(sub)
                    break
            else:
                # hard word-boundary split as last resort
                words = chunk.split(' ')
                buf = ""
                for w in words:
                    if len(buf) + len(w) + 1 <= chunk_size:
                        buf = (buf + ' ' + w).lstrip()
                    else:
                        if buf.strip():
                            result.append(buf)
                        buf = w
                if buf.strip():
                    result.append(buf)
        return result

    # Priority split: double newline → single newline → '. ' → word
    segments: list[str] = []
    for para in text.split('\n\n'):
        para = para.strip()
        if not para:
            continue
        if len(para) <= chunk_size:
            segments.append(para + '\n\n')
        else:
            for line in para.split('\n'):
                line = line.strip()
                if not line:
                    continue
                if len(line) <= chunk_size:
                    segments.append(line + '\n')
                else:
                    for sent in re.split(r'(?<=\. )', line):
                        if sent:
                            segments.append(sent)

    raw_chunks = _merge_segments(segments)
    raw_chunks = _refine(raw_chunks)

    # Apply overlap
    chunks = [c.strip() for c in raw_chunks if c.strip()]
    if not chunks:
        return []

    overlapped: list[str] = [chunks[0]]
    for i in range(1, len(chunks)):
        prev = chunks[i - 1]
        tail = prev[-overlap:].lstrip() if len(prev) > overlap else prev
        overlapped.append(tail + chunks[i])

    return [c for c in overlapped if len(c) >= MIN_CHUNK_SIZE]


def chunk_document(doc: dict) -> list[dict]:
    text = clean_text(doc['content'])
    raw = split_into_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)

    # total_chunks determined after filtering; rebuild with correct count
    chunks = []
    for i, chunk_text in enumerate(raw):
        chunks.append({
            'chunk_id': f"{doc['id']}_chunk_{i:03d}",
            'doc_id': doc['id'],
            'chunk_index': i,
            'total_chunks': len(raw),
            'text': chunk_text,
            'metadata': {
                'title': doc['title'],
                'category': doc['category'],
                'department': doc['department'],
                'doc_type': doc['doc_type'],
                'last_updated': doc['last_updated'],
                'source_doc_id': doc['id'],
            },
        })
    return chunks


def ingest_all(documents: list[dict]) -> list[dict]:
    all_chunks: list[dict] = []
    for doc in documents:
        doc_chunks = chunk_document(doc)
        print(f"  {doc['id']:10s}  {len(doc_chunks):3d} chunks")
        all_chunks.extend(doc_chunks)
    return all_chunks


def print_stats(chunks: list[dict]) -> None:
    if not chunks:
        print("No chunks.")
        return

    lengths = [len(c['text']) for c in chunks]
    total = len(chunks)
    print(f"\n{'='*50}")
    print(f"Total chunks : {total}")
    print(f"Min length   : {min(lengths)}")
    print(f"Max length   : {max(lengths)}")
    print(f"Avg length   : {sum(lengths)/total:.1f}")
    print(f"{'='*50}")

    from collections import defaultdict
    by_doc: dict[str, list[int]] = defaultdict(list)
    for c in chunks:
        by_doc[c['doc_id']].append(len(c['text']))

    print(f"\n{'Doc ID':<12} {'Chunks':>6} {'Min':>6} {'Max':>6} {'Avg':>7}")
    print('-' * 44)
    for doc_id, lens in sorted(by_doc.items()):
        print(
            f"{doc_id:<12} {len(lens):>6} {min(lens):>6} "
            f"{max(lens):>6} {sum(lens)/len(lens):>7.1f}"
        )
