import colorsys
import ctypes
import io
import math
import os
import re
import sys
import threading
import time
import urllib.request
import pygame
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
import syncedlyrics

# --- Spotify Setup ---
C_ID = "3192b60bce0b44ddab655721cace88ee"
C_SEC = "c9ab5c224fca4d32b682a1c67b1c1ab5"

cache_file = os.path.join(os.path.expanduser("~"), ".spotify_cache_app")

sp = spotipy.Spotify(
    auth_manager=SpotifyOAuth(
        client_id=C_ID,
        client_secret=C_SEC,
        redirect_uri="http://127.0.0.1:8888/callback",
        scope="user-read-playback-state user-modify-playback-state user-library-read user-library-modify",
        cache_path=cache_file,
    )
)

# Globaler Status & Locks (Müssen vor den Threads deklariert sein!)
data_lock = threading.Lock()
wake_event = threading.Event()

spotify_state = {
    "device_id": None,
    "device_name": "Kein Gerät",
    "device_type": "Speaker",
    "volume_percent": 50,
    "accent_color": (230, 40, 110),
    "available_devices": [],
    "queue_tracks": [],
    "track_id": "",
    "title": "Warte auf Spotify...",
    "artist": "",
    "cover_url": "",
    "is_playing": False,
    "current_sec": 0.0,
    "duration_sec": 1,
    "shuffle_state": False,
    "repeat_state": "off",
    "is_saved": False,
    "new_data_ready": False,
    "lyrics_lines": [],
    "reset_scroll": False,
}

# =====================================================================
# NEU: INTEGRIERTER CLOUD-CONNECT LAUTSPRECHER WITH CALLBACK (README)
# =====================================================================
from librespot.core import Session
import logging

# 1. Debug-Modus aktivieren laut README (zeigt uns genau, was klemmt!)
logging.basicConfig(level=logging.DEBUG)

connect_session = None

# Callback-Funktion fängt den blockierenden Link ab, damit das Terminal weiterläuft
def auth_url_callback(url):
    print(f"\n>>> [INFO] Spotify verlangt einmalige Autorisierung. Link: {url}\n")

def starte_globalen_connect_lautsprecher():
    global connect_session
    try:
        print(">>> Versuche Verbindung zur Spotify-Cloud aufzubauen...")
        
        # Offizielle Syntax aus deinem GitHub-README mit Callback-Schutz:
        # success_page sorgt dafür, dass die Session danach sauber schließt
        success_page = "<html><body><h1>Erfolgreich verbunden!</h1><p>Du kannst das Fenster schließen.</p></body></html>"
        
        connect_session = Session.Builder() \
            .oauth(auth_url_callback, success_page) \
            .create()
            
        print(">>> [ERFOLG] Echter Spotify Cloud-Lautsprecher im RAM aktiv!")
        
        while True:
            time.sleep(1)
    except Exception as e:
        print(f">>>> Fehler beim Starten des Cloud-Lautsprechers: {e}")

# Startet den echten Netzwerk-Dienst isoliert im Hintergrund (Daemon)
speaker_thread = threading.Thread(target=starte_globalen_connect_lautsprecher, daemon=True)
speaker_thread.start()

# Der Synchronisator für dein 1360-Zeilen-Wörterbuch (Lyrics & Cover)
def cloud_sync_worker():
    while True:
        try:
            status = sp.current_playback()
            if status and status.get("item"):
                item = status["item"]
                with data_lock:
                    spotify_state["track_id"] = item["id"]
                    spotify_state["title"] = item["name"]
                    spotify_state["artist"] = item["artists"]["name"]
                    spotify_state["cover_url"] = item["album"]["images"]["url"]
                    spotify_state["is_playing"] = status["is_playing"]
                    spotify_state["duration_sec"] = item["duration_ms"] / 1000.0
                    spotify_state["current_sec"] = status["progress_ms"] / 1000.0
                    spotify_state["new_data_ready"] = True
        except Exception:
            pass
        time.sleep(0.8)

threading.Thread(target=cloud_sync_worker, daemon=True).start()
# =====================================================================


# --- Fenster-Setup ---
pygame.init()
BASE_WIDTH = 380
BASE_HEIGHT = 550

EXPANDED_WIDTH = 1180
EXPANDED_HEIGHT = 620

current_w = BASE_WIDTH
current_h = BASE_HEIGHT

screen = pygame.display.set_mode((current_w, current_h), pygame.RESIZABLE)
pygame.display.set_caption("Spotify Controller")
clock = pygame.time.Clock()

# Schriften
font_title = pygame.font.SysFont("segoeui", 20, bold=True)
font_title_large = pygame.font.SysFont("segoeui", 25, bold=True)
font_title_fs = pygame.font.SysFont("segoeui", 32, bold=True)
font_artist = pygame.font.SysFont("segoeui", 15)
font_artist_large = pygame.font.SysFont("segoeui", 17)
font_artist_fs = pygame.font.SysFont("segoeui", 22)

font_device = pygame.font.SysFont("segoeui", 13, bold=True)
font_device_list = pygame.font.SysFont("segoeui", 14, bold=True)
font_time = pygame.font.SysFont("segoeui", 12)
font_time_large = pygame.font.SysFont("segoeui", 14)
font_time_fs = pygame.font.SysFont("segoeui", 16)
font_repeat_one = pygame.font.SysFont("segoeui", 10, bold=True)

# Lyrics Fonts
font_lyric_active = pygame.font.SysFont("segoeui", 26, bold=True)
font_lyric_idle = pygame.font.SysFont("segoeuisemibold,segoeui", 19, bold=False)

font_display_lyric_active = pygame.font.SysFont("segoeui", 36, bold=True)
font_display_lyric_idle = pygame.font.SysFont("segoeuisemibold,segoeui", 24, bold=False)

font_queue_header = pygame.font.SysFont("segoeui", 18, bold=True)
font_queue_track = pygame.font.SysFont("segoeui", 15, bold=True)
font_queue_artist = pygame.font.SysFont("segoeui", 13)

# Caches
lyrics_cache = {}
cover_cache = {}
rendered_lyrics_cache = {}

# Globaler Status
data_lock = threading.Lock()
wake_event = threading.Event()

spotify_state = {
    "device_id": None,
    "device_name": "Kein Gerät",
    "device_type": "Speaker",
    "volume_percent": 50,
    "accent_color": (230, 40, 110),
    "available_devices": [],
    "queue_tracks": [],
    "track_id": "",
    "title": "Warte auf Spotify...",
    "artist": "",
    "cover_url": "",
    "is_playing": False,
    "current_sec": 0.0,
    "duration_sec": 1,
    "shuffle_state": False,
    "repeat_state": "off",
    "is_saved": False,
    "new_data_ready": False,
    "lyrics_lines": [],
    "reset_scroll": False,
}

show_lyrics = False
show_device_menu = False
show_queue = False
display_mode = False

lyric_scroll_y = 40.0
user_scrolled_time = 0.0
last_seek_time = 0.0
last_mode_time = 0.0
last_play_time = 0.0
dragging_volume = False
last_vol_api_time = 0.0
last_mouse_move_time = 0.0
fs_controls_alpha = 0.0


# --- Farbanalyse & Cover-Blur-Generierung ---
def extract_accent_color(pil_img):
    try:
        small = pil_img.resize((48, 48))
        quant = small.quantize(colors=4, method=2)
        palette = quant.getpalette()[:12]
        r, g, b = palette[0], palette[1], palette[2]
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        if lum < 75:
            r = min(255, int(r * 1.8) + 55)
            g = min(255, int(g * 1.8) + 55)
            b = min(255, int(b * 1.8) + 55)
        elif lum > 220:
            r, g, b = int(r * 0.8), int(g * 0.8), int(g * 0.8)
        return (r, g, b)
    except Exception:
        return (230, 40, 110)


