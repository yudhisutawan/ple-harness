# Baseline minggu 1 — PLE (25 Nov 2026)

Status: **setup selesai, baseline dev-set BELUM bisa jalan — blocker B2 (HF gated) + Docker VM tidak bisa pull image; VPS hermes bukan mesin run yang layak**
(lihat §3 + §6). Yang jalan malam ini: smoke test sintetik lokal + `kit validate` lolos.

## 1. Yang sudah diverifikasi malam ini

| Item | Hasil |
|---|---|
| `uv` | Terpasang 0.13.10 (`~/.local/bin/uv`) |
| Docker | CLI 29.1.3 terpasang; daemon jalan (4 CPU / 7,75 GB) tapi **tidak bisa pull image**: `docker run hello-world` gagal — `registry-1.docker.io` tidak terjangkau (context deadline exceeded, 60 dtk; dicoba ulang 25 Nov malam). Dampak: `kit check` / `eval/run.py` resmi TIDAK BISA jalan di VM ini walau `HF_TOKEN` sudah ada. VPS `hermes` juga bukan alternatif (lihat B3): ARM 2 CPU / 11 GB, Docker tidak terpasang. |
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

### B1. Kit tidak boleh dieksekusi — ✅ SELESAI 25 Nov 22:09 WITA
Yudhi memberi go-ahead eksplisit ("Boleh, jalankan kit resmi PLE").
Hasil: `kit validate` pada entry asli **LOLOS** ("ok: cryptoboy-ple,
google-cloud/gemini-3.8-flash; egress none"), dan pada salinan lokal
`ple-harness-local` (model_api openai-compatible) juga **LOLOS**.
Harbor 0.20.0 terpasang (`uv tool install harbor==0.20.0 --with websockets`).
Go-ahead ini hanya berlaku untuk kode kit resmi google-research/ple.

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

**Terkonfirmasi 25 Nov 22:xx WITA (probe `eval/run.py`, 1 tugas):** download
gagal dengan `GatedRepoError` — "set HF_TOKEN to a token that can read it
(while the dataset is gated, request access on that page, signed in to
Hugging Face, and use a token of the account that was granted it)".
Dataset commit `9ca4de831267` (metadata terbaca anonim, `"gated":"auto"`).
Diagnosis tambahan: percobaan pertama gagal dengan `InvalidURL: Invalid
port: ':1]'` — BUKAN gate, melainkan entri IPv6 berkurung (`[::1]`,
`[fd8b:...]`) di `NO_PROXY` yang merusak parsing URL di stack HTTP Python
(huggingface_hub). Workaround: jalankan dengan `NO_PROXY=localhost,127.0.0.1
no_proxy=localhost,127.0.0.1` — setelah itu metadata HF terbaca dan
download mencapai gate yang sebenarnya.

### B3. Docker VM tidak bisa pull image; VPS hermes bukan mesin run
- **VM ini:** daemon jalan (4 CPU / 7,75 GB), tapi `docker run hello-world`
  gagal — `registry-1.docker.io` tidak terjangkau (context deadline
  exceeded, 60 dtk). Jadi `kit check` / `eval/run.py` TIDAK BISA jalan di
  sini walau `HF_TOKEN` sudah ada — keduanya butuh pull/build image.
- **VPS `hermes` (dicek 25 Nov malam, read-only via SSH):** `aarch64`
  (ARM), 2 CPU, RAM 11 GB (10 available), disk 38 GB bebas, dan **Docker
  tidak terpasang** (`docker: command not found`). Kit butuh image
  `linux/amd64` + slot 6 CPU / 16,25 GB per tugas. Kesimpulan: VPS **tidak
  layak** jadi mesin run (butuh install Docker + emulasi amd64 di ARM 2 CPU
  — sangat lambat, belum tentu didukung Harbor/kit). Opsi mesin run yang
  tersisa: VM/laptop lain milik Yudhi dengan Docker penuh + 6+ CPU / 16+ GB
  RAM, atau cloud VM (butuh biaya — tanya Yudhi dulu).

## 4. Rencana baseline 3–5 tugas (setelah B1 + B2 beres)

Urutan (campur domain + jenis grading, mulai dari yang paling terukur):
1. `data-hall-mep-routing` (Mechanical, checks, `solution.py`) — kode + IFC.
2. `wind-diaphragm-shear` (Structural, checks, `submission.zip`) — kalkulasi.
3. `lv-cable-sizing` (Electrical, checks-judge, `submission.zip`) — kalkulasi.
4. `fire-test-validation-memo` (Mechanical, rubric, `final_message`) — memo.
5. `data-center-site-model` (Civil, checks, `model.ifc`) — tersulit, terakhir.

Perintah resmi (setelah B1 disetujui + `HF_TOKEN` ada + mesin yang Docker-nya
bisa pull image — lihat §6; entry yang dijalankan adalah salinan lokal
`../ple-harness-local`, BUKAN repo asli, karena `--model-base-url` ditolak
untuk entry `google-cloud`):
```bash
cd ~/workspace/ple-kit
NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
  uv run python eval/run.py ../ple-harness-local --env-file local.env \
  --tasks data-hall-mep-routing,wind-diaphragm-shear
# + MODEL_API_KEY (100ms) di local.env; judge lokal = model sendiri
```
Catatan: `eval/run.py` butuh Docker + Harbor 0.20.0 (`uv tool install
harbor==0.20.0 --with websockets`, sudah terpasang) + ~10 GB disk untuk image.

## 5. Taksonomi kegagalan pertama

_(diisi setelah run dev-set pertama; smoke test sintetik bukan sumber
taksonomi — terlalu mudah)_

## 6. Validasi kit + probe eval/run.py (25 Nov malam, setelah go-ahead Yudhi)

- `kit validate` entry asli: **LOLOS** (`cryptoboy-ple`,
  `google-cloud/gemini-3.8-flash`, egress none). `kit validate` salinan
  lokal (`ple-harness-local`, `openai-compatible/deepseek-v4.1-flash-free`,
  `model_base_url: https://100milionseek.top/v1`): **LOLOS** (egress
  `100milionseek.top:443`).
- **Catatan model lokal:** `submission.yaml` asli (`google-cloud/...`)
  MENOLAK `--model-base-url` ("a google-cloud model is reached through
  MODEL_PROXY_URL..."). Karena itu baseline lokal memakai salinan terpisah
  `~/workspace/ple-harness-local/` (commit `6de91cf`, hanya ubah
  `model_api`/`model_base_url`, repo asli TIDAK diubah). Key 100ms di
  `~/workspace/ple-kit/local.env` (mode 600, `MODEL_API_KEY`, tidak pernah
  di-print); judge lokal = model sendiri (otomatis untuk entry
  openai-compatible).
- **Probe `eval/run.py` (1 tugas, `data-hall-mep-routing`):** gagal di
  download dataset — `GatedRepoError`, HF_TOKEN belum ada (lihat B2).
  Perintah yang dipakai (setelah B2 beres, dan di mesin yang Docker-nya
  bisa pull image):
  ```bash
  cd ~/workspace/ple-kit
  NO_PROXY=localhost,127.0.0.1 no_proxy=localhost,127.0.0.1 \
    uv run python eval/run.py ../ple-harness-local --env-file local.env \
    --tasks data-hall-mep-routing,wind-diaphragm-shear,lv-cable-sizing,fire-test-validation-memo,data-center-site-model
  ```
- **Skor baseline resmi: BELUM ADA** (0/5 tugas terukur — blokir B2 + Docker).
  Taksonomi kegagalan tetap kosong sampai run pertama berhasil.
