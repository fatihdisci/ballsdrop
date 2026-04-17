import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import subprocess
import threading
import sys
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent


class DropCounterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Drop Counter Launcher")
        self.root.minsize(520, 600)
        self.root.resizable(True, True)
        self.process = None
        self.running = False
        self._setup_ui()

    def _setup_ui(self):
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        # Baslik
        ttk.Label(main, text="DROP COUNTER", font=("Arial", 14, "bold")).pack(anchor="w")
        ttk.Label(main, text="YouTube Shorts Video Renderer", foreground="gray").pack(anchor="w")
        ttk.Separator(main, orient="horizontal").pack(fill="x", pady=10)

        # Ayarlar
        settings = ttk.LabelFrame(main, text="Ayarlar", padding=12)
        settings.pack(fill="x", pady=(0, 8))
        settings.columnconfigure(1, weight=1)

        # Metric
        ttk.Label(settings, text="Metric:").grid(row=0, column=0, sticky="w", padx=4, pady=6)
        self.metric_var = tk.StringVar(value="subs")
        mf = ttk.Frame(settings)
        mf.grid(row=0, column=1, sticky="w")
        ttk.Radiobutton(mf, text="Subscribers", variable=self.metric_var, value="subs").pack(side="left", padx=6)
        ttk.Radiobutton(mf, text="Likes", variable=self.metric_var, value="likes").pack(side="left", padx=6)
        ttk.Radiobutton(mf, text="Views", variable=self.metric_var, value="views").pack(side="left", padx=6)

        # Top sayisi
        ttk.Label(settings, text="Top Sayisi:").grid(row=1, column=0, sticky="w", padx=4, pady=6)
        self.count_var = tk.StringVar(value="500")
        ttk.Spinbox(settings, from_=1, to=9999, textvariable=self.count_var, width=10).grid(row=1, column=1, sticky="w")
        ttk.Label(settings, text="adet", foreground="gray").grid(row=1, column=2, sticky="w", padx=4)

        # Sure
        ttk.Label(settings, text="Video Suresi:").grid(row=2, column=0, sticky="w", padx=4, pady=6)
        self.duration_var = tk.StringVar(value="135")
        ttk.Spinbox(settings, from_=10, to=600, textvariable=self.duration_var, width=10).grid(row=2, column=1, sticky="w")
        ttk.Label(settings, text="saniye (onerilen: 120-150)", foreground="gray").grid(row=2, column=2, sticky="w", padx=4)

        # Cikti dosyasi
        ttk.Label(settings, text="Cikti Dosyasi:").grid(row=3, column=0, sticky="w", padx=4, pady=6)
        of = ttk.Frame(settings)
        of.grid(row=3, column=1, columnspan=2, sticky="ew")
        self.output_var = tk.StringVar(value="output.mp4")
        ttk.Entry(of, textvariable=self.output_var).pack(side="left", fill="x", expand=True)
        ttk.Button(of, text="Gozat...", command=self._browse_output, width=9).pack(side="left", padx=(6, 0))

        # Preview
        ttk.Label(settings, text="Preview:").grid(row=4, column=0, sticky="w", padx=4, pady=6)
        self.preview_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(settings, text="Render sirasinda onizleme goster (render yavaslar)",
                        variable=self.preview_var).grid(row=4, column=1, columnspan=2, sticky="w")

        # Butonlar
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill="x", pady=8)

        self.start_btn = ttk.Button(btn_frame, text="RENDER BASLAT", command=self.start_render, width=18)
        self.start_btn.pack(side="left", padx=(0, 6))

        self.stop_btn = ttk.Button(btn_frame, text="Durdur", command=self.stop_render, state="disabled", width=10)
        self.stop_btn.pack(side="left")

        self.open_btn = ttk.Button(btn_frame, text="Videoyu Ac", command=self._open_video, state="disabled")
        self.open_btn.pack(side="right")

        # Ilerleme
        self.progress_var = tk.DoubleVar(value=0)
        self.progress = ttk.Progressbar(main, variable=self.progress_var, maximum=100, length=300)
        self.progress.pack(fill="x", pady=(0, 2))
        self.status_label = ttk.Label(main, text="Hazir")
        self.status_label.pack(anchor="w", pady=(0, 6))

        # Log
        ttk.Label(main, text="Cikti:").pack(anchor="w")
        self.log = scrolledtext.ScrolledText(main, height=14, state="disabled",
                                              font=("Consolas", 9), wrap="word")
        self.log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4 Video", "*.mp4"), ("Tum Dosyalar", "*.*")],
            initialfile=self.output_var.get(),
            title="Kayit Konumunu Sec"
        )
        if path:
            self.output_var.set(path)

    def _open_video(self):
        output = self.output_var.get()
        if not Path(output).is_absolute():
            output = str(SCRIPT_DIR / output)
        if Path(output).exists():
            os.startfile(output)
        else:
            messagebox.showerror("Hata", f"Dosya bulunamadi:\n{output}")

    def _log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def start_render(self):
        if self.running:
            return

        try:
            count = int(self.count_var.get())
            duration = int(self.duration_var.get())
            if count < 1 or duration < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Gecersiz Giris", "Top sayisi ve sure gecerli bir sayi olmali.")
            return

        output = self.output_var.get().strip()
        if not output:
            messagebox.showerror("Gecersiz Giris", "Cikti dosyasi bos olamaz.")
            return

        metric = self.metric_var.get()
        preview = self.preview_var.get()

        self._clear_log()
        self.running = True
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.open_btn.config(state="disabled")
        self.progress_var.set(0)
        self.status_label.config(text="Baslatiliyor...")

        thread = threading.Thread(
            target=self._run_render,
            args=(metric, count, duration, output, preview),
            daemon=True
        )
        thread.start()

    def _run_render(self, metric, count, duration, output, preview):
        dropcounter = SCRIPT_DIR / "dropcounter.py"

        cmd = [
            sys.executable, str(dropcounter),
            "--metric", metric,
            "--count", str(count),
            "--duration", str(duration),
            "--output", output,
        ]
        if not preview:
            cmd.append("--no-preview")

        total_frames = None

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(SCRIPT_DIR),
                bufsize=1
            )

            for line in self.process.stdout:
                self.root.after(0, self._log, line)

                stripped = line.strip()

                # Toplam frame sayisini al
                if "Total frames:" in line:
                    try:
                        total_frames = int(stripped.split("Total frames:")[-1].strip().replace(",", ""))
                    except Exception:
                        pass

                # Frame ilerleme: "  Frame   300/ 2400 ( 12.5%) — Balls: ..."
                elif stripped.startswith("Frame") and "/" in stripped and total_frames:
                    try:
                        nums = stripped.split("/")
                        current = int(nums[0].split()[-1].strip())
                        pct = current / total_frames * 100
                        label = f"Isleniyor: {current:,} / {total_frames:,} frame  ({pct:.0f}%)"
                        self.root.after(0, self.progress_var.set, pct)
                        self.root.after(0, self.status_label.config, {"text": label})
                    except Exception:
                        pass

                elif "Rendering audio" in line:
                    self.root.after(0, self.progress_var.set, 97)
                    self.root.after(0, self.status_label.config, {"text": "Ses isleniyor..."})

                elif "Encoding video" in line:
                    self.root.after(0, self.progress_var.set, 99)
                    self.root.after(0, self.status_label.config, {"text": "Video kodlaniyor (FFmpeg)..."})

            self.process.wait()
            code = self.process.returncode

            if code == 0:
                self.root.after(0, self.progress_var.set, 100)
                self.root.after(0, self.status_label.config, {"text": "TAMAMLANDI!"})
                self.root.after(0, self._log, "\n--- RENDER TAMAMLANDI ---\n")
                self.root.after(0, self.open_btn.config, {"state": "normal"})
            else:
                self.root.after(0, self.status_label.config, {"text": f"HATA (cikis kodu: {code})"})
                self.root.after(0, self._log, f"\n--- RENDER BASARISIZ (kod: {code}) ---\n")

        except Exception as e:
            self.root.after(0, self._log, f"\nHATA: {e}\n")
            self.root.after(0, self.status_label.config, {"text": "Beklenmeyen hata"})

        finally:
            self.process = None
            self.running = False
            self.root.after(0, self.start_btn.config, {"state": "normal"})
            self.root.after(0, self.stop_btn.config, {"state": "disabled"})

    def stop_render(self):
        if self.process:
            self.process.terminate()
        self.running = False
        self.root.after(0, self.start_btn.config, {"state": "normal"})
        self.root.after(0, self.stop_btn.config, {"state": "disabled"})
        self.root.after(0, self.status_label.config, {"text": "Durduruldu"})
        self.root.after(0, self._log, "\n--- RENDER DURDURULDU ---\n")


if __name__ == "__main__":
    root = tk.Tk()
    app = DropCounterGUI(root)
    root.mainloop()
