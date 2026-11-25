# Baseline minggu 1 — PLE (25 Nov 2026)

Status: **setup selesai, baseline dev-set BELUM bisa jalan — 2 blocker keras**
(lihat bawah). Yang jalan malam ini: smoke test sintetik lokal.

## 1. Yang sudah diverifikasi malam ini

| Item | Hasil |
|---|---|
| `uv` | Terpasang 0.13.10 (`~/.local/bin/uv`) |
| Docker | CLI 29.1.3 terpasang; daemon jalan tapi **degraded**: `--iptables=false --bridge=none` (bounding set VM tidak punya `CAP_NET_ADMIN`, `iptables` ditolak meski uid=0). Hanya network `host`/`none` yang ada — bridge/NAT tidak bisa dibuat. Pull image gagal: TLS handshake timeout ke `registry-1.docker.io` (egress proxy). Satu aksi terkait Docker sempat minta persetujuan yang kedaluwarsa tanpa jawaban — JANGAN diulang tanpa Yudhi yang minta. Dampak: `kit check` / `eval/run.py` resmi hampir pasti tidak bisa jalan di VM ini; butuh mesin dengan Docker penuh (kandidat: VPS `hermes` — perlu dicek) atau kapabilitas jaringan. |
| Sumber daya VM | Disk 144 GB bebas (cukup untuk image Docker 10 + 17 GB). CPU `nproc` 4, RAM total ~8 GB (hanya 376 MB available saat dicek) — jauh di bawah slot kit (6 CPU / 16,25 GB per tugas); run resmi di VM ini pun akan sangat pelan/berisiko OOM. |
| Kit | Clone bersih `google-research/ple` → `~/workspace/ple-kit/` |
| Repo harness | `pytest tests/` — **7 passed** (sesudah fix, lihat §2) |
| Model iterasi | 100milionseek `deepseek-v4.1-flash-free` — **OK**: `/v1/models` berisi model itu; chat completion dengan tools + `reasoning_effort="max"` (persis seperti `harness.py`) berhasil, `finish_reason: tool_calls`, 682 in / 152 out token untuk 1 panggilan tes. Catatan: model mengembalikan tool call bernama `read` (bukan `bash`/`read_file`) pada tes — harness membalasnya sebagai error tool tak dikenal dan model bisa pulih; pantau di run nyata. |
| Local runner | `eval/run_local.py` (kode sendiri) — bicara protokol serve ke `serve.py` tanpa kit/Docker; `exec`/`read_file`/`write_file` dilayani dari workdir lokal; catat `usage`/`log`; self-check deliverable (ada, non-kosong, tanpa TODO/placeholder, `.py` lolos `py_compile`). |
| Dataset HF | Metadata dev-set terbaca dari `eval/dev_set.yaml` (29 tugas). **File tugas TIDAK bisa diunduh**: dataset `google/physical-engineerings-last-exam` gated — `resolve` mengembalikan "Access ... is restricted ... Please log in." |

## 2. Smoke test sintetik (pengganti dev task sampai blocker 2 beres)

Tugas: `eval/tasks-local/synthetic-smoke/` — hitung total order balok baja
dari `data/order.csv` dengan script Python, tulis memo di `output/memo.md`,
jaga `calc/UNITS.md`. Timeout lokal 600 detik (bukan 360 menit resmi —
dicatat sebagai deviasi baseline).

### Run 1 — `eval/runs/synthetic-smoke-1/` (SEBELUM fix, 25 Nov ~21:30 WITA)
- Status `DONE`, durasi **485,6 dtk**, model `deepseek-v4.1-flash-free`.
- Token: **81.680 in / 11.547 out** (20 panggilan model). Request: exec 14,
  read_file 5, write_file 3.
- Deliverable: `output/memo.md` **OK** (535 B), `calc/UNITS.md` **OK**
  (1.663 B). Isi **benar** (dicek manual): subtotal 2214.00 / 1814.00 /
  1446.00 / 1928.00, grand total **USD 7402.00** — cocok dengan hitungan
  tangan. Worker menulis `calc/total_cost.py` + `calc/make_docs.py`, lalu
  menulis sendiri `calc/verify.py` (verifikasi independen) dan me-re-run
  untuk konfirmasi. Calc-verifier me-re-run script dari nol di salinan
  sementara + menjumlah ulang secara independen.
