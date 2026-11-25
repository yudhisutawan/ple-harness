# Ringkasan aturan — Google Agent Harness on PLE (Kaggle)

Sumber diverifikasi 25 Nov 2026 dini hari WITA dari:
- https://www.kaggle.com/competitions/physical-engineerings-last-exam
  (overview, submission-requirements, rules, timeline)
- https://ple-bench.com/competition/guide
- Repo template https://github.com/physical-engineerings-last-exam/submission-template
  (commit 22c26a93a9e4974b16e4351faab0e860ff9fb24f)
- Repo kit https://github.com/google-research/ple (docs/rules.md,
  docs/local-models.md, docs/protocol.md, eval/dev_set.yaml)
- Dataset HF: google/physical-engineerings-last-exam,
  revision b3857a3fea39a695e18f845d4a88f29442e96e75

## Kompetisi

- Hadiah $400.000: 1st $250.000, 2nd $100.000, 3rd $50.000. Sponsor Google LLC.
- Deadline final: **5 Jan 2027 23:59 UTC = 6 Jan 2027 07:59 WITA**.
  Mulai 9 Nov 2026. Tidak ada entry deadline terpisah.
- Partisipasi saat dicek 24 Nov 2026: 4.168 entrants, **89 tim, 89 submission**
  (bukan ~25 seperti info awal — sudah 89 tim).
- Tim maks. 5 orang, 1 submission per tim, usia ≥18, Indonesia eligible
  (yang dilarang hanya wilayah sanksi: Crimea, DNR/LNR, Cuba, Iran, Korut).
- Tidak ada poin/medal Kaggle. Lisensi pemenang: Apache-2.0/MIT (kode),
  CC BY 4.0 (Writeup/dokumentasi).

## Stage 1 — Writeup + gate (100 poin)

Top 100 lolos ke Stage 2. Empat syarat lolos gate:
1. **Kaggle Writeup ≤2.000 kata**, mencakup 5 kriteria rubrik + **3 gambar
   wajib**: (1) diagram arsitektur, (2) plot skor-vs-biaya, (3) breakdown
   kegagalan dev-set. Draft yang tidak di-submit tidak dinilai.
2. **Repo GitHub + SHA commit 40 karakter** di Project Links. Root repo
   wajib berisi: `submission.yaml`, `serve.py`/`harness.py`, lisensi
   Apache-2.0/MIT, direktori `artifacts/` (unpacked). Repo boleh privat
   selama kompetisi bila dipasang GitHub App `ple-submission`; wajib publik
   saat kompetisi tutup.
3. **`model_api` di `submission.yaml` = salah satu model `google-cloud/<id>`**
   resmi (11 model — lihat bawah). Dev lokal boleh model apa saja; TIDAK
   perlu akun billing Google Cloud/Vertex. Saat Stage 2, proxy evaluasi
   memblokir `.env`, key sendiri, server model eksternal, dan web search;
   Google menyediakan evaluation key gratis.
4. **Lolos `uv run python -m kit check` dan `uv run python -m kit artifacts`**
   (PLE Competition Kit). `artifacts/` maks. 512 MiB, 10.000 file, tanpa Git
   LFS/symlink, dibuat oleh `uv run python eval/run.py`. Mengganti
   `model_api` ke target `google-cloud/<id>` SETELAH artifacts dibuat
   dengan model lokal **tidak mendiskualifikasi**. Judge LLM berbayar TIDAK
   wajib untuk dev lokal (dokumentasikan model+judge lokal di Writeup;
   penyelenggara akan re-score artifacts dengan judge resmi).

### Rubrik Writeup (100 poin)

