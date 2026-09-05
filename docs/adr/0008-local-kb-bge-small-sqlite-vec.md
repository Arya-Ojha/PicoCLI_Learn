# Local knowledge base with bge-small and sqlite-vec

Answers must ground in the organization's own manuals, SOPs, and correspondence with nothing external, while sharing 4-8GB VRAM with the LLM and VLM. We decided on a folder-mounted corpus with 512/100 chunking, CPU `bge-small-en-v1.5 (ONNX)` embeddings plus `sqlite-vec`, file-level ACL checks at query time, and hard citations — the agent must cite `doc/chunk/page` spans or answer "not in corpus".
