"""
Drop Counter — YouTube Shorts Video Renderer
=============================================
Komple offline Python pipeline.
Her frame mükemmel kalitede render edilir, FFmpeg ile 1080x1920 mp4 çıkar.

Kurulum:
    pip install pygame pymunk numpy

FFmpeg kurulu olmalı:
    Windows: https://ffmpeg.org/download.html → PATH'e ekle
    macOS:   brew install ffmpeg
    Linux:   sudo apt install ffmpeg

Kullanım:
    python dropcounter.py

CONFIG bölümünden metric, sayı ve ayarları değiştir.
"""

import pygame
import pygame.gfxdraw
import pymunk
import pymunk.pygame_util
import numpy as np
import subprocess
import os
import sys
import math
import random
import struct
import wave
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Tuple, Optional

# ============================================================
# CONFIG — Buradan ayarla
# ============================================================
CONFIG = {
    # --- Metric seç: "subs", "likes", "views" ---
    "metric": "subs",

    # --- Top sayısı ---
    "count": 500,

    # --- Hedef video süresi (saniye) - 120-150 arası önerilir ---
    "target_duration": 135,

    # --- Video ayarları ---
    "width": 1080,
    "height": 1920,
    "fps": 60,

    # --- Çıktı ---
    "output": "dropcounter_output.mp4",

    # --- Önizleme (render sırasında ekranda göster, yavaşlatır) ---
    "preview": False,

    # --- Frames klasörü (geçici, otomatik temizlenir) ---
    "frames_dir": "frames_tmp",
}

# ============================================================
# METRIC TANIMLARI
# ============================================================
METRICS = {
    "subs": {
        "label": "Subscribers",
        "title": "1 SUB = 1 BALL DROP",
        "footer": "SUBSCRIBE TO ADD MORE",
        "accent": (255, 77, 109),
        "palette": [
            (255, 77, 109), (255, 107, 53), (255, 149, 88),
            (255, 180, 162), (255, 94, 126), (230, 57, 70),
            (247, 37, 133), (255, 143, 163), (255, 71, 126), (255, 120, 73),
        ],
        "bowl": "shallow",
        "bowl_color": (154, 165, 176),
        "bowl_stroke": (216, 221, 227),
    },
    "likes": {
        "label": "Likes",
        "title": "1 LIKE = 1 BALL DROP",
        "footer": "LIKE TO ADD MORE",
        "accent": (77, 142, 255),
        "palette": [
            (77, 142, 255), (94, 96, 206), (72, 191, 227),
            (86, 207, 225), (116, 0, 184), (105, 48, 195),
            (83, 144, 217), (67, 97, 238), (114, 9, 183), (58, 134, 255),
        ],
        "bowl": "deep",
        "bowl_color": (138, 150, 164),
        "bowl_stroke": (200, 210, 221),
    },
    "views": {
        "label": "Views",
        "title": "1 VIEW = 1 BALL DROP",
        "footer": "KEEP WATCHING",
        "accent": (46, 213, 115),
        "palette": [
            (46, 213, 115), (38, 208, 206), (6, 255, 165),
            (61, 220, 151), (123, 241, 168), (82, 183, 136),
            (64, 145, 108), (149, 213, 178), (116, 198, 157), (183, 228, 199),
        ],
        "bowl": "massive",
        "bowl_color": (138, 152, 144),
        "bowl_stroke": (197, 210, 204),
    },
}

