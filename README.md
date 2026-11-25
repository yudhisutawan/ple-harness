# Cryptoboy PLE harness

Agent harness for **Google — Agent Harness on Physical-Engineering's Last
Exam** (Kaggle, $400.000). Entry: `cryptoboy-ple`. License: Apache-2.0.

> Status 25 Nov 2026: **kerangka v0.1 + smoke test lokal lolos.** Baseline
> dev-set BELUM bisa jalan — 2 blocker: (1) kit resmi tidak boleh dieksekusi
> sampai Yudhi menyetujui (execution-risk flag); (2) dataset HF dev-set
> gated, butuh akun HF + akses + `HF_TOKEN`. Yang sudah terbukti: `uv`
> terpasang, kit ter-clone, `pytest` 7 passed, model gratis 100milionseek
> `deepseek-v4.1-flash-free` jalan dengan tools + `reasoning_effort=max`,
> runner lokal `eval/run_local.py` menjalankan harness end-to-end pada tugas
> sintetik (memo benar, total USD 7402.00, 485 dtk, 81.680 in / 11.547 out
> token) dan menemukan 1 bug final_message yang sudah diperbaiki. Docker di
> VM ini degraded (tanpa bridge/NAT, pull image gagal) — run resmi
> kemungkinan butuh mesin lain. Detail: `docs/BASELINE-WEEK1.md`. Target
> model di `submission.yaml` masih placeholder.

## Arsitektur: planner → worker → calc-verifier → verifier

Satu loop tool-calling saja gagal di tugas engineering karena satu angka
salah = seluruh deliverable salah. Karena itu harness ini memisahkan peran:

```
task ──▶ PLANNER (read-only) ──▶ plan (deliverables, metode, constraints)
            │
            ▼
         WORKER (bash/read/write) ──▶ deliverables + calc/*.py + calc/UNITS.md
            │                              (semua angka dari kode, bukan
            │                               hitungan kepala)
            ▼
      CALC-VERIFIER (read-only+bash) ──▶ re-run script dari nol, cek unit &
            │                              constraint keras (safety/feasibility)
            ▼
      DELIVERABLE-VERIFIER (read-only) ──▶ PASS / daftar issue ──▶ fix (≤2 ronde)
            │
            ▼
         done + final_message
```

| Tahap | Tools | Anggaran waktu (dari total 6 jam/tugas) |
|---|---|---|
| Planner | bash, read_file | 10% pertama |
| Worker | + write_file | sampai tersisa 25% |
| Calc-verifier | bash, read_file | sampai tersisa 18% |
| Verifier | bash, read_file | sampai tersisa 12,5% |
| Fix rounds (≤2) | + write_file | sampai tersisa 4 menit |

Aturan keras worker: **hitung dengan kode, bukan dengan kepala**; setiap
angka tercatat di `calc/UNITS.md` (nilai, satuan, rumus/sumber, script).
Calc-verifier menjalankan ulang script dan memeriksa konsistensi dimensi —
ini pembeda utama dari sample `plan-verify` (yang tidak punya tahap
verifikasi perhitungan independen).

Ketahanan (diambil dari sample `minimal`): retry backoff 5–120 dtk,
pemotongan hasil tool saat konteks penuh, wrap-up paksa sebelum deadline,
dan `final_message` yang selalu terisi meski timeout — karena deliverable
yang sudah tertulis tetap dinilai walau harness gagal di akhir.

## File

| File | Isi |
|---|---|
| `submission.yaml` | nama entry, `model_api`, perintah install & serve |
| `serve.py` | entrypoint: `taskbridge.run(harness.solve)` |
| `harness.py` | loop agen + 4 tahap + prompt peran |
| `taskbridge.py` | protokol serve (salinan resmi kit kompetisi, Apache-2.0) |
| `requirements.txt` | `openai`, `websockets` (pin sama seperti sample `minimal`) |
| `artifacts/` | output dev-set dari `eval/run.py` — **jangan edit manual** |
| `WRITEUP-DRAFT.md` | draf kerangka Writeup (rubrik 100 poin) |
| `BRIEF-PENDAFTARAN.md` | langkah daftar Kaggle + join kompetisi (tugas browser) |
| `docs/RULES-NOTES.md` | ringkasan aturan kompetisi yang diverifikasi |

## Dev lokal (gratis, tanpa Google Cloud)

Model evaluasi resmi (`google-cloud/<id>`) HANYA dipakai saat Stage 2 —
Google menyediakan key-nya, tanpa billing account. Dev lokal boleh pakai
model sendiri:

- **Claude Sonnet 5 via NaraRouter** (endpoint OpenAI-compatible) — utama.
- **Hermes via 9Router** (`yudhi-combo`) — kandidat kedua / cross-model.
- **Open-weight lokal** (vLLM/Ollama, mis. gpt-oss-120b) — bila tersedia.

Caranya: set `OPENAI_BASE_URL`, `OPENAI_API_KEY`, `MODEL_NAME` di
`local.env` (JANGAN commit), lalu jalankan kit dari repo kompetisi:

```bash
git clone https://github.com/google-research/ple.git   # kit + dev set
cd ple
uv run python -m kit validate ../kaggle-ple-harness   # tanpa Docker
uv run python -m kit check ../kaggle-ple-harness --env-file local.env
uv run python eval/run.py ../kaggle-ple-harness --env-file local.env
uv run python -m kit artifacts ../kaggle-ple-harness
```

`kit check` butuh Docker; `validate` tidak. Sebelum submit final, ganti
`model_api` di `submission.yaml` ke target `google-cloud/<id>` (keputusan
minggu ke-4/5 setelah uji cross-model) — mengganti ini setelah artifacts
dibuat dengan model lokal **tidak** mendiskualifikasi.

## Rencana 6 minggu (25 Nov 2026 → 5 Jan 2027)

| Minggu | Tanggal | Target |
|---|---|---|
| 1 | 25 Nov–1 Des | Setup: akun Kaggle + repo GitHub, `kit validate` lolos, baseline `minimal` di 3–5 dev task, taksonomi kegagalan pertama |
| 2 | 2–8 Des | Planner+verifier hidup; run dev-set penuh pertama (29 tugas) dengan Claude lokal; catat skor & biaya per tugas |
| 3 | 9–15 Des | Calc-verifier + units ledger; ablasi (dengan/tanpa calc-verify, dengan/tanpa planner); perbaiki 3 mode gagal terbesar |
| 4 | 16–22 Des | Uji cross-model (≥2 model, beda famili) + plot skor-vs-biaya; putuskan `model_api` target |
| 5 | 23–29 Des | Hardening: timeout, retry, konteks; 3× run dev-set penuh; draf Writeup + 3 gambar (arsitektur, skor-vs-biaya, breakdown kegagalan) |
| 6 | 30 Des–5 Jan | Final: `kit check` + `kit artifacts` lolos, commit `artifacts/`, push GitHub, submit Writeup Kaggle **paling lambat 3 Jan** (buffer 2 hari) |

Deadline final: **5 Jan 2027 23:59 UTC = 6 Jan 2027 07:59 WITA**.
Satu submission per tim; tim maks. 5 orang (kami solo).

## Aturan fair-play (ringkas — lengkap di `docs/RULES-NOTES.md`)

- Jangan hard-code jawaban / deteksi tugas spesifik; jangan baca grader
  atau `artifacts/` sendiri saat run.
- `artifacts/` hanya dari `eval/run.py` dengan harness yang di-submit.
- Stage 2: tanpa web search, tanpa API eksternal, tanpa `.env`/key sendiri.
- `model_api` di `submission.yaml` harus sama dengan model yang dipanggil.
