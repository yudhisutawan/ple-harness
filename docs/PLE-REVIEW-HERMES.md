# Analisis Arsitektur Harness PLE (Cryptoboy v0.1)

Analisis ini mengevaluasi arsitektur 4-tahap (Planner, Worker, Calc-Verifier, Verifier) untuk kompetisi Kaggle Physical-Engineering Last Exam.

## 1. Lima Kelemahan Terbesar Arsitektur

1.  **Hambatan "Read-Only" pada Calc-Verifier**: Arsitektur mewajibkan Calc-Verifier menjalankan ulang script perhitungan, namun ia tidak memiliki `write_file`. Jika Worker gagal menulis script yang *self-contained* atau lupa menyertakan file data input, Calc-Verifier akan gagal total tanpa bisa melakukan perbaikan kecil pada kode, menyebabkan kegagalan verifikasi yang sebenarnya bisa dihindari.
2.  **Alokasi Waktu Statis vs Dinamis**: Pembagian waktu (10% Plan, 65% Work, 25% Verify/Fix) terlalu kaku. Tugas engineering fisika yang kompleks seringkali membutuhkan iterasi cepat antara hitungan dan validasi. Menunggu hingga 75% waktu habis baru melakukan verifikasi perhitungan (`calc-verify`) berisiko menemukan kesalahan fundamental saat waktu sudah hampir habis (dead-end).
3.  **Risiko "Silent Pass" pada Logika Verifikasi**: Harness menganggap hasil verifikasi sebagai `PASS` jika tidak ditemukan daftar bernomor (baris 539). Dalam tugas engineering yang ambigu, LLM Verifier mungkin memberikan catatan kritis dalam bentuk paragraf atau saran tanpa nomor. Arsitektur ini akan mengabaikan kritik tersebut dan langsung melakukan submit.
4.  **Isolasi Konteks Reasoning**: Verifier dan Calc-Verifier tidak diberikan akses ke *thought process* (reasoning) Worker. Dalam engineering fisika, pemilihan asumsi (misal: koefisien gesek, standar material) sangat krusial. Tanpa memahami "mengapa" suatu angka dipilih, Verifier mungkin memberikan feedback yang tidak relevan atau salah arah.
5.  **Prompt Peran Terlalu Deskriptif, Kurang Prosedural**: Prompt `CALC_VERIFIER` memerintahkan pemeriksaan "dimensional consistency" secara umum. Tanpa instruksi prosedural yang keras (seperti: "Gunakan pustaka `pint` jika tersedia" atau "Cek rasio L/d secara eksplisit"), LLM cenderung melakukan pengecekan visual yang dangkal daripada audit teknis yang mendalam.

## 2. Tiga Perbaikan Konkret

1.  **Pemberian WRITE_TOOLS Terbatas untuk Calc-Verifier**: Izinkan Calc-Verifier menulis ke direktori khusus (misal: `calc/verify_logs/`). Ini memungkinkan pemeriksa untuk membuat script tandingan sendiri untuk memvalidasi angka Worker tanpa mengganggu deliverable utama, memberikan bukti audit yang lebih kuat bagi Worker saat fase perbaikan.
2.  **Mekanisme Early-Exit & Time-Reallocation**: Tambahkan logika di `harness.py` untuk mendeteksi penyelesaian tahap lebih awal. Jika `PLANNER` selesai dalam 5 menit, sisa 30 menit (dari 10% budget) harus dialokasikan secara otomatis ke fase `WORKER` atau `FIX ROUNDS` untuk meningkatkan ketelitian.
3.  **Cross-Reference Units Ledger Otomatis**: Alih-alih mengandalkan Verifier untuk "spot-check" angka, buat fungsi pembantu (helper) yang secara otomatis membandingkan angka di file `.md` deliverable dengan angka di `calc/UNITS.md` menggunakan Regex. Ini memastikan sinkronisasi data tanpa membuang token/konteks LLM untuk tugas mekanis.

## 3. Pendekatan Alternatif: "Independent Double-Check (Dual-Agent)"

**Konsep**: Gantikan urutan linear dengan pendekatan redundansi paralel.
*   **Prosedur**: Dua agen independen (Agen A dan Agen B) menerima instruksi yang sama dan bekerja di folder terpisah (`/workdir/A` dan `/workdir/B`) secara simultan. Setelah keduanya selesai, seorang **Arbitrator** membandingkan `calc/UNITS.md` dari keduanya.
*   **Alasan**: Dalam praktek teknik profesional (Civil/Mechanical), redundansi adalah standar emas. Jika dua agen menghasilkan angka yang sama (margin < 1%) melalui proses yang berbeda, tingkat kepercayaan (confidence score) terhadap hasil tersebut sangat tinggi. Jika berbeda, Arbitrator hanya perlu fokus membedah perbedaan asumsi atau rumus di antara keduanya, yang jauh lebih efisien daripada melakukan verifikasi dari nol.