| # | Kriteria | Poin | Yang dicari juri |
|---|---|---|---|
| 1 | Insight & Failure Analysis | 25 | Temuan non-obvious tentang engineering agent; kegagalan dev-set nyata (salah baca callout gambar, salah pilih klausa kode, error satuan, berhenti terlalu dini); ablasi terkontrol ("tambah X, skor A→B"); ide yang gagal |
| 2 | Engineering Reasoning | 25 | Telusuri 1 tugas dev-set konkret, bandingkan trajektori agen vs workflow licensed engineer; di mana penalaran bertahan, di mana shortcut; skill domain apa yang membedakan lolos/gagal (baca gambar CAD/PDF, cek tabel kode, jalankan solver) |
| 3 | Cross-Model Generalizability | 15 | Uji 29 dev task dengan ≥2 model (termasuk open-weight lokal / API pribadi), idealnya lintas famili; laporkan perubahan apa yang membantu semua model vs satu model saja; tabel perbandingan di Writeup; commit 1 target `model_api` di submission.yaml |
| 4 | Efficiency & Scaling | 20 | Plot skor dev-set vs anggaran komputasi (calls, token, runtime, atau verifikasi paralel); tandai titik plateau; estimasi headroom tersisa |
| 5 | Clarity & Visuals | 15 | Ditulis untuk peneliti ML tanpa latar sipil/mekanikal/elektrikal; temuan utama di atas; 3 gambar wajib; <2.000 kata |

Stage 1 murni gate kualifikasi — skornya hanya dipakai sebagai tie-break
di final (setelah skor Stage 2).

## Stage 2 — 56 tugas tersembunyi

- Komposisi: 6 Structural, 9 Civil, 18 Electrical, 23 Mechanical.
- Evaluator clone commit → `install` sekali di container debian:bookworm
  (timeout 30 menit, `/opt/harness` maks. 2 GiB terkompresi) → smoke test
  (`serve` bind `0.0.0.0:$PORT` dalam 120 detik, tulis file tes, kirim `done`).
- Lalu nilai `artifacts/` di 29 dev task + re-run sampel dev live. Gagal
  reproducibility / hard-code output = diskualifikasi.
- Per tugas tersembunyi: container terisolasi (2 CPU, 4 GB RAM, `/opt/harness`
  read-only, `/tmp`+`$HOME` writable 1 GB, **limit 6 jam/tugas**) via
  WebSocket. Skrip verifikasi cek perhitungan kuantitatif, geometri CAD/IFC,
  dan constraint; LLM judge (**Claude Opus 5.5**) nilai deliverable
  open-ended 0.0–1.0. Tugas tanpa frame `done`/`error` (ungraded/timeout)
  = 0.0.
- Tiap finalis jalan **3× independen** di semua 56 tugas (168 task-run).
  Hasil = mean skor (0.0–1.0) + biaya rata-rata → Pareto frontier
  performa-biaya.
- **Syarat hadiah: mean Stage 2 ≥ 0.138** DAN berada di Pareto frontier.
  Ranking 1–3 oleh mean skor Stage 2; tie-break: skor Writeup Stage 1,
  lalu timestamp submit Kaggle lebih awal.
- HTTP 400 / crash agen yang tak pulih / timeout mengurangi skor. Gangguan
  evaluator & rate-limit endpoint sponsor di-retry otomatis tanpa penalti.

## Model resmi Stage 2 (11 `google-cloud/<id>`)

| model_api | Model |
|---|---|
| google-cloud/gemini-4-carbon *(baru)* | Gemini 4 Carbon |
| google-cloud/gemini-4-neon *(baru)* | Gemini 4 Neon |
| google-cloud/gemini-4-hydrogen *(baru)* | Gemini 4 Hydrogen |
| google-cloud/gemini-4-argon | Gemini 4 Argon |
| google-cloud/gemini-3.8-flash | Gemini 3.8 Flash |
| google-cloud/gemini-3.1-pro-preview | Gemini 3.1 Pro (Preview) |
| google-cloud/gemma-4-26b | Gemma 4 26B A4B (open-weight) |
| google-cloud/claude-opus-5-5 | Claude Opus 5.5 |
| google-cloud/gpt-oss-120b | gpt-oss 120B (open-weight) |
| google-cloud/glm-5.2 | GLM 5.2 (open-weight) |
| google-cloud/llama-4-maverick | Llama 4 Maverick 17B 128E (open-weight) |

Di-inject via proxy evaluator: `MODEL_BASE_URL`/`OPENAI_BASE_URL`,
`ANTHROPIC_BASE_URL`, `GOOGLE_GEMINI_BASE_URL`. Daftar bisa bertambah.

## Dev set (29 tugas publik)