- **BUG ketemu — final_message rusak:** verifier mengembalikan verdict
  yang terpotong/garbled (bukan `PASS`), `solve()` memperlakukannya sebagai
  daftar issue dan menjalankan fix round dengan issue sampah. Model fix
  round tidak diberi `workdir` maupun instruksi tugas, jadi tidak bisa
  menemukan file dan membalas kebingungan — itulah yang jadi
  `final_message` run ini (bukan ringkasan worker). Deliverable tetap benar,
  tapi untuk tugas `rubric` (final_message dibaca grader) ini bisa
  merugikan skor.
- **Fix (commit berikut):** (1) verdict kosong = `PASS` (aturan sama seperti
  sample resmi `plan-verify`); (2) fix round kini menerima `workdir` +
  instruksi tugas di pesannya.
- **Run 2 — `eval/runs/synthetic-smoke-2/`:** re-run setelah fix (1).
  Status `DONE`, durasi **488,0 dtk**, token **143.446 in / 18.289 out**
  (22 panggilan) — jauh lebih boros dari run 1 (81.680 in): varians antar
  run besar, model banyak menjelajah. Deliverable **benar lagi**
  (memo 1.707 B, UNITS 3.918 B; total USD 7,402.00, 45 pieces, dicek
  manual). **Tapi final_message MASIH rusak:** verifier lagi-lagi
  mengembalikan verdict non-PASS (tanpa daftar issue bernomor), fix round
  berjalan, dan di dalam fix round model mengeluarkan tool call dalam
  format native DeepSeek (`<｜DSML｜ calls>...`) sebagai TEKS biasa — bukan
  function call — sehingga `final_message` run ini adalah teks pembuka fix
  round + blok DSML. Dua pelajaran: (a) verifier model gratis ini tidak
  bisa diandalkan mengikuti kontrak "PASS atau daftar issue bernomor";
  (b) endpoint 100ms membocorkan format tool-call native DeepSeek ke teks
  saat `tool_choice="none"` (wrap-up) atau saat model gagal emit function
  call.
