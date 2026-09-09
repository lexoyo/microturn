# microturn

**A reimplementation of [DuplexCascade](https://arxiv.org/abs/2603.09180) that runs on consumer hardware, using prompting instead of fine-tuning.**

Researchers at SB Intuitions showed that a language model can hold a *full-duplex* conversation — listening continuously and deciding **on its own** when to reply, with no silence detector, no wake word and no button — provided you fine-tune it with LoRA.

microturn takes their mechanism and **trains nothing**: the same decision comes from a prompt.

The other difference is the machine. **Their implementation needs about 20 GiB of GPU memory** — three Kyutai models plus a Qwen2-7B. This one runs on **any computer**, down to a **Raspberry Pi**: speech recognition and speech synthesis are small and local, and the only heavy part is the decision itself — which is a call to whatever model you are testing, local or remote.

So the question this repository asks is: *how far does that get you, and with which models?* The sorting is part of the answer — some models fail outright, and that is measured below.

This is an **experiment**, not a product. Contributions are welcome. More benchmarks on more models would be great.

[[Original paper]](https://arxiv.org/abs/2603.09180) [[Their code]](https://github.com/sbintuitions/DuplexCascade) [[Their demo]](https://sbintuitions.github.io/DuplexCascadeDemo/) [[Our demos]](demos/) [[Reading notes]](PAPIER.md)

⚠️ **Their code does not run on consumer hardware, so their results are not reproduced here — they are quoted from their paper.** Two independent reasons, checked on 2026-09-09: their weights sit behind a gated HuggingFace repository that **excludes EU residents**, and their three services need ~20 GiB of VRAM in bf16, the TTS alone claiming 3.79.

## How it works

```
mic ──▶ sherpa-onnx ──▶ decider ──▶ piper ──▶ speaker
              │             │
         transcript    SPEAKING · DONE · THINKING · INTERRUPTING
```

A voice activity detector fires on a silence threshold, and that cannot work: a thinking pause and the end of a sentence last the same time. The paper removes the detector and hands that judgement to the language model, which has the **content** and not just the signal. Every 1.2 seconds the model says where the person is — *still speaking, done, thinking, cutting in* — and only in the second case, what to reply.

Two of their choices are borrowed, and they matter.

**Silence is data.** When nothing was said since the previous tick, `<|no voice|>` goes to the model. It *sees* that nothing happened and can count consecutive silences. That is what replaces the threshold.

**The tokens describe the person's state, not the action to take.** We ask for a perception (*where is she?*), not a policy decision (*should I speak?*). That is a far better posed task for a general-purpose model.

## Which models can do it

The four clips in [`demos/`](demos/) are the three scenarios from the researchers' demo page plus a fourth one of ours, made of thinking pauses **inside** sentences — the difficulty their demos never show. Recorded by a native English speaker: varying pace, breaths, soft onsets, a muttered "Okay". That is exactly what breaks the system.

| decider | turn ends | pauses held | status |
|---|---|---|---|
| `google/gemini-2.5-flash-lite` | 14/16 · 11/16 | 4/4 · 4/4 | measured |
| `qwen/qwen-2.5-7b-instruct` — their base model | 12/16 · 11/16 | 4/4 · 4/4 | measured |
| `meta-llama/llama-3.2-3b-instruct` | 11/16 · 8/16 | 4/4 · 2/4 | measured |
| `openai/gpt-4o-mini` | — | — | rejects the strict schema, HTTP 400 |
| `meta-llama/llama-3.2-1b-instruct` | — | — | provider refuses schema mode, HTTP 403 |
| `qwen/qwen3-8b` | — | — | 4.3 s per call, over the 1.5 s budget |

**Two passes per model, and they do not agree.** gemini scores 14/16 then 11/16 on the same audio with the same code. The three measured models overlap, so this bench does **not** rank them — and in particular it does not show the researchers' base model doing worse than gemini. All of the spread comes from one scenario, the travel one, where the system is speaking while the user cuts in and any timing shift changes everything downstream. The hesitation scenario is stable across every pass.

**Only models that accept a strict JSON schema can be measured here.** The decision is constrained at decoding time — an enum over the state tokens — which is what replaces the format guarantee their fine-tuning provides. A model that refuses that schema loses 100 % of its decisions, not some of them. It is not a heavy constraint in practice, and those models likely offer another route to constrained output; that is left for later.

**Two quantities, never one.** A system that always stays quiet holds 100 % of the pauses; a system that always talks catches 100 % of the turn ends. Neither number means anything alone, so neither is published alone here.

## Against their own benchmark

On two replayed sessions, deterministic, averaged over five passes:

| | accuracy | turn ends | missed pauses | perceived latency |
|---|---|---|---|---|
| baseline, 2026-08-29 | 0.634 | 11/17 | 11/29 | 5–7 s |
| **selected**, `gemini`, Δt 1.2 s | **0.816 ± 0.015** | 13.8/17 | 5.2/29 | 3.55 / 3.75 s |
| DuplexCascade, their bench, Δt 0.6 s | 0.858 | — | — | 1.724 s |

Four points behind a Qwen2-7B fine-tuned for five hours on eight H100s, from a prompt. **But read those four points together with the clock step**: their 0.858 is measured at Δt = 0.6 s, and their own ablation shows accuracy climbing up to 1.2 s. At *our* clock step their figure peaks around 0.93. **At comparable settings the gap is about a dozen points, not four.**

⚠️ **Those three rows are no longer reproducible.** The sessions they were measured on lived in a gitignored directory and were lost with an old clone. They stand as recorded measurements, not as something you can re-run today. The demo benchmark above, on the other hand, regenerates from the original recordings.

Method, details and caveats: [`RESULTATS.md`](RESULTATS.md), [`RESULTATS-PI.md`](RESULTATS-PI.md), [`PLAN-REPRO.md`](PLAN-REPRO.md).

## Install

```bash
./install.sh
```

Idempotent: whatever is already there is not downloaded again. It sets up the venv, the speech recognition model, the voice, and **the local decider** — Qwen2.5-7B-Instruct in Q4_K_M, 4.4 GiB.

Two things it does not do:

- **the `piper` binary**, shipped as a per-platform archive: get it from [its releases](https://github.com/rhasspy/piper/releases) and drop it in `~/.local/bin/piper`. Without it, `--tts espeak` works.
- **the OpenRouter key**, which is optional: without one the decider runs locally.

`arecord`, `aplay` and `ffmpeg` must be present.

## Run

```bash
.venv/bin/python pipeline.py                    # conversation, from the mic
.venv/bin/python pipeline.py --trace sessions/  # same, keeping everything
.venv/bin/python pipeline.py clip.wav --muet    # replay a recording
```

Startup announces the three stages, and **where the decision comes from**:

```
  transcription  sherpa
  décideur       openrouter · qwen/qwen-2.5-7b-instruct (clé lue dans .env)
  voix           piper · fr_FR-siwis-medium.onnx
```

The default decider is the researchers' **base model**, Qwen2.5-7B without their LoRA: the only setting where the comparison is about their own contribution. A key in `.env` runs it on OpenRouter, otherwise it runs locally on the GGUF. ⚠️ **Locally, one decision costs about twenty seconds on a laptop with no GPU**, against a 1.2 s tick: fine for the bench, not for a conversation.

<details>
<summary><b>What is taken from the paper, and what is not</b></summary>

Taken:

- [x] **Tokens describe the user's state**, not the system's action. They have six, we have five: `<user is speaking>`, `<user finish speaking>`, `<user is thinking>`, `<user backchannel>`, `<system backchannel>`.
- [x] **Silence sent as data** on every tick. One marker for them (`<no voice>`), three here, one of which counts consecutive silences.
- [x] **The fixed clock step** replacing the silence threshold. 0.6 s for them, 1.2 s here — and 1.2 s happens to be the accuracy optimum of *their* own ablation.
- [x] **The cascade** transcription → decider → speech, with no voice detector.

Not taken:

- [ ] **The LoRA fine-tuning** (r=16, α=32, 50k UltraChat dialogues, 8×H100). That is exactly what a prompt and a decoding constraint replace here, and it is the whole point of this repository.
- [ ] **Their `<user is interrupting>` token.** Interruption is inferred by the host, the only party that knows it is currently speaking.
- [ ] **Their Kyutai models** for speech recognition and synthesis, replaced by sherpa-onnx and piper — that is what takes the requirement from ~20 GiB of VRAM down to a Raspberry Pi.
- [ ] **Their backchannel post-processing by Qwen2-72B.**
- [ ] **Their benchmark**, Full-Duplex-Bench, never run here: their weights are unreachable from the EU.

⚠️ One point is on shaky ground on our side: `<user is thinking>` was dropped from our prompt on 2026-08-29 on the grounds that "DuplexCascade only has three tokens", which was **false**. The measured gain was real, the justification was not. Details in [`FORMAT-CHERCHEURS.md`](FORMAT-CHERCHEURS.md).

</details>

<details>
<summary><b>Reproducing their benchmark</b></summary>

The accuracy figure above uses **their** definition — one minus the take-over rate where low is good, the rate where high is good, unpaired mean — computed on **their** corpus, Full-Duplex-Bench. That is the only number in this repository that can sit next to their 0.858.

Two things to fetch, neither of them versioned here:

- the evaluation code, [`DanielLin94144/Full-Duplex-Bench`](https://github.com/DanielLin94144/Full-Duplex-Bench), cloned to `~/_/fdbench`;
- the v1.0 corpus, [five zip archives on Google Drive](https://drive.google.com/drive/folders/1DtoxMVO9_Y_nDs2peZtx3pw-U2qYgpd3), unpacked into `~/_/fdbench-data` — 730 samples, 1.3 GiB, about 14 seconds each.

```bash
.venv/bin/python bench/mesurer.py --taches pause,pause_synth,turn,interrupt,backchannel \
    --echantillon 15 --modele qwen/qwen-2.5-7b-instruct
```

Their backchannel evaluator needs `torchaudio` and `silero-vad`; the others need only `tqdm`. Interruption goes through our own adapter, `bench/eval_interrupt.py`, because theirs requires an OpenAI client for a GPT-4o rating that is out of scope here. **A partial average is refused on purpose**: publishing four tasks out of five under the same name would not be the same quantity.

</details>

<details>
<summary><b>Options and environment variables</b></summary>

`--moteur sherpa|whisper|vosk|rejeu` (default `sherpa`) · `--langue fr|en` · `--modele NAME` (a `.gguf` path means a local decider) · `--tts piper|espeak` · `--mic` · `--porte` (echo gate, off by default) · `--rendu out.wav` (the format Full-Duplex-Bench expects) · `--modele simule` (dummy decider, deterministic, no network call).

| variable | role | default |
|---|---|---|
| `OPENROUTER_API_KEY` | present = remote decider, absent = local decider | — |
| `MICROTURN_MODEL` | remote model | `qwen/qwen-2.5-7b-instruct` |
| `MICROTURN_LOCAL` | force the choice: `1` local, `0` remote | follows the key |
| `MICROTURN_MODELE_LOCAL` | GGUF path | `models/Qwen2.5-7B-Instruct-Q4_K_M.gguf` |
| `MICROTURN_CTX` | llama.cpp context | `4096` |
| `MICROTURN_GPU_LAYERS` | layers offloaded to the GPU | `0` |
| `MICROTURN_TIMEOUT` | remote call timeout, seconds | `1.5` |
| `MICROTURN_SHERPA` | speech recognition model directory | follows `--langue` |
| `MICROTURN_WHISPER` | fallback model | `models/ggml-tiny-q5_1.bin` |
| `MICROTURN_TTS` | speech engine | `piper` |
| `MICROTURN_PIPER` | piper binary | `~/.local/bin/piper` |
| `MICROTURN_VOICE` | piper voice | `fr_FR-siwis-medium.onnx` |

The code reads about a dozen more that only serve the bench and the tests (`MICROTURN_LOCALES`, `MICROTURN_SANS_R`, `MICROTURN_TICKS_SILENCE`…). They are documented where they are used, under `bench/`.

</details>

<details>
<summary><b>The target: a Raspberry Pi 3B</b></summary>

905 MiB of RAM, four Cortex-A53, no GPU, thermal throttling after 25 seconds of load. Every megabyte counts.

| stage | choice | why |
|---|---|---|
| Transcription | **sherpa-onnx**, streaming zipformer, 2 threads | the only one holding real time: 244 ms per 300 ms chunk |
| Fallback | whisper.cpp `tiny` q5 | the only multilingual engine, but new text only every ~4.3 s |
| Decision | **remote model** | a 7B does not fit in 905 MiB; ~0.46 s median latency from the Pi |
| Speech | **piper** kept resident, one WAV per sentence | keeping piper alive saves ~8 s per reply |

**RTF was the wrong criterion**, and that is what forced the engine change on 2026-08-29. whisper re-transcribes the whole turn on every pass: its 0.62 RTF hides the fact that it only produces new text every 4.3 seconds. On the **delay before the last word appears**, sherpa is at 0.25 s and whisper loses by an order of magnitude.

Two counter-intuitive settings, both free: on the Pi, **fewer threads is faster** (244 ms on two threads, 550 on four); and whisper goes from 1.17 to 0.62 RTF just by dropping its beam search.

Since 2026-09-03 piper stays resident and writes **one WAV file per sentence**, like `wyoming-piper`, `rhasspy3` and `pipecat` — no serious project uses `piper --output-raw`, which yields bytes with no end marker.

</details>

<details>
<summary><b>Analysing a session, and watching it live</b></summary>

With `--trace`, a session writes the replayable input audio, a timestamped log of every transcription hypothesis, every prompt and every raw reply, plus the settings and **a fingerprint of the code**.

```bash
.venv/bin/python tests/reference.py sessions/<date>   # what was ACTUALLY said
.venv/bin/python pipeline.py --moteur rejeu sessions/<date> --modele X --muet
```

**Replay mode** reads the recorded transcriptions back: two models then get exactly the same inputs at the same instants, and any difference comes from what you varied. Without it you would be comparing two noises. Open questions are in [`IDEES.md`](IDEES.md).

`visu/` streams `session.jsonl` as it is written, with nothing to install:

```bash
python3 visu/serveur.py sessions      # then http://127.0.0.1:8731/
```

The page shows **only** the conversation: the user's turn appears on the first partial and rewrites itself in place, revisions included, then freezes when the model decides. Everything else — chosen token, prompt, raw reply, latency — is one click away. Press `R` to replay the session at its real speed.

⚠️ Two numbers in the panel are **analogues, not the paper's quantities**: the latencies there are read off trace timestamps, where the researchers measure on annotated audio.

</details>

## Not solved

- **Perceived latency is 3.5 s.** The researchers are at 1.7 s.
- **The local decider is twenty times too slow** to hold a conversation, and a 7B will never fit on the Raspberry Pi target.
- **The echo gate is off.** It threw away 81 % of the audio of a real session, to fight an echo that actually came from a mic resting against the speaker. `--porte 2.0` turns it back on.

Where the project is going, and what is already settled: [`SPEC-PIVOT.md`](SPEC-PIVOT.md).

**Nothing enters this repository without being measured on a recorded session.**

Code under AGPL. The mechanism comes from DuplexCascade (MIT), not their code.