# ============================================================
# BOWL GEOMETRY
# ============================================================
def build_bowl_points(bowl_type: str, W: int, H: int) -> List[Tuple[float, float]]:
    cx = W / 2
    points = []

    if bowl_type == "shallow":
        bowl_y = H * 0.62
        bowl_width = W * 0.82
        wall_height = H * 0.18
        wall_spread = bowl_width * 0.12
        bottom_width = bowl_width * 0.60
        n = 24
        for i in range(n):
            t = i / (n - 1)
            x = cx - bottom_width / 2 + t * bottom_width
            dip = math.sin(t * math.pi) * 6
            points.append((x, bowl_y + dip))
        lb, rb = points[0], points[-1]
        points.insert(0, (lb[0] - wall_spread, lb[1] - wall_height))
        points.append((rb[0] + wall_spread, rb[1] - wall_height))

    elif bowl_type == "deep":
        bowl_y = H * 0.55
        bowl_width = W * 0.78
        bowl_depth = H * 0.28
        wall_height = H * 0.12
        n = 48
        for i in range(n):
            t = i / (n - 1)
            angle = math.pi + t * math.pi
            x = cx + math.cos(angle) * (bowl_width / 2)
            y = bowl_y - math.sin(angle) * bowl_depth
            points.append((x, y))
        lb, rb = points[0], points[-1]
        points.insert(0, (lb[0], lb[1] - wall_height))
        points.append((rb[0], rb[1] - wall_height))

    elif bowl_type == "massive":
        bowl_y = H * 0.58
        bowl_width = W * 0.94
        bowl_depth = H * 0.32
        wall_height = H * 0.18
        n = 56
        for i in range(n):
            t = i / (n - 1)
            angle = math.pi + t * math.pi
            x = cx + math.cos(angle) * (bowl_width / 2)
            y = bowl_y - math.sin(angle) * bowl_depth * (0.6 + 0.4 * math.sin(t * math.pi))
            points.append((x, y))
        lb, rb = points[0], points[-1]
        points.insert(0, (lb[0] - W * 0.01, lb[1] - wall_height))
        points.append((rb[0] + W * 0.01, rb[1] - wall_height))

    return points


def add_bowl_to_space(space: pymunk.Space, points: List[Tuple[float, float]]):
    """Pymunk'a görünmez kalın segmentler ekle (tunneling önleme)."""
    seg_height = 20
    line_thickness = 12
    offset_dist = (seg_height - line_thickness) / 2

    for i in range(len(points) - 1):
        p1 = pymunk.Vec2d(*points[i])
        p2 = pymunk.Vec2d(*points[i + 1])
        delta = p2 - p1
        length = delta.length
        if length < 0.5:
            continue

        # Dışa bakan normal (çanağın iç tarafından uzak)
        normal = pymunk.Vec2d(-delta.y, delta.x).normalized()
        mid = (p1 + p2) / 2
        toward_interior = pymunk.Vec2d(540, 800) - mid  # bowl center approx
        if normal.dot(toward_interior) > 0:
            normal = -normal

        # Segmenti offset'le
        offset_mid = mid + normal * offset_dist

        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = offset_mid
        body.angle = math.atan2(delta.y, delta.x)

        half_w = length / 2 + 4
        half_h = seg_height / 2
        shape = pymunk.Poly(body, [
            (-half_w, -half_h), (half_w, -half_h),
            (half_w, half_h), (-half_w, half_h)
        ])
        shape.friction = 0.3
        shape.elasticity = 0.4
        shape.collision_type = 2
        space.add(body, shape)

    # Joint caps
    for pt in points:
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        body.position = pymunk.Vec2d(*pt)
        shape = pymunk.Circle(body, line_thickness / 2)
        shape.friction = 0.3
        shape.elasticity = 0.4
        shape.collision_type = 2
        space.add(body, shape)


# ============================================================
# AUDIO ENGINE
# ============================================================
@dataclass
class SoundEvent:
    time_sec: float       # when to play (in video time)
    velocity: float       # impact velocity
    radius: float         # ball radius (affects pitch)


