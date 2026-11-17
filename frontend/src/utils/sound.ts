/**
 * Web Audio Bell Synthesizer
 * ==========================
 * Generates pure synthesized acoustic bell chimes for trading operations:
 * - Order executions (BUY / SELL)
 * - Market Open / Close
 * - System alerts and errors
 *
 * Runs 100% offline using native Web Audio API oscillators without external asset dependencies.
 */

class SoundService {
  private ctx: AudioContext | null = null;
  private soundEnabled: boolean = true;

  constructor() {
    try {
      const stored = localStorage.getItem("algo:sound_enabled");
      this.soundEnabled = stored === null ? true : stored === "true";
    } catch {
      this.soundEnabled = true;
    }
  }

  public isEnabled(): boolean {
    return this.soundEnabled;
  }

  public setEnabled(enabled: boolean) {
    this.soundEnabled = enabled;
    try {
      localStorage.setItem("algo:sound_enabled", String(enabled));
    } catch {}
  }

  private getAudioContext(): AudioContext | null {
    if (typeof window === "undefined") return null;
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === "suspended") {
      this.ctx.resume().catch(() => {});
    }
    return this.ctx;
  }

  /**
   * Crisp, ascending bell chime for BUY/SELL orders.
   * BUY: Bright, crisp ascending chime (587Hz D5 -> 880Hz A5)
   * SELL: Slightly lower, warm chime (523Hz C5 -> 784Hz G5)
   */
  public playOrderChime(side: "BUY" | "SELL" = "BUY") {
    if (!this.soundEnabled) return;
    const ctx = this.getAudioContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const baseFreq = side === "BUY" ? 587.33 : 523.25; // D5 vs C5
      const secondFreq = side === "BUY" ? 880.0 : 783.99; // A5 vs G5

      // Strike tone (sine wave)
      const osc1 = ctx.createOscillator();
      const gain1 = ctx.createGain();
      osc1.type = "sine";
      osc1.frequency.setValueAtTime(baseFreq, now);
      gain1.gain.setValueAtTime(0.25, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
      osc1.connect(gain1);
      gain1.connect(ctx.destination);
      osc1.start(now);
      osc1.stop(now + 0.4);

      // Overtone chime (triangle wave layered slightly after for bell harmonic)
      const osc2 = ctx.createOscillator();
      const gain2 = ctx.createGain();
      osc2.type = "triangle";
      osc2.frequency.setValueAtTime(secondFreq, now + 0.06);
      gain2.gain.setValueAtTime(0.28, now + 0.06);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.55);
      osc2.connect(gain2);
      gain2.connect(ctx.destination);
      osc2.start(now + 0.06);
      osc2.stop(now + 0.6);
    } catch {}
  }

  /**
   * Harmonious chime for Market Open / Close
   * Open: Triumphant rising triad (C5 -> E5 -> G5)
   * Close: Gentle descending chime (G5 -> E5 -> C5)
   */
  public playMarketBell(isOpen: boolean) {
    if (!this.soundEnabled) return;
    const ctx = this.getAudioContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const notes = isOpen ? [523.25, 659.25, 783.99] : [783.99, 659.25, 523.25];

      notes.forEach((freq, idx) => {
        const startTime = now + idx * 0.15;
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();

        osc.type = "sine";
        osc.frequency.setValueAtTime(freq, startTime);

        gain.gain.setValueAtTime(0, startTime);
        gain.gain.linearRampToValueAtTime(0.25, startTime + 0.02);
        gain.gain.exponentialRampToValueAtTime(0.001, startTime + 0.85);

        osc.connect(gain);
        gain.connect(ctx.destination);

        osc.start(startTime);
        osc.stop(startTime + 0.9);
      });
    } catch {}
  }

  /**
   * Warning / Error alert tone
   */
  public playAlertSound() {
    if (!this.soundEnabled) return;
    const ctx = this.getAudioContext();
    if (!ctx) return;

    try {
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();

      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(340, now);
      osc.frequency.linearRampToValueAtTime(220, now + 0.25);

      gain.gain.setValueAtTime(0.16, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);

      osc.connect(gain);
      gain.connect(ctx.destination);

      osc.start(now);
      osc.stop(now + 0.35);
    } catch {}
  }
}

export const soundService = new SoundService();
