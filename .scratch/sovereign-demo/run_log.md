# Offline run log (Wi-Fi off)

- Date: 2026-09-05, venue laptop Wi-Fi off, loopback vLLM only.
- Corpus: `.scratch/sovereign-demo/kb/` (5 SOPs) indexed, all citations `[doc chunk page]`.
- Document: `inspection-report.txt` split into pages (`report-pN-dpi200.png` refs), `inspection-report.pdf` queued for local VLM (NuExtract-3 4B, DPI 200; alias openrouter-vision-alias for routing tests).
- Router: `code -> qwen2.5-3B-instruct-Q4`, `ocr/vision -> nuextract-3-4B-Q4` (swap logged as `router.decision`).
- Deliverable: `approval-note.docx` emitted with findings + citations footer via template.
- Code verify proxy: `python -m py_compile calc_task.py` exit 0 (sandbox deferred, cwd-jail enforced).
- Trace (from `trace.jsonl`): `router ocr -> nuextract-3-4B-Q4`, `kb SOP-1.md c0 p1`, `ocr p1 report-p1-dpi200.png`, `result read: ok`. No external calls observed.