class AudioRenderer:
    def __init__(self, fps: int, sample_rate: int = 44100):
        self.fps = fps
        self.sr = sample_rate
        self.events: List[SoundEvent] = []

    def add_event(self, frame: int, velocity: float, radius: float):
        t = frame / self.fps
        self.events.append(SoundEvent(t, velocity, radius))

    def render(self, total_frames: int) -> np.ndarray:
        """Tüm ses eventlerini tek bir stereo audio array'e render et."""
        total_samples = int(total_frames / self.fps * self.sr) + self.sr
        audio = np.zeros(total_samples, dtype=np.float32)

        print(f"  Rendering {len(self.events)} sound events...")

        for ev in self.events:
            vol = min(ev.velocity / 18.0, 1.0) * 0.35
            if vol < 0.02:
                continue

            size_factor = 1.0 - min((ev.radius - 5) / 10.0, 1.0)
            base_freq = 700 + size_factor * 700 + random.uniform(0, 300)

            duration = 0.18
            n_samples = int(duration * self.sr)
            t = np.linspace(0, duration, n_samples, endpoint=False)

            # Two oscillators: triangle + sine harmonic
            osc1 = np.sign(np.sin(2 * np.pi * base_freq * t)) * (
                2 * np.abs(np.sin(2 * np.pi * base_freq * t) * 0.5 + 0.5) - 1
            )  # triangle approx
            osc2 = np.sin(2 * np.pi * base_freq * 2.4 * t)
            signal = (osc1 * 0.6 + osc2 * 0.4)

            # Envelope: fast attack, exponential decay
            attack_samples = max(int(0.002 * self.sr), 1)
            env = np.ones(n_samples)
            env[:attack_samples] = np.linspace(0, 1, attack_samples)
            decay = np.exp(-np.linspace(0, 25, n_samples))
            env *= decay
            signal *= env * vol

            # Place in buffer
            start = int(ev.time_sec * self.sr)
            end = min(start + n_samples, total_samples)
            audio[start:end] += signal[:end - start]

        # Normalize + compress
        peak = np.max(np.abs(audio))
        if peak > 0:
            audio = audio / peak * 0.85

        # Simple soft clip
        audio = np.tanh(audio * 1.2) / 1.2

        return audio

    def save_wav(self, audio: np.ndarray, path: str):
        # Convert to 16-bit PCM stereo
        audio_int = (audio * 32767).astype(np.int16)
        stereo = np.stack([audio_int, audio_int], axis=1)
        with wave.open(path, 'w') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(self.sr)
            wf.writeframes(stereo.tobytes())


# ============================================================
# DRAWING HELPERS
# ============================================================
def draw_smooth_path(surface: pygame.Surface, points: List[Tuple[float, float]],
                     color: Tuple, width: int, offset_x: float = 0, offset_y: float = 0):
    """Quadratic bezier smooth path."""
    if len(points) < 2:
        return

    # Build bezier approximation points
    draw_pts = []
    pts = [(p[0] + offset_x, p[1] + offset_y) for p in points]

    draw_pts.append(pts[0])
    for i in range(1, len(pts) - 1):
        xc = (pts[i][0] + pts[i + 1][0]) / 2
        yc = (pts[i][1] + pts[i + 1][1]) / 2
        # Approximate quadratic bezier with line segments
        steps = max(4, int(math.dist(pts[i - 1], pts[i]) / 8))
        for s in range(steps):
            t = s / steps
            x = (1 - t) ** 2 * pts[i - 1][0] + 2 * (1 - t) * t * pts[i][0] + t ** 2 * xc
            y = (1 - t) ** 2 * pts[i - 1][1] + 2 * (1 - t) * t * pts[i][1] + t ** 2 * yc
            draw_pts.append((x, y))
        draw_pts.append((xc, yc))
    draw_pts.append(pts[-1])

    if len(draw_pts) >= 2:
        pygame.draw.lines(surface, color, False, draw_pts, width)


def draw_bowl(surface: pygame.Surface, points: List[Tuple[float, float]],
              bowl_color: Tuple, bowl_stroke: Tuple):
    """Üç katman: gölge, ana metalik çizgi, highlight."""
    # Shadow
    draw_smooth_path(surface, points, (0, 0, 0, 120), 16, 4, 4)
    # Main
    draw_smooth_path(surface, points, bowl_color, 12)
    # Highlight
    draw_smooth_path(surface, points, (*bowl_stroke, 180), 2, 0, -3)