- **Fix tambahan (commit berikut):** (3) verdict tanpa daftar issue
  bernomor/berbutir → dianggap `PASS` (kontrak prompt verifier); (4) bila
  model membalas teks yang mengandung penanda `｜DSML｜` tanpa tool call,
  `agent_loop` menegurnya sekali ("pakai hanya function tools yang
  disediakan") dan melanjutkan, bukan menjadikannya jawaban akhir.
  Runner lokal juga diubah menyimpan SEMUA baris log (bukan 30 terakhir)
  agar verdict tiap tahap bisa diaudit.
- **Run 3 — `eval/runs/synthetic-smoke-3/`:** re-run setelah fix (3)+(4).
  Status `DONE`, durasi **393,4 dtk** (tercepat), token **95.793 in /
  13.768 out** (17 panggilan). Deliverable **benar lagi** (memo 1.559 B,
  UNITS 2.878 B; total USD 7,402.00). **FIX TERVERIFIKASI:** log mencatat
  "verifier verdict named no numbered issues; treating as PASS" — tidak ada
  fix round palsu, dan `final_message` kini ringkasan worker yang benar:
  tabel deliverable, hasil kunci, verifikasi yang dilakukan (dua
  recomputasi independen, memo di-parse programatik lawan CSV, sweep
  placeholder bersih, sha256 input tidak berubah), plus judgement calls
  (tidak ada design code yang dikutip karena tidak ada di data — tepat).
  Worker juga membersihkan `__pycache__` sendiri. **Kesimpulan smoke
  test: pipeline harness + model gratis berfungsi end-to-end 3/3 run,
  angka selalu benar; kelemahan yang tersisa ada di tahap verifier/fix
  (model gratis), sudah dimitigasi, bukan dihitung.**

## 3. Temuan perilaku harness (bukan taksonomi kegagalan dev-set)

- **Verifier model gratis tidak konsisten** mengikuti kontrak "PASS atau
  daftar issue bernomor" — 2 dari 3 run mengembalikan verdict non-PASS
  tanpa issue jelas atas deliverable yang benar. Mitigasi: verdict tanpa
  daftar issue → PASS; verdict kosong → PASS.
- **Endpoint 100ms membocorkan format tool-call native DeepSeek** (`｜DSML｜`)
  sebagai teks saat model gagal emit function call / saat `tool_choice="none"`.
  Mitigasi: teguran sekali di `agent_loop` + jangan jadikan teks itu jawaban
  akhir di luar wrap-up.
- **Varians token besar antar run** untuk tugas yang sama: 82k / 143k /
  96k token input. Untuk 29 tugas nyata (6 jam/tugas) anggarannya harus
  diukur per tugas; kuota gratis 100M/hari masih longgar untuk baseline,
  tapi konteks 198K model gratis bisa jadi batas di tugas panjang.
- **Worker berperilaku seperti engineer yang hati-hati** (verifikasi
  independen, determinism check, placeholder sweep, cleanup) — arsitektur
  4 tahap + calc-verifier bekerja sesuai desain pada tugas sintetik.

## 3. Blocker keras

### B1. Kit tidak boleh dieksekusi — butuh persetujuan Yudhi
Clone `google-research/ple` memicu execution-risk check pada hasil tool.
Aturan: JANGAN menjalankan kode kit (`kit validate`, `kit check`,
`eval/run.py`, `kit artifacts`, `kit up`) sampai Yudhi menyetujui secara
eksplisit bahwa kode kit boleh dijalankan. Dampak: tidak ada `kit validate`
malam ini, tidak ada skor resmi dev-set, tidak ada `artifacts/` resmi.
Yang TIDAK kena blokir: membaca file kit (sudah dilakukan — protocol,
local-models, artifacts, eval/README), menjalankan harness sendiri
(`serve.py`/`harness.py` — kode repo sendiri, sudah dibaca penuh), dan
runner lokal `eval/run_local.py`.

**Pertanyaan untuk Yudhi:** "Bolehkah Cryptoboy menjalankan kode kit resmi
kompetisi PLE (repo google-research/ple — `kit validate` / `eval/run.py`)
di VM ini?"

### B2. Dataset dev-set gated — butuh akun Hugging Face + akses
`eval/run.py` mengunduh tugas dari dataset HF dengan `HF_TOKEN`. Akses
dataset harus diminta dulu di halaman dataset sambil login ke Hugging Face,
lalu token read dibuat. Yang dibutuhkan:
1. Akun Hugging Face (buat bila belum ada — kerja browser).
2. Buka https://huggingface.co/datasets/google/physical-engineerings-last-exam,
   klik "Request access" / setujui syarat dataset.
3. Buat read token (Settings → Access Tokens) dan simpan sebagai `HF_TOKEN`
   (jangan pernah tulis token di chat; simpan mode 600 seperti key lain).
Tanpa ini, TIDAK ADA tugas dev yang bisa dijalankan — resmi maupun lokal.

## 4. Rencana baseline 3–5 tugas (setelah B1 + B2 beres)

Urutan (campur domain + jenis grading, mulai dari yang paling terukur):
1. `data-hall-mep-routing` (Mechanical, checks, `solution.py`) — kode + IFC.
2. `wind-diaphragm-shear` (Structural, checks, `submission.zip`) — kalkulasi.
3. `lv-cable-sizing` (Electrical, checks-judge, `submission.zip`) — kalkulasi.
4. `fire-test-validation-memo` (Mechanical, rubric, `final_message`) — memo.
5. `data-center-site-model` (Civil, checks, `model.ifc`) — tersulit, terakhir.

Perintah resmi (setelah B1 disetujui + `HF_TOKEN` ada):
```bash
cd ~/workspace/ple-kit
uv run python eval/run.py ../kaggle-ple-harness --env-file local.env \
  --tasks data-hall-mep-routing,wind-diaphragm-shear \
  --model-base-url https://100milionseek.top/v1
# + MODEL_API_KEY (100ms) di local.env; judge lokal = model sendiri
```
Catatan: `eval/run.py` butuh Docker + Harbor 0.20.0 (`uv tool install
harbor==0.20.0 --with websockets`) + ~10 GB disk untuk image.

## 5. Taksonomi kegagalan pertama

_(diisi setelah run dev-set pertama; smoke test sintetik bukan sumber
taksonomi — terlalu mudah)_
