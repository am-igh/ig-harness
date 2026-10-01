# Local models

Everything runs through the model gateway to your own Ollama (see `harness/gateway/`). Pick the model for each job from the **model picker** (click the model name in the header). Until you pick one, the harness uses `IG_LOCAL_MODEL` from your `.env`. The other models are also what the Inbox tab's scoreboard compares.

**What the picker can and cannot do:** the gateway decides what data may go where, whatever you pick. Email triage handles confidential (S2) mail, so only local models can be chosen for it. Online models (Infomaniak, Claude API, OpenRouter) are listed but locked until Phase 6; they will only ever be offered for jobs whose data is public or internal.

| Model | Size | Notes |
|---|---|---|
| `qwen3.8:27b-mlx` | 18 GB | In use. Strongest so far; about 3 to 13 s per email once loaded. |
| `qwen3.5:9b` | 6.6 GB | Smaller Qwen, Ollama official library. |
| `qwen3:8b` | 5.2 GB | Previous default. |
| `apertus1.5-8b-text:f16` | 16 GB | Apertus 1.5 (Swiss AI Initiative), text-only build made locally. See below. |
| `gemma3:latest` | 3.3 GB | Small, fast. |

## Apertus 1.5: where the local build comes from

Apertus 1.5 is not in Ollama's library (checked 1 Oct 2026). `apertus1.5-8b-text:f16` was made on this Mac from Swiss AI's **official** weights (`swiss-ai/Apertus-v1.5-8B`, Apache-2.0, downloaded after accepting their terms). It is an **unofficial text-only conversion**, so treat results as ours, not Swiss AI's:

1. The official release is multimodal (`Apertus1p5ForConditionalGeneration`). Only the text decoder was kept: tensors renamed from `model.language_model.*` to `model.*` (headers only, weights untouched); image and audio parts dropped.
2. The input table and tokenizer were trimmed from 266,752 to the 131,072 text tokens (everything above is reserved for image/audio; the output layer is 131,072 wide). The `<|assistant_end|>` token was declared as end-of-sequence.
3. Converted with the official `llama.cpp` converter to a 16-bit GGUF and imported into Ollama with a hand-written chat template (`<|system_start|>` … `<|assistant_start|>`), thinking mode off.

Not done: quantisation (Ollama only quantises its own formats at import; a smaller `q4_K_M` needs `llama-quantize`), and any image, audio or long-context use. Sanity checks passed (English, French with "vous", German, JSON triage output), but it has not been evaluated beyond that: use the scoreboard.

## Moving the Apertus build to another Mac

A ready-to-copy folder was prepared at `~/Desktop/Apertus-1.5-for-transfer` (the model file, `Modelfile`, a checksum and install instructions in `README-install.txt`). Copy it to the other Mac (USB or external drive; it is 16 GB), then run `shasum -a 256 -c SHA256.txt` and `ollama create apertus1.5-8b-text:f16 -f Modelfile` there. Needs Ollama 0.12 or newer.
