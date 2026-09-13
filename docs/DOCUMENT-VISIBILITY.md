# Public and tenant document access

Unauthenticated All Airlines retrieval searches only points explicitly marked
`visibility=public`. Missing visibility is private by default. This restriction
applies to vector confidence lookups, hybrid vector search and lexical results.
Authenticated airline scope may read its own documents and published DGCA
material; it cannot read private documents of another airline.

Bundled repository documents are public. Self-serve uploads are always private;
a title or document text cannot grant public visibility. Future publication needs
a separate administrator approval workflow. Do not expose the generic vector
store's trusted airline_filter argument directly as a browser-supplied filter.

Existing cloud points need migration before deploying the new public search:

```sh
uv run python scripts/publish_bundled_corpus.py --env-file /secure/isha.env
uv run python scripts/publish_bundled_corpus.py --env-file /secure/isha.env --apply
```

Back up first. Dry run is the default. Only legacy points with IDs, chunk IDs,
text, source document IDs and airline metadata matching bundled public documents
are marked public. Explicitly private or changed points remain private. There is
no blanket publication of existing tenant uploads. No embeddings are regenerated.
The script is repeatable and creates the required visibility payload index.

Visibility changes in the bundled lexical corpus require rebuilding the index.
This release changes its cache namespace to avoid reusing pre-visibility caches;
the separate cache-invalidation roadmap item covers subsequent content changes.