Dataset HF `google/physical-engineerings-last-exam`, revisi
`b3857a3fea39a695e18f845d4a88f29442e96e75`. Tiap tugas: limit 360 menit.
Domain: Mechanical, Civil, Electrical, Structural. Grading: `checks`
(verifikasi otomatis), `rubric` (LLM judge), `checks-judge` (gabungan).
Contoh: data-hall-mep-routing (Mechanical, checks, deliverable
solution.py), data-center-site-model (Civil, checks, model.ifc),
lv-cable-sizing (Electrical, checks-judge, submission.zip),
wind/seismic-diaphragm-shear & roof-deck-design (Structural, checks,
submission.zip). Skor tugas 0–1; tugas design (paper_score) memakai
`s = 0.4p + 0.6·G·O'` (p = fraksi constraint terpenuhi, G = 1 bila semua
hard constraint terpenuhi else 0, O' = objektif vs baseline naive).
Skor run = mean semua tugas; tugas tanpa hasil = 0.

## Format submission.yaml (dari guide resmi)

```yaml
name: my-harness
model_api: google-cloud/claude-opus-5-5
install: >-
  uv venv --python 3.12 /opt/harness/venv
  && uv pip install --python /opt/harness/venv/bin/python -r {src}/requirements.txt
serve: /opt/harness/venv/bin/python {src}/serve.py
env:   # opsional, string dikutip
  LOG_LEVEL: "info"
```

`{src}` = `/opt/harness/src`, `{port}` = `$PORT`. Hanya `/opt/harness`
yang disimpan setelah build; download paket saat runtime diblokir.
Server wajib bind `0.0.0.0:$PORT` ≤120 detik; frame JSON UTF-8 ≤16 MiB,
maks. 8 request bersamaan; file read/write base64. Env saat run:
`PORT`, `MODEL_API`, `MODEL_NAME`, `MODEL_BASE_URL`, `MODEL_API_KEY`
(+ mirror `OPENAI_*`), `ANTHROPIC_BASE_URL`/`ANTHROPIC_API_KEY` (Claude),
`GOOGLE_GEMINI_BASE_URL`/`GEMINI_API_KEY` (Gemini), + `env:` sendiri.

## Cara submit (4 langkah resmi)

1. Clone `google-research/ple`, mulai dari
   `physical-engineerings-last-exam/submission-template` (atau sample
   `pi-opus`, `hermes-opus`, `agy-gemini`).
2. `uv run python -m kit check ../my-harness` → `uv run python eval/run.py
   ../my-harness` (tulis artifacts/) → `uv run python -m kit artifacts
   ../my-harness`.
3. Commit kode + submission.yaml + artifacts/ dalam SATU commit, push
   GitHub.
4. Di Kaggle: tab Writeups → New Writeup → lampirkan link repo GitHub di
   Project Links → SHA 40 karakter di atas → Submit.

Registrasi langsung di ple-bench.com SUDAH DITUTUP — semua entry resmi
hanya via Kaggle Writeups.

## Fair play (pelanggaran = diskualifikasi)

- Jangan hard-code jawaban / deteksi tugas spesifik (termasuk dev task).
- Harness TIDAK BOLEH membaca grader, file referensi, atau `artifacts/`
  sendiri (disk, git history, network) saat build/run.
- `artifacts/` harus dari `eval/run.py` dengan harness yang di-submit dan
  `model_api` yang dideklarasi (re-run per tugas individual boleh; edit
  manual / harness lain / model lain tidak boleh).
- Jangan bypass egress proxy, jangan hubungi host selain endpoint model
  (web search termasuk search tool provider, dan API eksternal dilarang),
  jangan mengintip skrip grading / merusak container evaluasi.
- Jangan log/store/publish/share prompt atau file tugas test.
- `model_api` di submission.yaml harus sama dengan model yang dipanggil.

## Aturan model lokal (dev saja)

`model_api: openai-compatible/<model>` HANYA untuk run lokal; `kit check`
tidak pernah menyatakan entry seperti itu siap submit. Server model di
`127.0.0.1` + auth gate (contoh: `sample_submissions/local-model/host/`
dengan Caddy). `--model-base-url http://<host>:<port>/v1` di-override saat
`kit check`/`eval/run.py`; di dalam container `localhost` menjadi
`host.docker.internal`. Key di env/`--env-file` sebagai `MODEL_API_KEY`,
JANGAN di entry. Endpoint harus kembalikan tool call (streaming maupun
tidak). Judge lokal default = server model sendiri kecuali
`JUDGE_BASE_URL`/`MODEL_PROXY_URL` di-set.