def clean_song_title(title):
    t = re.sub(r"-\s*.*remaster.*", "", title, flags=re.IGNORECASE)
    t = re.sub(r"-\s*.*version.*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\(.*?remaster.*?\)", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\[.*?remaster.*?\]", "", t, flags=re.IGNORECASE)
    return t.strip()


def parse_lrc(lrc_text):
    lines = []
    if not lrc_text:
        return lines
    for line in lrc_text.splitlines():
        if line.startswith("[") and "]" in line:
            parts = line.split("]", 1)
            time_tag = parts[0][1:]
            text = parts[1].strip() if len(parts) > 1 else ""
            try:
                m, s = time_tag.split(":")
                ms = int(float(m) * 60000 + float(s) * 1000)
                if text:
                    lines.append((ms, text))
            except Exception:
                continue
    lines.sort(key=lambda x: x[0])
    return lines


def process_cover_images(url, target_w, target_h):
    fallback_cover = pygame.Surface((220, 220), pygame.SRCALPHA).convert_alpha()
    pygame.draw.rect(fallback_cover, (45, 45, 45), (0, 0, 220, 220), border_radius=16)

    fallback_fs_cover = pygame.Surface((480, 480), pygame.SRCALPHA).convert_alpha()
    pygame.draw.rect(fallback_fs_cover, (45, 45, 45), (0, 0, 480, 480), border_radius=28)

    fallback_bg = pygame.Surface((int(target_w * 1.3), int(target_h * 1.3))).convert()
    fallback_bg.fill((18, 18, 18))

    if not url:
        return fallback_cover, fallback_fs_cover, fallback_bg, (230, 40, 110)

    cache_key = (url, target_w, target_h)
    if cache_key in cover_cache:
        return cover_cache[cache_key]

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SpotifyController/1.0"})
        with urllib.request.urlopen(req, timeout=3) as response:
            raw_data = response.read()

        base_pil = Image.open(io.BytesIO(raw_data)).convert("RGBA")
        accent = extract_accent_color(base_pil)

        small_size = (220, 220)
        c_small = base_pil.resize(small_size, Image.Resampling.BILINEAR)
        mask = Image.new("L", small_size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0) + small_size, radius=16, fill=255)
        c_small.putalpha(mask)
        cover_surf = pygame.image.frombytes(c_small.tobytes(), small_size, "RGBA").convert_alpha()

        fs_size = (480, 480)
        c_fs = base_pil.resize(fs_size, Image.Resampling.BILINEAR)
        mask_fs = Image.new("L", fs_size, 0)
        draw_fs = ImageDraw.Draw(mask_fs)
        draw_fs.rounded_rectangle((0, 0) + fs_size, radius=28, fill=255)
        c_fs.putalpha(mask_fs)
        cover_fs_surf = pygame.image.frombytes(c_fs.tobytes(), fs_size, "RGBA").convert_alpha()

        # Echter starker Cover-Blur Hintergrund
        bg_w, bg_h = int(target_w * 1.3), int(target_h * 1.3)
        bg_pil = base_pil.resize((max(80, bg_w // 12), max(80, bg_h // 12)), Image.Resampling.BILINEAR)
        bg_pil = bg_pil.filter(ImageFilter.GaussianBlur(radius=10))
        bg_pil = bg_pil.resize((bg_w, bg_h), Image.Resampling.BILINEAR)
        bg_pil = bg_pil.filter(ImageFilter.GaussianBlur(radius=18))
        bg_pil = ImageEnhance.Brightness(bg_pil).enhance(0.40)
        bg_surf = pygame.image.frombytes(bg_pil.convert("RGB").tobytes(), (bg_w, bg_h), "RGB").convert()

        res = (cover_surf, cover_fs_surf, bg_surf, accent)
        cover_cache[cache_key] = res
        return res
    except Exception:
        return fallback_cover, fallback_fs_cover, fallback_bg, (230, 40, 110)


def create_song_card(title, artist, cover_surf, cover_large_surf, is_fs=False):
    t_str = title[:24] + "..." if len(title) > 27 else title
    a_str = artist[:30] + "..." if len(artist) > 33 else artist

    if is_fs:
        fs_sub = pygame.Surface((560, 640), pygame.SRCALPHA).convert_alpha()
        if cover_large_surf:
            fs_sub.blit(cover_large_surf, (40, 20))

        t_shadow = font_title_fs.render(t_str, True, (0, 0, 0))
        t_rend = font_title_fs.render(t_str, True, (255, 255, 255))
        a_rend = font_artist_fs.render(a_str, True, (215, 215, 220))

        cx_t = 40 + (480 - t_rend.get_width()) // 2
        cx_a = 40 + (480 - a_rend.get_width()) // 2

        fs_sub.blit(t_shadow, (cx_t + 1, 515))
        fs_sub.blit(t_rend, (cx_t, 514))
        fs_sub.blit(a_rend, (cx_a, 558))
        return fs_sub
    else:
        std_sub = pygame.Surface((380, 360), pygame.SRCALPHA).convert_alpha()
        if cover_surf:
            std_sub.blit(cover_surf, ((BASE_WIDTH - 220) // 2, 25))

        t_shadow = font_title.render(t_str, True, (0, 0, 0))
        t_rend = font_title.render(t_str, True, (255, 255, 255))
        a_rend = font_artist.render(a_str, True, (200, 200, 205))

        cx_t = (BASE_WIDTH - t_rend.get_width()) // 2
        cx_a = (BASE_WIDTH - a_rend.get_width()) // 2

        std_sub.blit(t_shadow, (cx_t + 1, 266))
        std_sub.blit(t_rend, (cx_t, 265))
        std_sub.blit(a_rend, (cx_a, 296))
        return std_sub


# --- Vektorielle Hi-Res Icons ---
def draw_vector_icon(surface, icon_type, rect, color, filled=False):
    scale = 4
    w, h = rect.w * scale, rect.h * scale
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    if icon_type == "shuffle":
        pygame.draw.line(surf, color, (6 * scale, 22 * scale), (22 * scale, 10 * scale), int(2.2 * scale))
        pygame.draw.line(surf, color, (6 * scale, 10 * scale), (12 * scale, 14.5 * scale), int(2.2 * scale))
        pygame.draw.line(surf, color, (16 * scale, 17.5 * scale), (22 * scale, 22 * scale), int(2.2 * scale))
        pygame.draw.polygon(surf, color, [(20 * scale, 6 * scale), (27 * scale, 10 * scale), (20 * scale, 14 * scale)])
        pygame.draw.polygon(surf, color, [(20 * scale, 18 * scale), (27 * scale, 22 * scale), (20 * scale, 26 * scale)])

    elif icon_type in ("repeat", "repeat_one"):
        pygame.draw.line(surf, color, (10 * scale, 9 * scale), (22 * scale, 9 * scale), int(2.2 * scale))
        pygame.draw.arc(surf, color, (5 * scale, 9 * scale, 10 * scale, 14 * scale), math.pi / 2, math.pi * 1.5, int(2.2 * scale))
        pygame.draw.polygon(surf, color, [(20 * scale, 5 * scale), (27 * scale, 9 * scale), (20 * scale, 13 * scale)])

        pygame.draw.line(surf, color, (10 * scale, 23 * scale), (22 * scale, 23 * scale), int(2.2 * scale))
        pygame.draw.arc(surf, color, (17 * scale, 9 * scale, 10 * scale, 14 * scale), -math.pi / 2, math.pi / 2, int(2.2 * scale))
        pygame.draw.polygon(surf, color, [(12 * scale, 19 * scale), (5 * scale, 23 * scale), (12 * scale, 27 * scale)])

    elif icon_type == "heart":
        pts = []
        for t in range(0, 360, 6):
            rad = math.radians(t)
            x = 16 * (math.sin(rad) ** 3)
            y = -(13 * math.cos(rad) - 5 * math.cos(2 * rad) - 2 * math.cos(3 * rad) - math.cos(4 * rad))
            pts.append((w / 2 + x * scale * 0.55, h / 2 + y * scale * 0.55 + 2 * scale))
        if filled:
            pygame.draw.polygon(surf, color, pts)
        else:
            pygame.draw.polygon(surf, color, pts, int(2.0 * scale))

    elif icon_type == "mic":
        pygame.draw.rect(surf, color, (12 * scale, 5 * scale, 8 * scale, 13 * scale), border_radius=int(4 * scale))
        pygame.draw.arc(surf, color, (9 * scale, 9 * scale, 14 * scale, 12 * scale), math.pi, 0, int(2.0 * scale))
        pygame.draw.line(surf, color, (16 * scale, 21 * scale), (16 * scale, 26 * scale), int(2.0 * scale))
        pygame.draw.line(surf, color, (12 * scale, 26 * scale), (20 * scale, 26 * scale), int(2.0 * scale))

    elif icon_type == "vol_low":
        pygame.draw.polygon(surf, color, [(7 * scale, 12 * scale), (11 * scale, 12 * scale), (15 * scale, 8 * scale), (15 * scale, 24 * scale), (11 * scale, 20 * scale), (7 * scale, 20 * scale)])
        pygame.draw.arc(surf, color, (13 * scale, 11 * scale, 8 * scale, 10 * scale), -math.pi / 3, math.pi / 3, int(1.8 * scale))

    elif icon_type == "vol_high":
        pygame.draw.polygon(surf, color, [(6 * scale, 12 * scale), (10 * scale, 12 * scale), (14 * scale, 8 * scale), (14 * scale, 24 * scale), (10 * scale, 20 * scale), (6 * scale, 20 * scale)])
        pygame.draw.arc(surf, color, (12 * scale, 11 * scale, 8 * scale, 10 * scale), -math.pi / 3, math.pi / 3, int(1.8 * scale))
        pygame.draw.arc(surf, color, (13 * scale, 7 * scale, 13 * scale, 18 * scale), -math.pi / 3, math.pi / 3, int(1.8 * scale))

    scaled = pygame.transform.smoothscale(surf, (rect.w, rect.h))
    surface.blit(scaled, (rect.x, rect.y))

    if icon_type == "repeat_one":
        one_rend = font_repeat_one.render("1", True, color)
        surface.blit(one_rend, (rect.centerx - one_rend.get_width() // 2, rect.centery - one_rend.get_height() // 2 - 1))


def draw_custom_buttons(surface, is_playing, p_btn_prev, p_btn_play, p_btn_next):
    scale = 4

    prev_surf = pygame.Surface((32 * scale, 32 * scale), pygame.SRCALPHA)
    pygame.draw.polygon(prev_surf, (255, 255, 255), [
        (24 * scale, 8 * scale), (10 * scale, 16 * scale), (24 * scale, 24 * scale)
    ])
    pygame.draw.rect(prev_surf, (255, 255, 255), (8 * scale, 8 * scale, 3 * scale, 16 * scale), border_radius=int(1.5 * scale))
    surface.blit(pygame.transform.smoothscale(prev_surf, (32, 32)), (p_btn_prev.x + 4, p_btn_prev.y + 4))

    next_surf = pygame.Surface((32 * scale, 32 * scale), pygame.SRCALPHA)
    pygame.draw.polygon(next_surf, (255, 255, 255), [
        (8 * scale, 8 * scale), (22 * scale, 16 * scale), (8 * scale, 24 * scale)
    ])
    pygame.draw.rect(next_surf, (255, 255, 255), (21 * scale, 8 * scale, 3 * scale, 16 * scale), border_radius=int(1.5 * scale))
    surface.blit(pygame.transform.smoothscale(next_surf, (32, 32)), (p_btn_next.x + 4, p_btn_next.y + 4))

    play_surf = pygame.Surface((52 * scale, 52 * scale), pygame.SRCALPHA)
    pygame.draw.circle(play_surf, (255, 255, 255), (26 * scale, 26 * scale), 25 * scale)
    if is_playing:
        pygame.draw.rect(play_surf, (0, 0, 0), (18 * scale, 15 * scale, 5 * scale, 20 * scale), border_radius=int(2 * scale))
        pygame.draw.rect(play_surf, (0, 0, 0), (29 * scale, 15 * scale, 5 * scale, 20 * scale), border_radius=int(2 * scale))
    else:
        pygame.draw.polygon(play_surf, (0, 0, 0), [
            (20 * scale, 14 * scale), (37 * scale, 25 * scale), (20 * scale, 36 * scale)
        ])
    surface.blit(pygame.transform.smoothscale(play_surf, (52, 52)), (p_btn_play.x, p_btn_play.y))


# --- Lyrics-Abruf ---
def fetch_lyrics_thread(query):
    if query in lyrics_cache:
        with data_lock:
            spotify_state["lyrics_lines"] = lyrics_cache[query]
            spotify_state["reset_scroll"] = True
        return

    parsed = []
    try:
        lrc = syncedlyrics.search(query)
        if lrc:
            parsed = parse_lrc(lrc)
    except Exception:
        parsed = []

    lyrics_cache[query] = parsed
    with data_lock:
        spotify_state["lyrics_lines"] = parsed
        spotify_state["reset_scroll"] = True


def async_image_processor(url, title, artist, target_w, target_h):
    new_cover, new_fs_cover, new_bg, new_accent = process_cover_images(url, target_w, target_h)
    std_card = create_song_card(title, artist, new_cover, None, is_fs=False)
    fs_card = create_song_card(title, artist, None, new_fs_cover, is_fs=True)
    
    with data_lock:
        spotify_state["pending_card_std"] = std_card
        spotify_state["pending_card_fs"] = fs_card
        spotify_state["pending_bg"] = new_bg
        spotify_state["accent_color"] = new_accent
        spotify_state["image_ready"] = True


def refresh_devices_async():
    def run():
        try:
            dev_res = sp.devices()
            with data_lock:
                spotify_state["available_devices"] = dev_res.get("devices", [])
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def fetch_queue_async():
    def run():
        try:
            q_res = sp.queue()
            tracks = []
            if q_res and "queue" in q_res:
                for item in q_res["queue"][:5]:
                    name = item.get("name", "")
                    artist = ", ".join([a["name"] for a in item.get("artists", [])])
                    tracks.append((name, artist))
            with data_lock:
                spotify_state["queue_tracks"] = tracks
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def spotify_worker():
    last_id = ""

    while True:
        try:
            playback = sp.current_playback()
            sleep_duration = 0.8

            if playback and playback.get("item"):
                item = playback["item"]
                t_id = item.get("id", "")
                dev = playback.get("device", {})
                dev_id = dev.get("id")
                dev_name = dev.get("name", "Unbekannt")
                dev_type = dev.get("type", "Speaker")
                dev_vol = dev.get("volume_percent", 50)
                is_new = t_id != last_id

                is_saved = False
                if is_new and t_id:
                    try:
                        saved_check = sp.current_user_saved_tracks_contains(tracks=[t_id])
                        is_saved = saved_check[0] if saved_check else False
                    except Exception:
                        pass
                    fetch_queue_async()

                with data_lock:
                    if dev_id:
                        spotify_state["device_id"] = dev_id
                        spotify_state["device_name"] = dev_name
                        spotify_state["device_type"] = dev_type
                        if not dragging_volume:
                            spotify_state["volume_percent"] = dev_vol

                    if is_new:
                        last_id = t_id
                        raw_title = item["name"]
                        title = clean_song_title(raw_title)
                        artist = ", ".join([a["name"] for a in item["artists"]])
                        images = item["album"]["images"]
                        cover_url = images[0]["url"] if images else ""

                        spotify_state["track_id"] = t_id
                        spotify_state["title"] = raw_title
                        spotify_state["artist"] = artist
                        spotify_state["cover_url"] = cover_url
                        spotify_state["duration_sec"] = max(1, item["duration_ms"] // 1000)
                        spotify_state["current_sec"] = float(playback["progress_ms"] // 1000)
                        spotify_state["is_saved"] = is_saved
                        spotify_state["lyrics_lines"] = []
                        spotify_state["reset_scroll"] = True

                        info = pygame.display.Info()
                        tw = info.current_w if display_mode else EXPANDED_WIDTH
                        th = info.current_h if display_mode else EXPANDED_HEIGHT

                        threading.Thread(
                            target=async_image_processor,
                            args=(cover_url, raw_title, artist, tw, th),
                            daemon=True
                        ).start()

                        q = f"{title} {artist}"
                        if q in lyrics_cache:
                            spotify_state["lyrics_lines"] = lyrics_cache[q]
                            spotify_state["reset_scroll"] = True
                        else:
                            threading.Thread(
                                target=fetch_lyrics_thread,
                                args=(q,),
                                daemon=True,
                            ).start()

                    if time.time() - last_play_time > 0.6:
                        spotify_state["is_playing"] = playback["is_playing"]

                    if time.time() - last_seek_time > 0.8:
                        server_sec = playback["progress_ms"] // 1000
                        if abs(spotify_state["current_sec"] - server_sec) >= 2:
                            spotify_state["current_sec"] = float(server_sec)

                    if time.time() - last_mode_time > 0.8:
                        spotify_state["shuffle_state"] = playback.get("shuffle_state", False)
                        spotify_state["repeat_state"] = playback.get("repeat_state", "off")

                rem_ms = item["duration_ms"] - playback["progress_ms"]
                if playback.get("is_playing", False):
                    sleep_duration = 0.3 if rem_ms < 2500 else 0.8
                else:
                    sleep_duration = 1.5
            else:
                with data_lock:
                    if time.time() - last_play_time > 0.6:
                        spotify_state["is_playing"] = False
                sleep_duration = 1.5

            wake_event.wait(timeout=sleep_duration)
            wake_event.clear()

        except SpotifyException as se:
            if se.http_status == 429:
                retry_after = int(se.headers.get("Retry-After", 60))
                wake_event.wait(timeout=retry_after + 1)
                wake_event.clear()
            else:
                wake_event.wait(timeout=1.5)
                wake_event.clear()
        except Exception:
            wake_event.wait(timeout=1.5)
            wake_event.clear()


def get_active_device_or_fallback():
    with data_lock:
        if spotify_state["device_id"]:
            return spotify_state["device_id"]
        devs = spotify_state["available_devices"]
        if devs:
            return devs[0]["id"]
    return None


def safe_api_call(target, *args, **kwargs):
    def run():
        if "device_id" not in kwargs or kwargs["device_id"] is None:
            kwargs["device_id"] = get_active_device_or_fallback()
        try:
            target(*args, **kwargs)
            time.sleep(0.04)
            wake_event.set()
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


# --- Hitboxen Normalmodus ---
progress_bar = pygame.Rect(35, 372, 310, 5)

btn_mode = pygame.Rect(35, 420, 36, 36)
btn_prev = pygame.Rect(100, 418, 40, 40)
btn_play = pygame.Rect(164, 422, 52, 52)
btn_next = pygame.Rect(240, 418, 40, 40)
btn_like = pygame.Rect(310, 420, 36, 36)

btn_lyrics = pygame.Rect(240, 335, 32, 28)
btn_device_bar = pygame.Rect(70, 337, 160, 24)

volume_bar = pygame.Rect(95, 495, 190, 4)
volume_hitbox = pygame.Rect(
    volume_bar.x - 25, volume_bar.y - 15, volume_bar.w + 50, volume_bar.h + 30
)

current_bg = pygame.Surface((int(EXPANDED_WIDTH * 1.3), int(EXPANDED_HEIGHT * 1.3))).convert()
current_bg.fill((18, 18, 18))

current_card_std = create_song_card("Warte auf Spotify...", "", None, None, is_fs=False)
current_card_fs = create_song_card("Warte auf Spotify...", "", None, None, is_fs=True)
next_card_std = None
next_card_fs = None
next_bg = None

crossfade_alpha = 255.0
CROSSFADE_SPEED = 24.0

threading.Thread(target=spotify_worker, daemon=True).start()

running = True
last_frame_time = time.time()

while running:
    current_time = time.time()
    dt_sec = max(0.001, min(0.05, current_time - last_frame_time))
    last_frame_time = current_time

    cur_screen_w, cur_screen_h = screen.get_size()

    # Hitboxen für Fullscreen-Steuerung
    fs_center_x = cur_screen_w // 2
    fs_ctrl_y = cur_screen_h - 110
    fs_btn_play = pygame.Rect(fs_center_x - 26, fs_ctrl_y - 8, 52, 52)
    fs_btn_prev = pygame.Rect(fs_center_x - 86, fs_ctrl_y - 2, 40, 40)
    fs_btn_next = pygame.Rect(fs_center_x + 46, fs_ctrl_y - 2, 40, 40)
    fs_btn_mode = pygame.Rect(fs_center_x - 146, fs_ctrl_y, 36, 36)
    fs_btn_like = pygame.Rect(fs_center_x + 110, fs_ctrl_y, 36, 36)
    
    fs_volume_bar = pygame.Rect(cur_screen_w - 240, fs_ctrl_y + 16, 140, 4)
    fs_volume_hitbox = pygame.Rect(fs_volume_bar.x - 25, fs_volume_bar.y - 15, fs_volume_bar.w + 50, fs_volume_bar.h + 30)

    # Grenzen für den Lyrics-Bereich
    if display_mode:
        lyrics_area_rect = pygame.Rect(580, 20, max(300, cur_screen_w - 640), max(100, cur_screen_h - 160))
    else:
        lyrics_area_rect = pygame.Rect(400, 25, max(100, cur_screen_w - 420), max(100, cur_screen_h - 50))

    with data_lock:
        if spotify_state["is_playing"] and time.time() - last_seek_time > 0.2:
            spotify_state["current_sec"] = min(
                float(spotify_state["duration_sec"]), spotify_state["current_sec"] + dt_sec
            )

        cur_sec_int = int(spotify_state["current_sec"])
        dur_sec_int = max(1, int(spotify_state["duration_sec"]))
        is_playing = spotify_state["is_playing"]
        progress_ms = int(spotify_state["current_sec"] * 1000)

        if spotify_state.get("image_ready", False):
            spotify_state["image_ready"] = False
            next_card_std = spotify_state["pending_card_std"]
            next_card_fs = spotify_state["pending_card_fs"]
            next_bg = spotify_state["pending_bg"]
            crossfade_alpha = 0.0

        if spotify_state.get("reset_scroll", False):
            spotify_state["reset_scroll"] = False
            lyric_scroll_y = 40.0 if display_mode else 25.0

        shuffle_on = spotify_state["shuffle_state"]
        repeat_mode = spotify_state["repeat_state"]
        is_saved = spotify_state["is_saved"]
        lyrics_lines = list(spotify_state["lyrics_lines"])
        queue_tracks = list(spotify_state["queue_tracks"])
        device_name = spotify_state["device_name"]
        device_type = spotify_state["device_type"]
        current_dev_id = spotify_state["device_id"]
        avail_devices = list(spotify_state["available_devices"])
        vol_pct = spotify_state["volume_percent"]
        accent = spotify_state["accent_color"]

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.VIDEORESIZE:
            cur_screen_w, cur_screen_h = event.w, event.h
            if spotify_state["cover_url"]:
                threading.Thread(
                    target=async_image_processor,
                    args=(spotify_state["cover_url"], spotify_state["title"], spotify_state["artist"], cur_screen_w, cur_screen_h),
                    daemon=True
                ).start()

        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_TAB, pygame.K_d):
                display_mode = not display_mode
                show_device_menu = False
                show_queue = False
                user_scrolled_time = 0.0
                
                try:
                    hwnd = pygame.display.get_wm_info()['window']
                    user32 = ctypes.windll.user32
                    
                    if display_mode:
                        mon_w = user32.GetSystemMetrics(0)
                        mon_h = user32.GetSystemMetrics(1)
                        
                        GWL_STYLE = -16
                        WS_POPUP = 0x80000000
                        WS_VISIBLE = 0x10000000
                        user32.SetWindowLongW(hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE)
                        
                        SWP_SHOWWINDOW = 0x0040
                        user32.SetWindowPos(hwnd, 0, 0, 0, mon_w, mon_h, SWP_SHOWWINDOW)
                        screen = pygame.display.set_mode((mon_w, mon_h), pygame.NOFRAME)
                    else:
                        GWL_STYLE = -16
                        WS_OVERLAPPEDWINDOW = 0x00CF0000
                        WS_VISIBLE = 0x10000000
                        user32.SetWindowLongW(hwnd, GWL_STYLE, WS_OVERLAPPEDWINDOW | WS_VISIBLE)
                        
                        target_w = EXPANDED_WIDTH if show_lyrics else BASE_WIDTH
                        screen = pygame.display.set_mode((target_w, BASE_HEIGHT), pygame.RESIZABLE)
                        
                        mon_w = user32.GetSystemMetrics(0)
                        mon_h = user32.GetSystemMetrics(1)
                        user32.SetWindowPos(hwnd, 0, (mon_w - target_w) // 2, (mon_h - BASE_HEIGHT) // 2, target_w, BASE_HEIGHT, 0x0040)
                except Exception:
                    pass

                cur_screen_w, cur_screen_h = screen.get_size()

                if spotify_state["cover_url"]:
                    threading.Thread(
                        target=async_image_processor,
                        args=(spotify_state["cover_url"], spotify_state["title"], spotify_state["artist"], cur_screen_w, cur_screen_h),
                        daemon=True
                    ).start()

            elif event.key == pygame.K_q:
                show_queue = not show_queue
                if show_queue:
                    fetch_queue_async()

            elif event.key == pygame.K_SPACE:
                new_playing = not is_playing
                with data_lock:
                    spotify_state["is_playing"] = new_playing
                    last_play_time = time.time()
                if new_playing:
                    safe_api_call(sp.start_playback, device_id=current_dev_id)
                else:
                    safe_api_call(sp.pause_playback, device_id=current_dev_id)

            elif event.key == pygame.K_RIGHT:
                safe_api_call(sp.next_track, device_id=current_dev_id)

            elif event.key == pygame.K_LEFT:
                def do_prev():
                    dev = get_active_device_or_fallback()
                    try:
                        sp.previous_track(device_id=dev)
                    except Exception:
                        try:
                            sp.seek_track(0, device_id=dev)
                        except Exception:
                            pass
                    with data_lock:
                        spotify_state["reset_scroll"] = True
                    wake_event.set()
                threading.Thread(target=do_prev, daemon=True).start()

        elif event.type == pygame.MOUSEWHEEL and (show_lyrics or display_mode):
            step = 76 if display_mode else 54
            lyric_scroll_y += event.y * step
            user_scrolled_time = time.time()

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if dragging_volume:
                dragging_volume = False
                safe_api_call(sp.volume, vol_pct, device_id=current_dev_id)

        elif event.type == pygame.MOUSEMOTION:
            last_mouse_move_time = time.time()
            mx = event.pos[0]
            
            if dragging_volume:
                active_vbar = fs_volume_bar if display_mode else volume_bar
                rel_x = mx - active_vbar.x
                new_pct = int(max(0.0, min(1.0, rel_x / active_vbar.w)) * 100)
                with data_lock:
                    spotify_state["volume_percent"] = new_pct

                if time.time() - last_vol_api_time > 0.15:
                    last_vol_api_time = time.time()
                    safe_api_call(sp.volume, new_pct, device_id=current_dev_id)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            last_mouse_move_time = time.time()

            if show_device_menu and not display_mode:
                popup_w = 320
                item_h = 34
                header_h = 38
                max_h = 240
                total_content_h = header_h + len(avail_devices) * item_h
                popup_h = min(max_h, max(80, total_content_h + 10))
                popup_x = (BASE_WIDTH - popup_w) // 2
                popup_y = max(10, btn_device_bar.y - popup_h - 10)

                item_clicked = False
                for idx, d in enumerate(avail_devices):
                    y_pos = header_h + idx * item_h
                    if y_pos + item_h > popup_h:
                        break
                    item_rect = pygame.Rect(
                        popup_x + 6, popup_y + y_pos, popup_w - 12, item_h - 4
                    )
                    if item_rect.collidepoint(mx, my):
                        safe_api_call(
                            sp.transfer_playback,
                            device_id=d["id"],
                            force_play=True,
                        )
                        show_device_menu = False
                        item_clicked = True
                        break

                if not item_clicked and not pygame.Rect(
                    popup_x, popup_y, popup_w, popup_h
                ).collidepoint(mx, my):
                    show_device_menu = False
                continue

            # Klick-to-Seek auf der Fortschrittsleiste
            if display_mode:
                click_prog_rect = pygame.Rect(60, cur_screen_h - 55, cur_screen_w - 120, 25)
                bar_x = 60
                bar_w = cur_screen_w - 120
            else:
                click_prog_rect = pygame.Rect(35, 362, 310, 25)
                bar_x = 35
                bar_w = 310

            if click_prog_rect.collidepoint(mx, my):
                rel_x = mx - bar_x
                pct = max(0.0, min(1.0, rel_x / bar_w))
                seek_sec = int(pct * dur_sec_int)
                with data_lock:
                    spotify_state["current_sec"] = float(seek_sec)
                last_seek_time = time.time()
                safe_api_call(sp.seek_track, seek_sec * 1000, device_id=current_dev_id)
                continue

            # Steuerung im Fullscreen-Modus
            if display_mode and fs_controls_alpha > 50:
                if fs_btn_play.collidepoint(mx, my):
                    new_playing = not is_playing
                    with data_lock:
                        spotify_state["is_playing"] = new_playing
                        last_play_time = time.time()
                    if new_playing:
                        safe_api_call(sp.start_playback, device_id=current_dev_id)
                    else:
                        safe_api_call(sp.pause_playback, device_id=current_dev_id)
                    continue

                elif fs_btn_next.collidepoint(mx, my):
                    safe_api_call(sp.next_track, device_id=current_dev_id)
                    continue

                elif fs_btn_prev.collidepoint(mx, my):
                    def do_prev():
                        dev = get_active_device_or_fallback()
                        try:
                            sp.previous_track(device_id=dev)
                        except Exception:
                            try:
                                sp.seek_track(0, device_id=dev)
                            except Exception:
                                pass
                        with data_lock:
                            spotify_state["reset_scroll"] = True
                        wake_event.set()
                    threading.Thread(target=do_prev, daemon=True).start()
                    continue

                elif fs_btn_mode.collidepoint(mx, my):
                    with data_lock:
                        if repeat_mode == "off" and not shuffle_on:
                            new_rep, new_shuf = "context", False
                        elif repeat_mode == "context":
                            new_rep, new_shuf = "track", False
                        elif repeat_mode == "track":
                            new_rep, new_shuf = "off", True
                        else:
                            new_rep, new_shuf = "off", False
                        spotify_state["repeat_state"] = new_rep
                        spotify_state["shuffle_state"] = new_shuf
                        last_mode_time = time.time()

                    def apply_mode():
                        dev = get_active_device_or_fallback()
                        try:
                            sp.repeat(state=new_rep, device_id=dev)
                            sp.shuffle(state=new_shuf, device_id=dev)
                        except Exception:
                            pass
                        wake_event.set()
                    threading.Thread(target=apply_mode, daemon=True).start()
                    continue

                elif fs_btn_like.collidepoint(mx, my):
                    t_id = spotify_state["track_id"]
                    if t_id:
                        new_saved = not is_saved
                        with data_lock:
                            spotify_state["is_saved"] = new_saved
                        if new_saved:
                            safe_api_call(sp.current_user_saved_tracks_add, tracks=[t_id])
                        else:
                            safe_api_call(sp.current_user_saved_tracks_delete, tracks=[t_id])
                    continue

                elif fs_volume_hitbox.collidepoint(mx, my):
                    dragging_volume = True
                    rel_x = mx - fs_volume_bar.x
                    new_pct = int(max(0.0, min(1.0, rel_x / fs_volume_bar.w)) * 100)
                    with data_lock:
                        spotify_state["volume_percent"] = new_pct
                    last_vol_api_time = time.time()
                    safe_api_call(sp.volume, new_pct, device_id=current_dev_id)
                    continue

            if (show_lyrics or display_mode) and lyrics_area_rect.collidepoint(mx, my):
                rel_my = my - lyrics_area_rect.y
                row_h = 76 if display_mode else 54
                clicked_row = int((rel_my - lyric_scroll_y) // row_h)
                if 0 <= clicked_row < len(lyrics_lines):
                    target_ms = lyrics_lines[clicked_row][0]
                    with data_lock:
                        spotify_state["current_sec"] = float(target_ms // 1000)
                    last_seek_time = time.time()
                    user_scrolled_time = 0.0
                    safe_api_call(sp.seek_track, target_ms, device_id=current_dev_id)
                continue

            if not display_mode:
                if btn_play.collidepoint(mx, my):
                    new_playing = not is_playing
                    with data_lock:
                        spotify_state["is_playing"] = new_playing
                        last_play_time = time.time()
                    if new_playing:
                        safe_api_call(sp.start_playback, device_id=current_dev_id)
                    else:
                        safe_api_call(sp.pause_playback, device_id=current_dev_id)

                elif btn_next.collidepoint(mx, my):
                    safe_api_call(sp.next_track, device_id=current_dev_id)

                elif btn_prev.collidepoint(mx, my):
                    def do_prev():
                        dev = get_active_device_or_fallback()
                        try:
                            sp.previous_track(device_id=dev)
                        except Exception:
                            try:
                                sp.seek_track(0, device_id=dev)
                            except Exception:
                                pass
                        with data_lock:
                            spotify_state["reset_scroll"] = True
                        wake_event.set()
                    threading.Thread(target=do_prev, daemon=True).start()

                elif btn_mode.collidepoint(mx, my):
                    with data_lock:
                        if repeat_mode == "off" and not shuffle_on:
                            new_rep, new_shuf = "context", False
                        elif repeat_mode == "context":
                            new_rep, new_shuf = "track", False
                        elif repeat_mode == "track":
                            new_rep, new_shuf = "off", True
                        else:
                            new_rep, new_shuf = "off", False
                        spotify_state["repeat_state"] = new_rep
                        spotify_state["shuffle_state"] = new_shuf
                        last_mode_time = time.time()

                    def apply_mode():
                        dev = get_active_device_or_fallback()
                        try:
                            sp.repeat(state=new_rep, device_id=dev)
                            sp.shuffle(state=new_shuf, device_id=dev)
                        except Exception:
                            pass
                        wake_event.set()
                    threading.Thread(target=apply_mode, daemon=True).start()

                elif btn_like.collidepoint(mx, my):
                    t_id = spotify_state["track_id"]
                    if not t_id:
                        continue
                    new_saved = not is_saved
                    with data_lock:
                        spotify_state["is_saved"] = new_saved
                    if new_saved:
                        safe_api_call(sp.current_user_saved_tracks_add, tracks=[t_id])
                    else:
                        safe_api_call(sp.current_user_saved_tracks_delete, tracks=[t_id])

                elif btn_device_bar.collidepoint(mx, my):
                    show_device_menu = not show_device_menu
                    if show_device_menu:
                        refresh_devices_async()

                elif btn_lyrics.collidepoint(mx, my):
                    show_lyrics = not show_lyrics
                    user_scrolled_time = 0.0
                    new_w = EXPANDED_WIDTH if show_lyrics else BASE_WIDTH
                    screen = pygame.display.set_mode((new_w, BASE_HEIGHT), pygame.RESIZABLE)

                elif volume_hitbox.collidepoint(mx, my):
                    dragging_volume = True
                    rel_x = mx - volume_bar.x
                    new_pct = int(max(0.0, min(1.0, rel_x / volume_bar.w)) * 100)
                    with data_lock:
                        spotify_state["volume_percent"] = new_pct
                    last_vol_api_time = time.time()
                    safe_api_call(sp.volume, new_pct, device_id=current_dev_id)

    # 1. Weicher Cover-Blur Hintergrund mit sanftem Floating-Effekt
    drift_x = int(math.sin(current_time * 0.25) * 20.0)
    drift_y = int(math.cos(current_time * 0.20) * 15.0)

    bg_offset_x = (cur_screen_w - current_bg.get_width()) // 2 + drift_x
    bg_offset_y = (cur_screen_h - current_bg.get_height()) // 2 + drift_y

    if next_bg is not None and crossfade_alpha < 255.0:
        crossfade_alpha = min(255.0, crossfade_alpha + (CROSSFADE_SPEED * 60.0 * dt_sec))
        if crossfade_alpha >= 255.0:
            current_bg = next_bg
            next_bg = None
            current_card_std = next_card_std
            current_card_fs = next_card_fs
            next_card_std = None
            next_card_fs = None

    screen.blit(current_bg, (bg_offset_x, bg_offset_y))
    if next_bg is not None:
        next_bg.set_alpha(int(crossfade_alpha))
        screen.blit(next_bg, (bg_offset_x, bg_offset_y))

    # 2. Cover- & Songkarte
    if display_mode:
        cover_pos_x = 50
        cover_pos_y = max(20, (cur_screen_h - 640) // 2)
        screen.blit(current_card_fs, (cover_pos_x, cover_pos_y))
        if next_card_fs is not None:
            next_card_fs.set_alpha(int(crossfade_alpha))
            screen.blit(next_card_fs, (cover_pos_x, cover_pos_y))
    else:
        active_card = current_card_std
        screen.blit(active_card, (0, 0))
        if next_card_std is not None:
            next_card_std.set_alpha(int(crossfade_alpha))
            screen.blit(next_card_std, (0, 0))

    # 3. Lyrics Panel (Sauber mit Alpha-Fill gegen Textverschmieren)
    if show_lyrics or display_mode:
        panel_w = max(10, lyrics_area_rect.w)
        panel_h = max(10, lyrics_area_rect.h)
        lyrics_surface = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        lyrics_surface.fill((0, 0, 0, 0))

        active_idx = -1
        for i, (l_ms, _) in enumerate(lyrics_lines):
            if progress_ms >= l_ms:
                active_idx = i
            else:
                break

        line_height = 76 if display_mode else 54
        target_center_y = panel_h // 2

        if time.time() - user_scrolled_time > 3.0:
            if not lyrics_lines:
                target_scroll = 0.0
            elif active_idx == -1:
                target_scroll = 50.0 if display_mode else 30.0
            else:
                target_scroll = -(active_idx * line_height) + target_center_y
            
            easing_factor = 1.0 - math.exp(-10.0 * dt_sec)
            lyric_scroll_y += (target_scroll - lyric_scroll_y) * easing_factor

        if not lyrics_lines:
            f_idle = font_display_lyric_idle if display_mode else font_lyric_idle
            t_none = f_idle.render("Keine Songtexte gefunden", True, (160, 160, 165))
            lyrics_surface.blit(t_none, (panel_w // 2 - t_none.get_width() // 2, panel_h // 2 - 20))
        else:
            max_line_w = max(50, panel_w - 30)

            for i, (_, line_text) in enumerate(lyrics_lines):
                y_pos = int(lyric_scroll_y + i * line_height)
                
                if -60 < y_pos < panel_h + 30:
                    is_active = (i == active_idx)
                    ref_idx = active_idx if active_idx != -1 else 0
                    dist = abs(i - ref_idx)
                    is_intro = (active_idx == -1)

                    cache_key = (line_text, is_active, dist, display_mode, max_line_w, is_intro)
                    if cache_key not in rendered_lyrics_cache:
                        if display_mode:
                            if is_active:
                                fnt = font_display_lyric_active
                                s_shadow = fnt.render(line_text, True, (0, 0, 0))
                                s_rend = fnt.render(line_text, True, (255, 255, 255))
                                if s_rend.get_width() > max_line_w:
                                    sc = max_line_w / s_rend.get_width()
                                    new_sz = (int(s_rend.get_width() * sc), int(s_rend.get_height() * sc))
                                    s_rend = pygame.transform.smoothscale(s_rend, new_sz)
                                    s_shadow = pygame.transform.smoothscale(s_shadow, new_sz)
                                rendered_lyrics_cache[cache_key] = (s_shadow, s_rend)
                            else:
                                fnt = font_display_lyric_idle
                                if is_intro:
                                    alpha = 180 if dist == 0 else (130 if dist == 1 else (75 if dist == 2 else 30))
                                else:
                                    alpha = 215 if dist == 1 else (150 if dist == 2 else (80 if dist == 3 else 35))
                                
                                s_rend = fnt.render(line_text, True, (230, 230, 235))
                                if s_rend.get_width() > max_line_w:
                                    sc = max_line_w / s_rend.get_width()
                                    new_sz = (int(s_rend.get_width() * sc), int(s_rend.get_height() * sc))
                                    s_rend = pygame.transform.smoothscale(s_rend, new_sz)

                                s_rend.set_alpha(alpha)
                                rendered_lyrics_cache[cache_key] = (None, s_rend)
                        else:
                            if is_active:
                                fnt = font_lyric_active
                                s_shadow = fnt.render(line_text, True, (0, 0, 0))
                                s_rend = fnt.render(line_text, True, (255, 255, 255))
                                if s_rend.get_width() > max_line_w:
                                    sc = max_line_w / s_rend.get_width()
                                    new_sz = (int(s_rend.get_width() * sc), int(s_rend.get_height() * sc))
                                    s_rend = pygame.transform.smoothscale(s_rend, new_sz)
                                    s_shadow = pygame.transform.smoothscale(s_shadow, new_sz)
                                rendered_lyrics_cache[cache_key] = (s_shadow, s_rend)
                            else:
                                fnt = font_lyric_idle
                                if is_intro:
                                    alpha = 160 if dist == 0 else (115 if dist == 1 else 45)
                                else:
                                    alpha = 185 if dist == 1 else (135 if dist == 2 else 45)

                                s_rend = fnt.render(line_text, True, (215, 215, 220))
                                if s_rend.get_width() > max_line_w:
                                    sc = max_line_w / s_rend.get_width()
                                    new_sz = (int(s_rend.get_width() * sc), int(s_rend.get_height() * sc))
                                    s_rend = pygame.transform.smoothscale(s_rend, new_sz)

                                s_rend.set_alpha(alpha)
                                rendered_lyrics_cache[cache_key] = (None, s_rend)

                    shadow, rend = rendered_lyrics_cache[cache_key]
                    cx = max(0, panel_w // 2 - rend.get_width() // 2)
                    if shadow:
                        lyrics_surface.blit(shadow, (cx + 1, y_pos - 1))
                    lyrics_surface.blit(rend, (cx, y_pos - 2 if is_active else y_pos))

        screen.blit(lyrics_surface, (lyrics_area_rect.x, lyrics_area_rect.y))

    # 4. Fortschrittsbalken
    if display_mode:
        curr_bar_x = 60
        curr_bar_y = cur_screen_h - 45
        curr_bar_w = cur_screen_w - 120
        curr_bar_h = 8
    else:
        curr_bar_x = 35
        curr_bar_y = 372
        curr_bar_w = 310
        curr_bar_h = 5

    render_progress_bar = pygame.Rect(curr_bar_x, curr_bar_y, curr_bar_w, curr_bar_h)
    pygame.draw.rect(
        screen, (255, 255, 255, 40), render_progress_bar, border_radius=4
    )

    fill_width = int(curr_bar_w * max(0.0, min(1.0, cur_sec_int / dur_sec_int)))

    if fill_width > 0:
        fill_rect = pygame.Rect(
            render_progress_bar.x,
            render_progress_bar.y,
            fill_width,
            render_progress_bar.h,
        )
        pygame.draw.rect(screen, accent, fill_rect, border_radius=4)

    curr_t = f"{cur_sec_int // 60}:{cur_sec_int % 60:02d}"
    tot_t = f"{dur_sec_int // 60}:{dur_sec_int % 60:02d}"

    t_fnt = font_time_fs if display_mode else font_time
    t_curr_rend = t_fnt.render(curr_t, True, (215, 215, 220))
    t_tot_rend = t_fnt.render(tot_t, True, (215, 215, 220))

    time_text_y = curr_bar_y + 12 if display_mode else curr_bar_y + 8
    screen.blit(t_curr_rend, (render_progress_bar.x, time_text_y))
    screen.blit(
        t_tot_rend,
        (render_progress_bar.right - t_tot_rend.get_width(), time_text_y),
    )

    # 5. Steuerungselemente
    if display_mode:
        if time.time() - last_mouse_move_time < 3.0:
            fs_controls_alpha = min(255.0, fs_controls_alpha + 350.0 * dt_sec)
        else:
            fs_controls_alpha = max(0.0, fs_controls_alpha - 250.0 * dt_sec)

        if fs_controls_alpha > 0:
            fs_ctrl_surf = pygame.Surface((cur_screen_w, 90), pygame.SRCALPHA)
            
            draw_custom_buttons(fs_ctrl_surf, is_playing, 
                                pygame.Rect(fs_btn_prev.x, 20, 40, 40),
                                pygame.Rect(fs_btn_play.x, 14, 52, 52),
                                pygame.Rect(fs_btn_next.x, 20, 40, 40))

            if repeat_mode == "context":
                draw_vector_icon(fs_ctrl_surf, "repeat", pygame.Rect(fs_btn_mode.x, 22, 36, 36), accent)
            elif repeat_mode == "track":
                draw_vector_icon(fs_ctrl_surf, "repeat_one", pygame.Rect(fs_btn_mode.x, 22, 36, 36), accent)
            elif shuffle_on:
                draw_vector_icon(fs_ctrl_surf, "shuffle", pygame.Rect(fs_btn_mode.x, 22, 36, 36), accent)
            else:
                draw_vector_icon(fs_ctrl_surf, "repeat", pygame.Rect(fs_btn_mode.x, 22, 36, 36), (180, 180, 180))

            heart_col = accent if is_saved else (200, 200, 200)
            draw_vector_icon(fs_ctrl_surf, "heart", pygame.Rect(fs_btn_like.x, 22, 36, 36), heart_col, filled=is_saved)

            draw_vector_icon(fs_ctrl_surf, "vol_low", pygame.Rect(fs_volume_bar.x - 28, 24, 28, 28), (170, 170, 170))
            draw_vector_icon(fs_ctrl_surf, "vol_high", pygame.Rect(fs_volume_bar.right + 4, 24, 28, 28), (170, 170, 170))
            pygame.draw.rect(fs_ctrl_surf, (255, 255, 255, 40), pygame.Rect(fs_volume_bar.x, 38, fs_volume_bar.w, 4), border_radius=2)
            
            fs_v_fill = int(fs_volume_bar.w * (vol_pct / 100))
            if fs_v_fill > 0:
                pygame.draw.rect(fs_ctrl_surf, accent, pygame.Rect(fs_volume_bar.x, 38, fs_v_fill, 4), border_radius=2)
            pygame.draw.circle(fs_ctrl_surf, (255, 255, 255), (fs_volume_bar.x + fs_v_fill, 40), 5)

            fs_ctrl_surf.set_alpha(int(fs_controls_alpha))
            screen.blit(fs_ctrl_surf, (0, fs_ctrl_y - 20))

    else:
        dev_str = f"Playing on: {device_name}"
        if len(dev_str) > 22:
            dev_str = dev_str[:20] + "..."
        d_rend = font_device.render(dev_str, True, accent)
        screen.blit(d_rend, (btn_device_bar.centerx - d_rend.get_width() // 2, btn_device_bar.y + 4))

        lyr_col = accent if show_lyrics else (180, 180, 180)
        draw_vector_icon(screen, "mic", btn_lyrics, lyr_col)

        if repeat_mode == "context":
            draw_vector_icon(screen, "repeat", btn_mode, accent)
        elif repeat_mode == "track":
            draw_vector_icon(screen, "repeat_one", btn_mode, accent)
        elif shuffle_on:
            draw_vector_icon(screen, "shuffle", btn_mode, accent)
        else:
            draw_vector_icon(screen, "repeat", btn_mode, (180, 180, 180))

        draw_custom_buttons(screen, is_playing, btn_prev, btn_play, btn_next)

        heart_col = accent if is_saved else (200, 200, 200)
        draw_vector_icon(screen, "heart", btn_like, heart_col, filled=is_saved)

        draw_vector_icon(
            screen, "vol_low", pygame.Rect(volume_bar.x - 28, volume_bar.y - 14, 28, 28), (170, 170, 170)
        )
        draw_vector_icon(
            screen, "vol_high", pygame.Rect(volume_bar.right + 4, volume_bar.y - 14, 28, 28), (170, 170, 170)
        )

        pygame.draw.rect(screen, (255, 255, 255, 40), volume_bar, border_radius=2)
        v_fill_width = int(volume_bar.w * (vol_pct / 100))
        if v_fill_width > 0:
            v_fill = pygame.Rect(
                volume_bar.x, volume_bar.y, v_fill_width, volume_bar.h
            )
            pygame.draw.rect(screen, accent, v_fill, border_radius=2)

        handle_x = volume_bar.x + v_fill_width
        h_col = (255, 255, 255)
        mx, my = pygame.mouse.get_pos()
        if volume_hitbox.collidepoint(mx, my) or dragging_volume:
            h_col = accent
        pygame.draw.circle(screen, h_col, (handle_x, volume_bar.centery), 6)

    # 6. Spotify Connect Popup
    if show_device_menu and not display_mode:
        popup_w = 320
        item_h = 34
        header_h = 38
        max_h = 240
        total_content_h = header_h + len(avail_devices) * item_h
        popup_h = min(max_h, max(80, total_content_h + 10))
        popup_x = (BASE_WIDTH - popup_w) // 2
        popup_y = max(10, btn_device_bar.y - popup_h - 10)

        popup_surf = pygame.Surface((popup_w, popup_h), pygame.SRCALPHA)
        pygame.draw.rect(popup_surf, (20, 20, 24, 240), (0, 0, popup_w, popup_h), border_radius=14)
        pygame.draw.rect(popup_surf, (255, 255, 255, 30), (0, 0, popup_w, popup_h), width=1, border_radius=14)

        title_rend = font_device.render("VERFÜGBARE GERÄTE", True, (175, 175, 180))
        popup_surf.blit(title_rend, (18, 13))

        if not avail_devices:
            n_rend = font_device_list.render("Suche Geräte...", True, (190, 190, 195))
            popup_surf.blit(n_rend, (18, 44))
        else:
            mx, my = pygame.mouse.get_pos()
            for idx, d in enumerate(avail_devices):
                y_pos = header_h + idx * item_h
                if y_pos + item_h > popup_h:
                    break

                is_cur = d.get("id") == current_dev_id
                d_col = accent if is_cur else (240, 240, 245)
                d_name = d.get("name", "Unbekannt")
                if len(d_name) > 23:
                    d_name = d_name[:21] + ".."

                item_global_rect = pygame.Rect(popup_x + 6, popup_y + y_pos, popup_w - 12, item_h - 4)
                if item_global_rect.collidepoint(mx, my):
                    hover_surf = pygame.Surface((popup_w - 12, item_h - 4), pygame.SRCALPHA)
                    hover_surf.fill((255, 255, 255, 30))
                    popup_surf.blit(hover_surf, (6, y_pos))

                dot_y = y_pos + (item_h - 4) // 2
                if is_cur:
                    pygame.draw.circle(popup_surf, (accent[0], accent[1], accent[2]), (22, dot_y), 4)
                else:
                    pygame.draw.circle(popup_surf, (140, 140, 145), (22, dot_y), 3)

                item_text = f"{d_name}"
                if is_cur:
                    item_text += " (Aktiv)"

                item_rend = font_device_list.render(item_text, True, d_col)
                popup_surf.blit(item_rend, (34, y_pos + 4))

        screen.blit(popup_surf, (popup_x, popup_y))

    # 7. Warteschlange Overlay
    if show_queue:
        qw = 340
        qh = 280
        qx = cur_screen_w - qw - 30 if display_mode else (BASE_WIDTH - qw) // 2
        qy = 40 if display_mode else 80

        q_surf = pygame.Surface((qw, qh), pygame.SRCALPHA)
        pygame.draw.rect(q_surf, (18, 18, 22, 235), (0, 0, qw, qh), border_radius=16)
        pygame.draw.rect(q_surf, (255, 255, 255, 35), (0, 0, qw, qh), width=1, border_radius=16)

        q_head = font_queue_header.render("NÄCHSTE TRACKS (Q)", True, (255, 255, 255))
        q_surf.blit(q_head, (20, 16))

        if not queue_tracks:
            q_empty = font_queue_artist.render("Keine Tracks in der Warteschlange", True, (160, 160, 165))
            q_surf.blit(q_empty, (20, 60))
        else:
            for idx, (q_t, q_a) in enumerate(queue_tracks[:4]):
                item_y = 52 + idx * 52
                
                t_str = q_t[:24] + "..." if len(q_t) > 27 else q_t
                a_str = q_a[:28] + "..." if len(q_a) > 31 else q_a

                num_rend = font_queue_track.render(f"{idx+1}.", True, accent)
                t_rend = font_queue_track.render(t_str, True, (240, 240, 245))
                a_rend = font_queue_artist.render(a_str, True, (170, 170, 175))

                q_surf.blit(num_rend, (20, item_y))
                q_surf.blit(t_rend, (42, item_y))
                q_surf.blit(a_rend, (42, item_y + 20))

        screen.blit(q_surf, (qx, qy))

    pygame.display.flip()
    clock.tick(60)

pygame.quit()