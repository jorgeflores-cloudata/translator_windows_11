"""Medidor de audio en vivo: el callback solo copia un búfer pequeño.

La FFT y todo acceso a Tk se ejecutan desde ``update_meter`` en el hilo de UI.
Las barras muestran energía de audio, no una predicción de que exista voz.
"""

from collections import deque
import math
import threading
import time
import tkinter as tk
from tkinter import ttk

import numpy as np


MAX_SAMPLES = 4096
STALE_AFTER = 0.18
CLEAR_AFTER = 0.38


def spectrum_levels(samples, rate, bands=24, gain=1.0):
    """Devuelve ``bands`` niveles 0..1 en bandas logarítmicas (50 Hz a 10 kHz).

    Acepta audio mono o multicanal normalizado a -1..1. No modifica la entrada.
    NaN/Inf, silencio, tasas inválidas y entradas vacías producen niveles seguros.
    """
    bands = max(1, int(bands))
    levels = np.zeros(bands, dtype=np.float32)
    try:
        rate = float(rate)
        gain = float(gain)
    except (TypeError, ValueError):
        return levels
    if not math.isfinite(rate) or rate <= 100:
        return levels
    if not math.isfinite(gain) or gain <= 0:
        gain = 1.0
    gain = min(gain, 1000.0)
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=-1)
    x = np.nan_to_num(x.reshape(-1)[-MAX_SAMPLES:], nan=0.0, posinf=0.0, neginf=0.0)
    if x.size < 4:
        return levels
    x = x.astype(np.float64) * gain
    x -= x.mean()  # Un offset de CC no es audio audible.
    if not np.any(x):
        return levels
    window = np.hanning(x.size)
    magnitude = np.abs(np.fft.rfft(x * window)) * (2.0 / max(window.sum(), 1.0))
    frequencies = np.fft.rfftfreq(x.size, d=1.0 / rate)
    high = min(10000.0, rate * 0.5)
    edges = np.geomspace(50.0, high, bands + 1)
    for i in range(bands):
        mask = (frequencies >= edges[i]) & (frequencies < edges[i + 1])
        if np.any(mask):
            amplitude = float(np.sqrt(np.sum(magnitude[mask] ** 2)))
        else:
            amplitude = float(np.interp(math.sqrt(edges[i] * edges[i + 1]),
                                        frequencies, magnitude))
        db = 20.0 * math.log10(max(amplitude, 1e-12))
        levels[i] = np.clip((db + 70.0) / 70.0, 0.0, 1.0)
    return levels