def draw_text_centered(surface: pygame.Surface, text: str, font: pygame.font.Font,
                       color: Tuple, cx: float, cy: float,
                       glow_color: Optional[Tuple] = None, glow_radius: int = 0):
    """Merkezlenmiş text, opsiyonel glow."""
    if glow_color and glow_radius > 0:
        for r in [glow_radius, glow_radius // 2]:
            glow_surf = font.render(text, True, glow_color)
            glow_rect = glow_surf.get_rect(center=(int(cx), int(cy)))
            # Simple glow: draw slightly offset copies
            for dx, dy in [(-r//2, 0), (r//2, 0), (0, -r//2), (0, r//2), (0, 0)]:
                surface.blit(glow_surf, (glow_rect.x + dx, glow_rect.y + dy))

    txt_surf = font.render(text, True, color)
    txt_rect = txt_surf.get_rect(center=(int(cx), int(cy)))
    surface.blit(txt_surf, txt_rect)


# ============================================================
# TEMPO CALCULATOR
# ============================================================
def compute_drop_schedule(total_balls: int, target_duration: float, fps: int) -> List[int]:
    """
    Her topun kaçıncı frame'de düşeceğini hesapla.
    Başta yavaş, giderek hızlanır.
    Toplam süre target_duration saniyeyi geçmez.
    """
    # Accelerating schedule: drop time = k * i^alpha
    # Solve for k so that last drop is at target_duration * 0.85
    # (kalan %15 final reveal için)
    drop_end = target_duration * 0.85
    total_frames_drop = int(drop_end * fps)

    if total_balls <= 1:
        return [int(fps * 1.0)]

    # Alpha controls acceleration curve: 0 = all at once, 2 = very slow start
    if total_balls <= 30:
        alpha = 1.8
    elif total_balls <= 100:
        alpha = 1.6
    elif total_balls <= 500:
        alpha = 1.4
    elif total_balls <= 2000:
        alpha = 1.2
    else:
        alpha = 1.0

    # Normalize so last ball lands at total_frames_drop
    raw = [((i / (total_balls - 1)) ** alpha) * total_frames_drop
           for i in range(total_balls)]

    # Add 1.5s intro pause before first drop
    intro_frames = int(1.5 * fps)
    schedule = [intro_frames + int(r) for r in raw]

    return schedule


# ============================================================
# MAIN RENDERER
# ============================================================
def render_video(cfg: dict):
    metric_name = cfg["metric"]
    metric = METRICS[metric_name]
    W = cfg["width"]
    H = cfg["height"]
    FPS = cfg["fps"]
    total_balls = cfg["count"]
    target_duration = cfg["target_duration"]
    preview = cfg["preview"]

    # Total frames
    total_frames = int(target_duration * FPS)
    reveal_start_frame = int(target_duration * 0.87 * FPS)
    reveal_duration = int(target_duration * 0.13 * FPS)

    print(f"\n{'='*55}")
    print(f"  Drop Counter Renderer")
    print(f"  Metric  : {metric['label']}")
    print(f"  Count   : {total_balls}")
    print(f"  Duration: {target_duration}s")
    print(f"  FPS     : {FPS}")
    print(f"  Output  : {cfg['output']}")
    print(f"  Total frames: {total_frames:,}")
    print(f"{'='*55}\n")

    # Frames directory
    frames_dir = Path(cfg["frames_dir"])
    frames_dir.mkdir(exist_ok=True)

    # ── Pygame init ──
    if preview:
        pygame.init()
        screen = pygame.display.set_mode((W // 2, H // 2))
        pygame.display.set_caption("Drop Counter — Rendering...")
    else:
        pygame.init()
        screen = None

    surface = pygame.Surface((W, H))

    # ── Fonts ──
    pygame.font.init()
    try:
        font_title = pygame.font.SysFont("Arial", int(H * 0.022), bold=True)
        font_counter = pygame.font.SysFont("Arial", int(H * 0.085), bold=True)
        font_footer = pygame.font.SysFont("Arial", int(H * 0.018), bold=False)
        font_reveal_label = pygame.font.SysFont("Arial", int(H * 0.025), bold=True)
        font_reveal_num = pygame.font.SysFont("Arial", int(H * 0.15), bold=True)
    except:
        font_title = pygame.font.Font(None, int(H * 0.022))
        font_counter = pygame.font.Font(None, int(H * 0.085))
        font_footer = pygame.font.Font(None, int(H * 0.018))
        font_reveal_label = pygame.font.Font(None, int(H * 0.025))
        font_reveal_num = pygame.font.Font(None, int(H * 0.15))

    # ── Physics ──
    space = pymunk.Space()
    space.gravity = (0, 980)
    space.damping = 0.98

    bowl_points = build_bowl_points(metric["bowl"], W, H)
    add_bowl_to_space(space, bowl_points)

    # Invisible walls
    for body_pos, size in [
        ((W / 2, -50), (W * 3, 100)),           # top (catch escaped balls)
        ((-50, H / 2), (100, H * 3)),            # left
        ((W + 50, H / 2), (100, H * 3)),         # right
        ((W / 2, H + 80), (W * 3, 100)),         # floor
    ]:
        b = pymunk.Body(body_type=pymunk.Body.STATIC)
        b.position = body_pos
        s = pymunk.Poly.create_box(b, size)
        s.friction = 0.3
        s.elasticity = 0.3
        space.add(b, s)

    # ── Drop schedule ──
    schedule = compute_drop_schedule(total_balls, target_duration, FPS)
    schedule_set = {}
    for i, frame in enumerate(schedule):
        if frame not in schedule_set:
            schedule_set[frame] = []
        schedule_set[frame].append(i)

    # ── Ball bodies store ──
    ball_bodies = []

    # ── Audio renderer ──
    audio_renderer = AudioRenderer(FPS)

    # ── Collision handler for audio events ──
    collision_data = {"last_frame": -1}
    current_frame_ref = [0]

    def on_collision(arbiter, space, data):
        frame = current_frame_ref[0]
        shapes = arbiter.shapes
        for shape in shapes:
            if hasattr(shape, 'is_ball') and shape.is_ball:
                vel = arbiter.total_impulse.length / max(shape.body.mass, 0.001)
                audio_renderer.add_event(frame, vel / 40.0, shape.radius)
                break
        return True

    space.on_collision(1, 2, post_solve=on_collision)
    space.on_collision(1, 1, post_solve=on_collision)

    # ── Background gradient (precompute) ──
    bg = pygame.Surface((W, H))
    for y in range(H):
        t = y / H
        r = int(10 + t * 8)
        g = int(10 + t * 8)
        b = int(12 + t * 10)
        pygame.draw.line(bg, (r, g, b), (0, y), (W, y))

    # ── RENDER LOOP ──
    print(f"Rendering frames...")
    dropped_count = 0
    counter_pulse = 0.0
    clock = pygame.time.Clock()

    for frame in range(total_frames):
        current_frame_ref[0] = frame

        # Handle preview window events
        if preview:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    print("\nAborted by user.")
                    pygame.quit()
                    return

        # ── Drop balls this frame ──
        if frame in schedule_set:
            for ball_idx in schedule_set[frame]:
                palette = metric["palette"]
                color = palette[ball_idx % len(palette)]

                # Size: smaller for large counts
                if total_balls > 1500:
                    radius = random.uniform(5, 8)
                elif total_balls > 300:
                    radius = random.uniform(7, 12)
                else:
                    radius = random.uniform(9, 15)

                drop_zone = W * 0.4
                x = (W - drop_zone) / 2 + random.uniform(0, drop_zone)
                y = H * 0.18

                mass = math.pi * radius ** 2 * 0.002
                moment = pymunk.moment_for_circle(mass, 0, radius)
                body = pymunk.Body(mass, moment)
                body.position = (x, y)
                body.velocity = (random.uniform(-30, 30), 0)

                shape = pymunk.Circle(body, radius)
                shape.friction = 0.3
                shape.elasticity = 0.5
                shape.collision_type = 1
                shape.is_ball = True
                shape.color_rgb = color

                space.add(body, shape)
                ball_bodies.append((body, shape))
                dropped_count += 1
                counter_pulse = 1.0

        # ── Physics step ──
        # Multiple sub-steps for accuracy (prevents tunneling)
        sub_steps = 3
        dt = 1.0 / FPS / sub_steps
        for _ in range(sub_steps):
            space.step(dt)

        # ── Draw ──
        surface.blit(bg, (0, 0))

        # Balls
        for body, shape in ball_bodies:
            x, y = body.position
            if -50 < x < W + 50 and -50 < y < H + 200:
                ix, iy, ir = int(x), int(y), int(shape.radius)
                pygame.gfxdraw.filled_circle(surface, ix, iy, ir, shape.color_rgb)
                pygame.gfxdraw.aacircle(surface, ix, iy, ir, shape.color_rgb)
                
                # Subtle highlight
                hi_r = max(int(shape.radius * 0.4), 1)
                hi_x = int(x - shape.radius * 0.25)
                hi_y = int(y - shape.radius * 0.25)
                hi_color = tuple(min(255, c + 60) for c in shape.color_rgb)
                pygame.gfxdraw.filled_circle(surface, hi_x, hi_y, hi_r, hi_color)
                pygame.gfxdraw.aacircle(surface, hi_x, hi_y, hi_r, hi_color)

        # Bowl overlay
        draw_bowl(surface, bowl_points, metric["bowl_color"], metric["bowl_stroke"])

        # ── HUD ──
        accent = metric["accent"]
        cx = W // 2

        # Title
        draw_text_centered(surface, metric["title"], font_title,
                           (255, 255, 255, 165), cx, H * 0.06)

        # Counter with pulse + glow
        pulse_scale = 1.0 + counter_pulse * 0.06
        counter_font_size = int(H * 0.085 * pulse_scale)
        try:
            cf = pygame.font.SysFont("Arial", counter_font_size, bold=True)
        except:
            cf = pygame.font.Font(None, counter_font_size)

        counter_text = f"{dropped_count:,}"
        draw_text_centered(surface, counter_text, cf, accent,
                           cx, H * 0.13,
                           glow_color=tuple(min(255, c + 40) for c in accent),
                           glow_radius=12)

        # Footer
        draw_text_centered(surface, metric["footer"], font_footer,
                           (255, 255, 255, 102), cx, H * 0.965)

        # Counter pulse decay
        counter_pulse *= 0.80

        # ── FINAL REVEAL ──
        if frame >= reveal_start_frame:
            t_reveal = (frame - reveal_start_frame) / max(reveal_duration, 1)
            t_reveal = min(t_reveal, 1.0)

            # Ease out back
            ease = 1 + 2.7 * (t_reveal - 1) ** 3 + 1.7 * (t_reveal - 1) ** 2
            opacity = min(t_reveal / 0.4, 1.0)

            overlay = pygame.Surface((W, H), pygame.SRCALPHA)

            # Radial glow background
            for r_size in [W * 0.7, W * 0.5, W * 0.3]:
                pygame.draw.circle(
                    overlay,
                    (*accent, int(15 * opacity)),
                    (cx, H // 2),
                    int(r_size)
                )

            surface.blit(overlay, (0, 0))

            # Big number
            reveal_font_size = int(H * 0.13 * ease)
            if reveal_font_size > 10:
                try:
                    rf = pygame.font.SysFont("Arial", reveal_font_size, bold=True)
                except:
                    rf = pygame.font.Font(None, reveal_font_size)

                rev_surf = rf.render(f"{total_balls:,}", True, accent)
                rev_rect = rev_surf.get_rect(center=(cx, H // 2))

                # Glow layers
                for glow_r in [3, 2, 1]:
                    for dx, dy in [(-glow_r, 0), (glow_r, 0), (0, -glow_r), (0, glow_r)]:
                        glow_surf = rf.render(f"{total_balls:,}", True,
                                              tuple(min(255, c + 30) for c in accent))
                        gs = pygame.Surface(glow_surf.get_size(), pygame.SRCALPHA)
                        gs.blit(glow_surf, (0, 0))
                        gs.set_alpha(int(80 * opacity))
                        surface.blit(gs, (rev_rect.x + dx, rev_rect.y + dy))

                final_surf = pygame.Surface(rev_surf.get_size(), pygame.SRCALPHA)
                final_surf.blit(rev_surf, (0, 0))
                final_surf.set_alpha(int(255 * opacity))
                surface.blit(final_surf, rev_rect)

                # Label below number
                label_y = H // 2 + int(reveal_font_size * 0.65)
                label_surf = font_reveal_label.render(
                    metric["label"].upper(), True, (200, 200, 200)
                )
                label_rect = label_surf.get_rect(center=(cx, label_y))
                ls = pygame.Surface(label_surf.get_size(), pygame.SRCALPHA)
                ls.blit(label_surf, (0, 0))
                ls.set_alpha(int(220 * opacity))
                surface.blit(ls, label_rect)

        # ── Save frame ──
        frame_path = frames_dir / f"frame_{frame:07d}.png"
        pygame.image.save(surface, str(frame_path))

        # ── Preview ──
        if preview and screen:
            small = pygame.transform.scale(surface, (W // 2, H // 2))
            screen.blit(small, (0, 0))
            pygame.display.flip()

        # Progress
        if frame % (FPS * 5) == 0:
            pct = frame / total_frames * 100
            balls_done = dropped_count
            print(f"  Frame {frame:5d}/{total_frames} ({pct:5.1f}%) — Balls: {balls_done}/{total_balls}")

    print(f"\n  All {total_frames} frames rendered.")

    # ── Render Audio ──
    print("\nRendering audio...")
    audio_data = audio_renderer.render(total_frames)
    audio_path = str(frames_dir / "audio.wav")
    audio_renderer.save_wav(audio_data, audio_path)
    print(f"  Audio saved: {audio_path}")

    # ── FFmpeg: frames + audio → mp4 ──
    print("\nEncoding video with FFmpeg...")
    output_path = cfg["output"]

    ffmpeg_cmd_gpu = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-i", str(frames_dir / "frame_%07d.png"),
        "-i", audio_path,
        "-c:v", "h264_nvenc",
        "-preset", "p6",
        "-cq", "18",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ]

    result = subprocess.run(ffmpeg_cmd_gpu, capture_output=True, text=True)
    if result.returncode != 0:
        print("  [GPU Encoder (h264_nvenc) Failed or Not Available, Falling back to CPU (libx264)]")
        ffmpeg_cmd_cpu = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%07d.png"),
            "-i", audio_path,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-movflags", "+faststart",
            output_path
        ]
        result = subprocess.run(ffmpeg_cmd_cpu, capture_output=True, text=True)
        
    if result.returncode != 0:
        print(f"\n[FFmpeg Error]\n{result.stderr}")
        print("\nTrying fallback (no audio)...")
        ffmpeg_cmd_no_audio = [
            "ffmpeg", "-y",
            "-framerate", str(FPS),
            "-i", str(frames_dir / "frame_%07d.png"),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            output_path
        ]
        subprocess.run(ffmpeg_cmd_no_audio, check=True)
    else:
        print(f"  Video encoded successfully.")

    # ── Cleanup ──
    print("\nCleaning up temp frames...")
    for f in frames_dir.glob("*.png"):
        f.unlink()
    try:
        Path(audio_path).unlink()
        frames_dir.rmdir()
    except:
        pass

    if preview:
        pygame.quit()

    # Final stats
    size_mb = Path(output_path).stat().st_size / 1024 / 1024
    print(f"\n{'='*55}")
    print(f"  DONE!")
    print(f"  Output : {output_path}")
    print(f"  Size   : {size_mb:.1f} MB")
    print(f"  Duration: {target_duration}s at {FPS}fps")
    print(f"  Balls  : {total_balls}")
    print(f"{'='*55}\n")


# ============================================================
# ENTRY POINT
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Drop Counter — Shorts Video Renderer")
    parser.add_argument("--metric", choices=["subs", "likes", "views"],
                        default=CONFIG["metric"], help="Metric type")
    parser.add_argument("--count", type=int,
                        default=CONFIG["count"], help="Number of balls")
    parser.add_argument("--duration", type=int,
                        default=CONFIG["target_duration"], help="Target duration in seconds")
    parser.add_argument("--output", type=str,
                        default=CONFIG["output"], help="Output file path")
    parser.add_argument("--no-preview", action="store_true",
                        help="Disable preview window (faster rendering)")
    args = parser.parse_args()

    cfg = CONFIG.copy()
    cfg["metric"] = args.metric
    cfg["count"] = args.count
    cfg["target_duration"] = args.duration
    cfg["output"] = args.output
    cfg["preview"] = not args.no_preview

    render_video(cfg)
