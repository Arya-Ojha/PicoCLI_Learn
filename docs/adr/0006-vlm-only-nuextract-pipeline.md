# VLM-only document pipeline with NuExtract-3 4B

Scanned PDFs, handwritten notes, drawings, and photos must be understood on-device with nothing external. We decided on a VLM-only pipeline (no Tesseract in v1): `pypdfium` renders pages to PNG at DPI 200, NuExtract-3 4B converts each page to Markdown plus structured JSON, and per-page text plus PNG is kept in the trace for citations, with a local VLM plus OpenRouter vision alias for routing tests on small GPUs.
