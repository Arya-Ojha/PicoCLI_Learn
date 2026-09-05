# Minimal capability router with models.yaml

Tasks need different models (code vs summary vs vision) and new open-weight models must be addable without redesign, on 4GB dev and 8GB venue GPUs. We decided on a deterministic registry (`id, provider, ctx, vram_gb, caps[]`) with a `capability -> model-id` map plus fallback and a logged `router.decision` reason, deferring scorers and LLM-judges without a schema break.
