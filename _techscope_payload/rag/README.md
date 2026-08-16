# TechScope RAG Source

`search-index.template.json` is intentionally dimension-parameterized because the
actual embedding deployment/dimensions are selected at provision time.

`index_documents.py` performs manual vectorization and push indexing.
This preserves the Frozen Baseline's classic RAG orchestration model.

The index keeps human-readable grounding metadata alongside the vector field.
