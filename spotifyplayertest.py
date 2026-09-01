import os
import streamlit as st
import spotipy
from spotipy.oauth2 import SpotifyOAuth
import syncedlyrics
import time

# --- Streamlit Seiten-Konfiguration ---
st.set_page_config(page_title="Spotify Now Playing", page_icon="🎵", layout="centered")

# --- Spotify API Setup ---
# Credentials (aus deinem Skript)
C_ID = "3192b60bce0b44ddab655721cace88ee"
C_SEC = "c9ab5c224fca4d32b682a1c67b1c1ab5"

# In der Cloud nutzen wir das aktuelle Verzeichnis für den Cache
cache_file = ".spotify_cache_app"

# Die Redirect URI MUSS mit der Adresse deiner Streamlit-App übereinstimmen!
# Für den lokalen Test: "http://localhost:8501" oder "http://127.0.0.1:8501"
# Für die Cloud: Die URL deiner Streamlit-App (z.b. https://streamlit.app)
REDIRECT_URI = "https://streamlit.app" 

auth_manager = SpotifyOAuth(
    client_id=C_ID,
    client_secret=C_SEC,
    redirect_uri=REDIRECT_URI,
    scope="user-read-playback-state user-modify-playback-state",
    cache_path=cache_file,
    show_dialog=True
)

# --- Authentifizierungs-Logik im Webbrowser ---
# Prüfen, ob wir bereits einen Token im Cache haben oder per URL zurückkommen
if st.query_params.get("code"):
    auth_manager.get_access_token(st.query_params["code"])
    # Bereinige die URL nach erfolgreichem Login
    st.query_params.clear()

token_info = auth_manager.get_cached_token()

if not token_info:
    # Wenn kein Token existiert, zeige einen Login-Button für den Browser an
    auth_url = auth_manager.get_authorize_url()
    st.title("🎵 Spotify Verbindung erforderlich")
    st.write("Bitte melde dich an, damit die App deinen aktuellen Song anzeigen kann.")
    st.link_button("Mit Spotify anmelden", auth_url)
    st.stop()

# Wenn eingeloggt, Client starten
sp = spotipy.Spotify(auth=token_info['access_token'])

# --- Haupt-Anwendung ---
st.title("🎵 Aktueller Spotify Song")

# Container für Live-Updates erstellen
placeholder = st.empty()

# Cache für Songtexte, um API-Limits zu sparen
if "lyrics_cache" not in st.session_state:
    st.session_state.lyrics_cache = {}

# Live-Update-Schleife (aktualisiert alle 3 Sekunden im Browser)
while True:
    try:
        playback = sp.current_playback()
        
        if playback and playback.get("item"):
            item = playback["item"]
            title = item["name"]
            artist = ", ".join([a["name"] for a in item["artists"]])
            cover_url = item["album"]["images"][0]["url"] if item["album"]["images"] else None
            
            # Songtexte abrufen
            query = f"{title} {artist}"
            if query not in st.session_state.lyrics_cache:
                try:
                    lyrics = syncedlyrics.search(query)
                    # Einfache Bereinigung von Zeitstempeln für die Anzeige
                    if lyrics:
                        lines = [line.split("]")[-1].strip() for line in lyrics.splitlines() if line]
                        st.session_state.lyrics_cache[query] = "\n".join([l for l in lines if l])
                    else:
                        st.session_state.lyrics_cache[query] = "Keine Songtexte gefunden."
                except Exception:
                    st.session_state.lyrics_cache[query] = "Fehler beim Laden der Songtexte."
            
            current_lyrics = st.session_state.lyrics_cache[query]

            # UI im Platzhalter neu zeichnen
            with placeholder.container():
                col1, col2 = st.columns([1, 2])
                
                with col1:
                    if cover_url:
                        st.image(cover_url, use_column_width=True)
                
                with col2:
                    st.subheader(title)
                    st.write(f"**Künstler:** {artist}")
                    if playback.get("is_playing"):
                        st.caption("🟢 Wird gerade abgespielt")
                    else:
                        st.caption("⏸️ Pausiert")
                
                st.markdown("---")
                st.write("**Songtext:**")
                st.text(current_lyrics)
                
        else:
            with placeholder.container():
                st.info("Es wird aktuell keine Musik auf deinem Spotify-Konto abgespielt.")
                
    except Exception as e:
        with placeholder.container():
            st.error(f"Verbindung zu Spotify verloren. Versuche es erneut... ({e})")
            
    time.sleep(3)
