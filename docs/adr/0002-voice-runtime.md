# ADR 0002: Voice runtime on Blackwell

- **Status:** Accepted
- **Date:** 2026-10-24
- **Context task:** 0.7b (issue #14)

## Context

Voice capture (Phase 5) uses faster-whisper `large-v3-turbo` on the RTX 5070 Ti (sm_120). CLAUDE.md flagged this as the riskiest dependency and assumed it needs cuBLAS for CUDA 12 **and** cuDNN 9 from PyPI wheels, on `LD_LIBRARY_PATH` before Python starts. The Phase 0 smoke test checked each assumption on Tyler's machine.

## Findings

| Question | Result |
| --- | --- |
| Does CTranslate2 run on sm_120? | Yes. CTranslate2 4.8.3 (CUDA 12.8 support since 4.6.3) transcribes correctly on CUDA |
| float16 | Works: 5 s of audio in 0.25 s warm, model load 0.9 s |
| int8_float16 | Also works (0.63 s), despite 4.6.2 noting INT8 disabled for sm_120; kept as the documented fallback |
| Is cuDNN needed? | **No.** `libctranslate2` loads only `libcublas.so.12` at runtime; since 4.6.3 Conv1d has a pure CUDA path and cuDNN is optional |
| Is the launcher needed? | Yes. Without `packaging/recon-launch`, loading fails with "libcublas.so.12 is not found" |
| First-run cost | About 13 s once, while the driver JIT-compiles kernels for sm_120 into `~/.nv/ComputeCache`; under 1 s afterwards |
| Version clash | faster-whisper 1.2.1 calls `av.open(metadata_errors=...)`, which PyAV 19 removed (SYSTRAN/faster-whisper#1589, fixed upstream, unreleased) |

## Decision

1. **Voice dependencies are an optional extra, `voice`:** `faster-whisper`, `ctranslate2>=4.6.3`, `nvidia-cublas-cu12`, and `av>=11,<19`. CI and the default `uv sync` skip about 1.5 GB of CUDA wheels; `packaging/recon-launch` always runs with `--extra voice`.
2. **No `nvidia-cudnn-cu12`.** It saves about 700 MB and one more library on the loader path. If a later CTranslate2 needs cuDNN again, the smoke test fails with a clear missing-library error.
3. **`packaging/recon-launch`** puts every `nvidia/*/lib` folder from the venv on `LD_LIBRARY_PATH`, raises `CUDA_CACHE_MAXSIZE` to 4 GB (the default 1 GB cache was already full, and evictions would bring back the 13 s first run), and execs `uv run --frozen --extra voice python -m recon`.
4. **PyAV is capped below 19** until a faster-whisper release includes the fix; then the cap is removed.

## Consequences

- Phase 5's "release-to-text under 3 seconds" budget is realistic once the JIT cache is warm. Task 5.1 should warm it (or tell Tyler the first clip is slow) after driver updates, which invalidate the cache.
- The fallbacks named in the build plan (whisper.cpp with CUDA, openai-whisper on PyTorch cu128) aren't needed. Tyler doesn't need to choose between them.
- `uv sync` without `--extra voice` removes the voice packages. Use `uv sync --extra voice`, or launch through `recon-launch`, which restores them.
