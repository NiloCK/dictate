# Model evaluations

Log of speech-to-text models looked at as alternatives to the status quo. One
section per candidate, newest first. Record what was *measured* here separately
from what the vendor claims.

## Status quo

- Backend: `faster-whisper` (CTranslate2), `compute_type="int8"`, `device="auto"`, `beam_size=5`.
- Models offered in the tray: `tiny`, `base`, `small`, `medium`, `large-v3-turbo`,
  `distil-small.en`, `distil-medium.en`. Day-to-day config (Oct 2026): `tiny`.
- Features we depend on: French + auto-detect, `translate` task (fr -> en).
- Constraints: dev box is 8-core CPU, no NVIDIA GPU, 15 GB RAM and routinely
  swapping (see `check_swap_latency.py`), so resident model size matters more
  than download size.

## Underdog Bark 3.0 (assessed 2026-10-21, desk review only, not run)

- Source: https://underdog.ai/bark, https://huggingface.co/ConwayResearch/Underdog-Bark-3.0
  (also `-Plus`, `-Clean`, `-Pro`).
- What it is: a quantized fine-tune of NVIDIA `parakeet-tdt-0.6b-v3` (via
  `moondream/parakeet-ultra`). 0.6B params, TDT (transducer), English only.
  CC-BY-4.0 (attribution required, fine for us).
- Vendor numbers (Open ASR Leaderboard, 7-set English avg WER, self-scored,
  not on the leaderboard yet):

  | Model | Download | AMI | Avg |
  |---|--:|--:|--:|
  | Bark 3.0 | 163 MB | 7.82 | 4.94 |
  | Bark 3.0 Plus | 180 MB | 7.76 | 4.76 |
  | Bark 3.0 Pro | 1,254 MB | 7.16 | 4.29 |
  | Parakeet TDT 0.6B v3 | 2,508 MB | 9.42 | 4.94 |
  | Whisper large-v3-turbo | 1,618 MB | 13.88 | 6.58 |

  "Beats Parakeet" is 4.937 vs 4.941: a tie on average. The real gain is on
  meetings (AMI). The gap to large-v3-turbo is real: about 1.6 points avg,
  6 on AMI. No numbers for `tiny`, but it is far worse than turbo.
- **The size claim is about download size only.** `model.bark` is an
  entropy-coded (ANS) quantized blob. `bark_loader.py` decodes it into a stock
  `transformers` `ParakeetForTDT` in **fp32 by default** (~2.4 GB resident;
  maybe ~1.2 GB if `dtype=bfloat16`, untested). In RAM it costs as much as stock
  Parakeet, not 163 MB. The low-bit runtimes (MLX, Core ML) are Apple-only.
- Linux runtime: `torch==2.8` + `transformers==5.19` + `constriction`. That is a
  new torch dependency next to CTranslate2. On first use it also fetches the
  processor/generation config from `nvidia/parakeet-tdt-0.6b-v3`, so it needs
  network or a warm HF cache.
- Gaps against what we use: no French, no auto-detect, no translate. It would
  be an extra English option in the tray, not a replacement.
  No word timings (we don't need them).
- `Bark 3.0 Clean` (removes fillers and false starts) is interesting for
  dictation, but it ships MLX files only. The README's PyTorch path is for the
  verbatim model.

**Verdict:** Not adopted for now. On accuracy it's the best English option
we've seen. On this machine, though, it means fp32 Parakeet under torch, and
the small file size doesn't help. If we want Parakeet-class accuracy, first look
at stock `parakeet-tdt-0.6b-v3` with an int8 ONNX export (onnx-asr /
sherpa-onnx). It needs no torch and should use less memory. Parakeet v3 is also
multilingual (25 European languages incl. French), which Bark gave up. Check
whether that path covers our French use before ruling it in.

**To decide properly (not yet done):** run Bark 3.0 (torch CPU, fp32 and bf16),
`tiny`, and `large-v3-turbo` on the same ~20 saved dictation clips. Record
resident RSS, latency per clip and hand-scored errors.
