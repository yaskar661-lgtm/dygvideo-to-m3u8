import re
import requests
from flask import Flask, redirect

app = Flask(__name__)

# Önbellek (Cache)
stream_urls = {}

DIRECT_STREAMS = {
    "startv": "http://dygvideo.dygdigital.com/live/hls/startv4puhu?m3u8",
    "ntv": "http://dygvideo.dygdigital.com/live/hls/ntv4puhu?m3u8",
    "kralpoptv": "http://dygvideo.dygdigital.com/live/hls/kralpop?m3u8"
}

def update_channels():
    """Her 2 saatte bir arka planda yayın linklerini günceller."""
    print("🔄 Doğuş kanalları güncelleniyor...")
    global stream_urls
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    # 1. Star TV, NTV, Kral Pop ve diğer direkt/yönlendirmeli linkler
    for name, url in DIRECT_STREAMS.items():
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                stream_urls[name] = url
                print(f"✅ {name}: Bağlantı doğrulandı.")
        except Exception as e:
            print(f"❌ {name} güncellenirken hata: {e}")

    # 2. Euro Star (Star TV linkinin Location header'ını alıp 'star' -> 'eurostar' değişimi)
    try:
        # allow_redirects=False diyerek 302 yönlendirmesini yakalıyoruz
        res = requests.get(DIRECT_STREAMS["startv"], headers=headers, allow_redirects=False, timeout=10)
        
        # Eğer yönlendirme (302 vb.) geldiyse ve Location başlığı varsa
        if res.status_code in (301, 302, 303, 307, 308) and "Location" in res.headers:
            star_location = res.headers["Location"]
            # re.sub ile 'star' kelimesini 'eurostar' olarak değiştiriyoruz
            eurostar_url = re.sub(r'star', 'eurostar', star_location, flags=re.IGNORECASE)
            stream_urls["eurostartv"] = eurostar_url
            print(f"✅ eurostartv: Location header'dan türetildi.")
        else:
            # Yönlendirme yoksa doğrudan Star TV linkini baz alıp değiştirmeyi dene
            fallback_url = re.sub(r'star', 'eurostar', DIRECT_STREAMS["startv"], flags=re.IGNORECASE)
            stream_urls["eurostartv"] = fallback_url
            print(f"⚠️ eurostartv: Alternatif yöntemle türetildi.")
            
    except Exception as e:
        print(f"❌ eurostartv türetilirken hata: {e}")

@app.route("/")
def index():
    """Ana sayfa - Mevcut kanal listesini gösterir."""
    return {
        "channels": list(stream_urls.keys()),
        "endpoints": {
            "redirect": "/stream/<channel_name>"
        }
    }

@app.route("/stream/<channel_name>")
def redirect_stream(channel_name):
    """Kanalların güncel yayın adresine yönlendirir (redirect)."""
    channel_name = channel_name.lower()
    if channel_name in stream_urls:
        return redirect(stream_urls[channel_name])
    return {"error": "Kanal bulunamadı."}, 404

if __name__ == "__main__":
    # İlk çalıştırmada hemen verileri çek
    update_channels()

    # APScheduler ile her 2 saatte bir tetiklenecek şekilde ayarla
    from apscheduler.schedulers.background import BackgroundScheduler
    scheduler = BackgroundScheduler()
    scheduler.add_job(func=update_channels, trigger="interval", hours=2)
    scheduler.start()

    try:
        app.run(host="0.0.0.0", port=5000, debug=False)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
