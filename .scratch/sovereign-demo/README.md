# Sovereign demo (offline)

1. Wi-Fi off.
2. `pico run "read inspection-report.txt, search kb, emit approval note"` in this folder (cwd-jail).
3. Verify `approval-note.docx` contains findings + `[SOP-*]` citations.
4. `python -m py_compile calc_task.py` as code-verify proxy (sandbox deferred).
5. Tracing tab shows `router.decision`, `kb.hit`, `ocr.page`.
