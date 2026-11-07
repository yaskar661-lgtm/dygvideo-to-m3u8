from flask import Flask, Response, abort
import requests
import re
import time
from threading import Lock

app = Flask(__name__)

# Desteklenen geçerli kanal listesi
VALID_CHANNELS = ["eurostar", "star", "ntv", "kralpoptv"]

# 2 saatlik (7200 saniye) TTL Cache sınıfı
class TTLCache:
    def __init__(self, ttl=7200):
        self.ttl = ttl
        self.cache_store = {}
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            if key in self.cache_store:
                data, timestamp = self.cache_store[key]
                if time.time() - timestamp < self.ttl:
                    return data
            return None

    def set(self, key, data):
        with self.lock:
            self.cache_store[key] = (data, time.time())
            return data

playlist_cache = TTLCache(ttl=7200)

@app.route("/canli/<channel_name>.m3u8", methods=["GET"])
def get_channel_stream(channel_name):
    channel_name = channel_name.lower()
    if channel_name not in VALID_CHANNELS:
        abort(404, description="Geçersiz kanal adı.")

    # 1. Cache kontrolü
    cached_data = playlist_cache.get(channel_name)
    if cached_data:
        return Response(cached_data, mimetype="application/vnd.apple.mpegurl")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        # 2. Eurostar ana sayfasından liveUrl'i çek
        source_page = "https://www.eurostartv.com.tr/canli-izle"
        main_response = requests.get(source_page, headers=headers, timeout=10)
        
        if main_response.status_code != 200:
            return "Kaynak sayfa yüklenemedi.", 500

        match = re.search(r"liveUrl = '(.*?)'", main_response.text)
        if not match:
            return "Live URL bulunamadı.", 404

        live_url = match.group(1)

        # 3. liveUrl isteği atıp 302 yönlendirmesini ve Location header'ını yakala
        redirect_response = requests.get(live_url, headers=headers, allow_redirects=False, timeout=10)
        
        if redirect_response.status_code == 302 and "Location" in redirect_response.headers:
            target_url = redirect_response.headers["Location"]
        else:
            target_url = live_url

        # NTV için özel URL düzenlemesi
        if channel_name == "ntv":
            st_match = re.search(r'[?&]st=([^&]+)', target_url)
            e_match = re.search(r'[?&]e=([^&]+)', target_url)
            
            if st_match and e_match:
                st_val = st_match.group(1)
                e_val = e_match.group(1)
                target_url = f"https://dogusdyg-ntv.lg.mncdn.com/live/dogusdyg_ntv/master.m3u8?st={st_val}&e={e_val}"

        # CDN base URL'ini Location adresinden türet 
        # (NTV için: https://dogusdyg-ntv.lg.mncdn.com/live/dogusdyg_ntv/)
        cdn_base = target_url.rsplit('/', 1)[0] + '/'

        # 4. Asıl m3u8 içeriğini çek
        content_response = requests.get(target_url, headers=headers, timeout=10)
        if content_response.status_code != 200:
            content_response = requests.get(live_url, headers=headers, timeout=10)
            
        if content_response.status_code != 200:
            return "Yayın içeriği alınamadı.", 500

        raw_content = content_response.text
        lines = raw_content.split("\n")

        # 5. live_ ile başlayan satırlara CDN base ekle
        processed_content = ""
        for line in lines:
            if line.startswith("live_") or line.startswith("stream"):
                processed_content += cdn_base + line + "\n"
            else:
                processed_content += line + "\n"

        # 6. re.subn ile metin içindeki 'eurostar' yazılarını istenen kanal slug'ına çevir
        if channel_name != "eurostar":
            final_content, count = re.subn(r'eurostar', channel_name, processed_content, flags=re.IGNORECASE)
        else:
            final_content = processed_content

        # 7. Sonucu cache'e kaydet (2 saat)
        playlist_cache.set(channel_name, final_content)

        return Response(final_content, mimetype="application/vnd.apple.mpegurl")

    except Exception as e:
        return f"Bir hata oluştu: {str(e)}", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