class AudioMeter(ttk.Frame):
    """Ecualizador visual. ``feed`` es seguro para callbacks de audio.

    Llama a ``update_meter(active, recording)`` cada ~50 ms desde el hilo de Tk.
    ``gain=0`` se interpreta como señal sin amplificación para el modo automático.
    """

    BG = "#0b1422"
    GRID = "#203044"
    MUTED = "#8fa3bb"
    TEXT = "#dce9f7"
    SIGNAL = "#2dd4bf"
    HIGH = "#fbbf24"
    CLIP = "#fb7185"

    def __init__(self, master, bands=24, **kwargs):
        super().__init__(master, **kwargs)
        self.bands = max(1, int(bands))
        self._lock = threading.Lock()
        self._chunks = deque()
        self._sample_count = 0
        self._rate = 16000.0
        self._gain = 1.0
        self._last_feed = 0.0
        self._revision = 0
        self._computed_revision = -1
        self._target = np.zeros(self.bands, dtype=np.float32)
        self._levels = self._target.copy()
        self._caps = self._target.copy()
        self._rms = self._peak = 0.0
        self._last_update = time.monotonic()
        self._clipping = False

        panel = tk.Frame(self, bg=self.BG, padx=12, pady=9)
        panel.pack(fill="both", expand=True)
        top = tk.Frame(panel, bg=self.BG)
        top.pack(fill="x")
        tk.Label(top, text="SEÑAL DEL MICRÓFONO", font=("Segoe UI", 8, "bold"),
                 bg=self.BG, fg=self.MUTED).pack(side="left")
        self.status = tk.Label(top, text="Micrófono inactivo", font=("Segoe UI", 8),
                               bg=self.BG, fg=self.MUTED)
        self.status.pack(side="right")
        self.canvas = tk.Canvas(panel, height=66, width=260, bg=self.BG,
                                highlightthickness=0, bd=0)
        self.canvas.pack(fill="x", pady=(6, 3))
        self._grid = [self.canvas.create_line(0, 0, 0, 0, fill=self.GRID)
                      for _ in range(3)]
        self._bars = [self.canvas.create_rectangle(0, 0, 0, 0, outline="", fill=self.SIGNAL)
                      for _ in range(self.bands)]
        self._peak_caps = [self.canvas.create_rectangle(0, 0, 0, 0,
                                                       outline="", fill="#93e7d8")
                           for _ in range(self.bands)]
        self.detail = tk.Label(panel, text="Activa el micrófono o inicia una grabación.",
                               anchor="w", font=("Segoe UI", 8), bg=self.BG, fg=self.MUTED)
        self.detail.pack(fill="x")
        self.canvas.bind("<Configure>", lambda event: self._draw())

    def feed(self, data, rate, gain=1.0):
        """Copia hasta 4096 muestras; no usa Tk ni calcula FFT en el callback."""
        try:
            rate = float(rate)
            gain = float(gain)
            if not math.isfinite(rate) or rate <= 100:
                return
            if not math.isfinite(gain) or gain <= 0:
                gain = 1.0
            gain = min(gain, 1000.0)
            samples = np.asarray(data, dtype=np.float32)
            if samples.ndim > 1:
                samples = samples.mean(axis=-1)
            samples = samples.reshape(-1)[-MAX_SAMPLES:].copy()
            if not samples.size:
                return
        except (TypeError, ValueError):
            return
        with self._lock:
            if self._rate != rate:
                self._chunks.clear()
                self._sample_count = 0
            self._chunks.append(samples)
            self._sample_count += samples.size
            while self._sample_count > MAX_SAMPLES:
                excess = self._sample_count - MAX_SAMPLES
                first = self._chunks[0]
                if first.size <= excess:
                    self._sample_count -= self._chunks.popleft().size
                else:
                    self._chunks[0] = first[excess:]
                    self._sample_count -= excess
            self._rate, self._gain = rate, gain
            self._last_feed = time.monotonic()
            self._revision += 1

    def reset(self):
        """Descarta audio pendiente; el siguiente refresco borra las barras."""
        with self._lock:
            self._chunks.clear()
            self._sample_count = 0
            self._last_feed = 0.0
            self._revision += 1

    def update_meter(self, active=False, recording=False):
        """Refresca espectro y etiquetas desde el hilo principal de Tk."""
        now = time.monotonic()
        dt = max(0.005, min(0.2, now - self._last_update))
        self._last_update = now
        with self._lock:
            age = now - self._last_feed
            revision = self._revision
            rate, gain = self._rate, self._gain
            chunks = tuple(self._chunks) if revision != self._computed_revision else ()
        live = bool(active or recording)
        if live and age < STALE_AFTER:
            if chunks:
                samples = np.nan_to_num(np.concatenate(chunks)[-MAX_SAMPLES:],
                                        nan=0.0, posinf=0.0, neginf=0.0)
                self._target = spectrum_levels(samples, rate, self.bands, gain)
                amplified = samples.astype(np.float64) * gain
                self._peak = float(np.abs(amplified).max()) if amplified.size else 0.0
                centered = amplified - amplified.mean() if amplified.size else amplified
                self._rms = float(np.sqrt(np.mean(centered ** 2))) if centered.size else 0.0
                self._computed_revision = revision
        else:
            self._target = np.zeros(self.bands, dtype=np.float32)
            self._rms = self._peak = 0.0

        if not live or age >= CLEAR_AFTER:
            self._levels.fill(0)
            self._caps.fill(0)
        else:
            tau = np.where(self._target > self._levels, 0.025, 0.10)
            self._levels += (self._target - self._levels) * (1 - np.exp(-dt / tau))
            self._caps = np.maximum(self._levels, self._caps - dt * 1.5)
        self._clipping = live and self._peak >= 0.98
        db = max(-70.0, 20.0 * math.log10(max(self._rms, 1e-12)))
        if not live:
            status, detail, color = ("Micrófono inactivo",
                                      "Activa el micrófono o inicia una grabación.", self.MUTED)
        elif age >= STALE_AFTER:
            status, detail, color = ("Esperando audio", "Sin datos recientes del micrófono.",
                                      self.MUTED)
        else:
            mode = "Grabando" if recording else "Escuchando"
            if self._clipping:
                status, detail, color = (f"{mode} · picos altos",
                                          "Volumen alto: revisa la ganancia del micrófono.",
                                          self.CLIP)
            elif db > -50:
                status, detail, color = (f"{mode} · audio presente",
                                          f"Nivel {db:.0f} dBFS",
                                          self.SIGNAL)
            else:
                status, detail, color = (f"{mode} · señal baja", f"Nivel {db:.0f} dBFS",
                                          self.MUTED)
        self.status.configure(text=status, fg=color)
        self.detail.configure(text=detail, fg=self.CLIP if self._clipping else self.MUTED)
        self._draw()

    def _draw(self):
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        baseline = height - 2
        usable = max(1, height - 7)
        for i, line in enumerate(self._grid, 1):
            y = baseline - usable * i / 3
            self.canvas.coords(line, 0, y, width, y)
        step = width / self.bands
        gap = min(4.0, step * 0.3)
        for i, (bar, cap) in enumerate(zip(self._bars, self._peak_caps)):
            left, right = i * step + gap / 2, (i + 1) * step - gap / 2
            level = float(self._levels[i])
            top = baseline - max(1.0, level * usable)
            color = self.CLIP if self._clipping else self.HIGH if level > 0.88 else self.SIGNAL
            self.canvas.coords(bar, left, top, right, baseline)
            self.canvas.itemconfigure(bar, fill=color if level > 0.01 else self.GRID)
            peak_y = baseline - float(self._caps[i]) * usable
            self.canvas.coords(cap, left, peak_y - 1, right, peak_y)
            self.canvas.itemconfigure(cap, state="normal" if self._caps[i] > 0.025 else "hidden",
                                      fill=self.CLIP if self._clipping else "#93e7d8")
