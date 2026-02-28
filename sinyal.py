import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import traceback

# --- AYARLAR ---
TELEGRAM_TOKEN = "7968551890:AAFmtuxAvIEhpYVg7m8NL2TjROLQPgJxvzA"
CHAT_ID = "@rhksinyal"
TIMEFRAME = "15m" 
LIMIT = 1000

def get_all_usdt_futures():
    """Binance Vadeli İşlemlerdeki aktif tüm USDT paritelerini bulur"""
    print("🌍 Tüm piyasa coinleri taranıyor, liste güncelleniyor...")
    try:
        exchange.load_markets()
        symbols = []
        for symbol in exchange.markets:
            market = exchange.markets[symbol]
            # Sadece USDT çiftlerini, aktif olanları ve Vadeli (Linear) olanları seç
            if market.get('active') and market.get('linear') and market.get('quote') == 'USDT':
                symbols.append(symbol)
        return symbols
    except Exception as e:
        mesaj = f"⚠️ Coin listesi çekilemedi!\nDetay: {e}"
        send_telegram_message(mesaj)
        return ["BTC/USDT:USDT", "ETH/USDT:USDT"] # Hata anında yedek güvenlik listesi

# --- RİSK VE TAKİP AYARLARI ---
STOP_LOSS_YUZDE = 0.01  # %1 Zarar Kes
TAKE_PROFIT_YUZDE = 0.02 # %2 Kâr Al

# Kârı Koruma (Trailing) Ayarları
KAR_KORUMA_TETIKLEYICI = 0.008  # Fiyat %0.8 kâra ulaşırsa koruma kalkanı açılır
KAR_KORUMA_MESAFESI = 0.004     # Zirveden %0.4 düşerse "Kârı al kaç" der

# --- BİNANCE FUTURES BAĞLANTISI ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# Botun Hafızası
aktif_islemler = {}  
son_sinyal_zamanlari = {}

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Mesaj hatası: {e}")

def aktif_islemi_takip_et(symbol):
    """15 saniyede bir işlemde olduğumuz coini denetler ve Telegram'a anlık rapor atar"""
    try:
        ticker = exchange.fetch_ticker(symbol)
        guncel_fiyat = ticker['last']
        
        islem = aktif_islemler[symbol]
        yon = islem['yon']
        giris = islem['giris_fiyati']
        
        # --- YENİ EKLENEN: HER 15 SANİYEDE BİR CANLI RAPOR MESAJI ---
        kar_zarar = "🟢 KÂRDA" if (yon == 'LONG' and guncel_fiyat > giris) or (yon == 'SHORT' and guncel_fiyat < giris) else "🔴 ZARARDA"
        
        canli_mesaj = (f"⏱️ **CANLI TAKİP: {symbol} ({yon})**\n"
                       f"Durum: {kar_zarar}\n"
                       f"Güncel Fiyat: {guncel_fiyat:.4f}\n"
                       f"Giriş Fiyatı: {giris:.4f}\n"
                       f"En İyi Görülen: {islem['en_iyi_fiyat']:.4f}\n"
                       f"----------------------------")
        send_telegram_message(canli_mesaj)
        # -------------------------------------------------------------
        
        if yon == 'LONG':
            if guncel_fiyat > islem['en_iyi_fiyat']:
                aktif_islemler[symbol]['en_iyi_fiyat'] = guncel_fiyat
            
            en_iyi = aktif_islemler[symbol]['en_iyi_fiyat']
            
            # 1. KÂR AL (BAŞARI MESAJI)
            if guncel_fiyat >= islem['hedef']:
                mesaj = (f"🎯 **BAŞARI: HEDEFE ULAŞILDI! (LONG)** 🎯\n"
                         f"----------------------------\n"
                         f"Coin: {symbol}\n"
                         f"Durum: %2 Kâr Hedefi Vuruldu!\n"
                         f"Güncel Fiyat: {guncel_fiyat:.4f}\n\n"
                         f"👉 **İşlemi hemen kârla kapatın ve kazancın tadını çıkarın!** 💰")
                send_telegram_message(mesaj)
                del aktif_islemler[symbol] 
                
            # 2. ZARAR KES (Stop Loss)
            elif guncel_fiyat <= islem['stop']:
                mesaj = f"🛑 **STOP PATLADI (LONG)**\n{symbol} %1 Zarara Ulaştı.\nKapanış: {guncel_fiyat:.4f}\nSağlık olsun, işlemi kapatın ve diğer fırsatları bekleyin."
                send_telegram_message(mesaj)
                del aktif_islemler[symbol]
                
            # 3. KÂRI KORU (Erken Çıkış)
            elif en_iyi >= giris * (1 + KAR_KORUMA_TETIKLEYICI): 
                if guncel_fiyat <= en_iyi * (1 - KAR_KORUMA_MESAFESI): 
                    mesaj = (f"⚠️ **KÂRI AL VE KAÇ! (LONG)**\n"
                             f"----------------------------\n"
                             f"Coin: {symbol}\n"
                             f"Durum: %2 hedefe gidemeden dönüşe geçti.\n"
                             f"Zirve Görülmüş: {en_iyi:.4f}\n"
                             f"Güncel Düşüş: {guncel_fiyat:.4f}\n"
                             f"👉 **Kârdan zarar etmemek için işlemi hemen kapatın!**")
                    send_telegram_message(mesaj)
                    del aktif_islemler[symbol]

        elif yon == 'SHORT':
            if guncel_fiyat < islem['en_iyi_fiyat']:
                aktif_islemler[symbol]['en_iyi_fiyat'] = guncel_fiyat
                
            en_iyi = aktif_islemler[symbol]['en_iyi_fiyat']
            
            # 1. KÂR AL (BAŞARI MESAJI)
            if guncel_fiyat <= islem['hedef']:
                mesaj = (f"🎯 **BAŞARI: HEDEFE ULAŞILDI! (SHORT)** 🎯\n"
                         f"----------------------------\n"
                         f"Coin: {symbol}\n"
                         f"Durum: %2 Kâr Hedefi Vuruldu!\n"
                         f"Güncel Fiyat: {guncel_fiyat:.4f}\n\n"
                         f"👉 **İşlemi hemen kârla kapatın ve kazancın tadını çıkarın!** 💰")
                send_telegram_message(mesaj)
                del aktif_islemler[symbol]
                
            # 2. ZARAR KES (Stop Loss)
            elif guncel_fiyat >= islem['stop']:
                mesaj = f"🛑 **STOP PATLADI (SHORT)**\n{symbol} %1 Zarara Ulaştı.\nKapanış: {guncel_fiyat:.4f}\nSağlık olsun, işlemi kapatın ve diğer fırsatları bekleyin."
                send_telegram_message(mesaj)
                del aktif_islemler[symbol]
                
            # 3. KÂRI KORU (Erken Çıkış)
            elif en_iyi <= giris * (1 - KAR_KORUMA_TETIKLEYICI):
                if guncel_fiyat >= en_iyi * (1 + KAR_KORUMA_MESAFESI):
                    mesaj = (f"⚠️ **KÂRI AL VE KAÇ! (SHORT)**\n"
                             f"----------------------------\n"
                             f"Coin: {symbol}\n"
                             f"Durum: Hedefe gidemeden yükselişe geçti.\n"
                             f"Dip Görülmüş: {en_iyi:.4f}\n"
                             f"Güncel Çıkış: {guncel_fiyat:.4f}\n"
                             f"👉 **Kârdan zarar etmemek için işlemi hemen kapatın!**")
                    send_telegram_message(mesaj)
                    del aktif_islemler[symbol]

    except Exception as e:
        hata_mesaji = f"⚠️ **TAKİP HATASI ({symbol})**\nArka planda bir sorun oluştu ama bot çalışmaya devam ediyor.\nDetay: `{e}`"
        send_telegram_message(hata_mesaji)
        print(f"Takip hatası ({symbol}): {e}")

def analyze_and_signal(symbol):
    """Yeni fırsatları arka planda SESSİZCE tarar"""
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['RSI'] = ta.rsi(df['close'], length=14)
        df['EMA_100'] = ta.ema(df['close'], length=100)
        df['VOL_SMA'] = ta.sma(df['volume'], length=20)
        
        latest = df.iloc[-1]
        close_price = latest['close']
        is_uptrend = close_price > latest['EMA_100']
        is_high_volume = latest['volume'] > latest['VOL_SMA']

        # --- DİKKAT: ESKİ DURUM RAPORU BURADAN TAMAMEN SİLİNDİ! ---

        # LONG SİNYALİ
        if latest['RSI'] <= 30 and is_uptrend and is_high_volume:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                stop_loss = close_price * (1 - STOP_LOSS_YUZDE)
                take_profit = close_price * (1 + TAKE_PROFIT_YUZDE)
                
                mesaj = (f"🟢 **LONG SİNYALİ AÇILDI**\n"
                         f"----------------------------\n"
                         f"Parite: {symbol}\n"
                         f"Giriş: {close_price:.4f}\n"
                         f"🎯 Hedef: {take_profit:.4f}\n"
                         f"🛑 Stop: {stop_loss:.4f}\n"
                         f"⚡ Bot bu işlemi 15 saniyede bir takip edecek!\n"
                         f"----------------------------")
                send_telegram_message(mesaj)
                son_sinyal_zamanlari[symbol] = latest['timestamp']
                
                aktif_islemler[symbol] = {
                    'yon': 'LONG',
                    'giris_fiyati': close_price,
                    'en_iyi_fiyat': close_price,
                    'hedef': take_profit,
                    'stop': stop_loss
                }
        
        # SHORT SİNYALİ
        elif latest['RSI'] >= 70 and not is_uptrend and is_high_volume:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                stop_loss = close_price * (1 + STOP_LOSS_YUZDE)
                take_profit = close_price * (1 - TAKE_PROFIT_YUZDE)
                
                mesaj = (f"🔴 **SHORT SİNYALİ AÇILDI**\n"
                         f"----------------------------\n"
                         f"Parite: {symbol}\n"
                         f"Giriş: {close_price:.4f}\n"
                         f"🎯 Hedef: {take_profit:.4f}\n"
                         f"🛑 Stop: {stop_loss:.4f}\n"
                         f"⚡ Bot bu işlemi 15 saniyede bir takip edecek!\n"
                         f"----------------------------")
                send_telegram_message(mesaj)
                son_sinyal_zamanlari[symbol] = latest['timestamp']
                
                aktif_islemler[symbol] = {
                    'yon': 'SHORT',
                    'giris_fiyati': close_price,
                    'en_iyi_fiyat': close_price,
                    'hedef': take_profit,
                    'stop': stop_loss
                }
                
    except Exception as e:
        hata_mesaji = f"⚠️ **TARAMA HATASI ({symbol})**\nBu coin taranırken bir sorun oluştu, pas geçiliyor.\nDetay: `{e}`"
        send_telegram_message(hata_mesaji)
        print(f"Analiz hatası ({symbol}): {e}")

# --- ANA DÖNGÜ (Zamanlayıcı Motoru) ---
if __name__ == "__main__":
    try:
        print("🤖 TÜM PİYASA (250+ COİN) AVCI BOTU BAŞLATILDI")
        send_telegram_message("🚀 **Sistem Başlatıldı!**\nBütün Binance Futures piyasası arka planda sessizce taranacak.")
        
        son_genel_tarama = 0
        TARAMA_ARALIGI = 300 # 5 Dakika
        TAKIP_ARALIGI = 15   # 15 Saniye
        
        while True:
            su_an = time.time()
            
            # 1. GÖREV: Aktif İşlemleri Saniye Saniye Koru
            if aktif_islemler:
                for symbol in list(aktif_islemler.keys()):
                    aktif_islemi_takip_et(symbol)
            
            # 2. GÖREV: Piyasada Yeni Fırsat Ara (Sadece 5 dakikada bir çalışır)
            if su_an - son_genel_tarama >= TARAMA_ARALIGI:
                
                guncel_coin_listesi = get_all_usdt_futures()
                toplam_coin = len(guncel_coin_listesi)
                
                döngü_baslangic = f"\n🔄 **YENİ TARAMA BAŞLIYOR**\nHedef: Tüm Piyasa ({toplam_coin} Coin)\n➖➖➖➖➖➖➖➖➖➖"
                print(döngü_baslangic)
                send_telegram_message(döngü_baslangic)
                
                tarama_sayaci = 0  # Hangi coinde olduğumuzu sayacak
                
                for symbol in guncel_coin_listesi:
                    if symbol not in aktif_islemler: 
                        analyze_and_signal(symbol)
                        time.sleep(0.5) # API Limiti Koruması
                        
                    tarama_sayaci += 1 # Her coinde sayacı 1 artır
                    
                    # HER 50 COİNDE BİR BİLGİLENDİRME AT (50, 100, 150...)
                    if tarama_sayaci % 50 == 0:
                        ara_mesaj = f"⏳ **ARA RAPOR:** {tarama_sayaci} / {toplam_coin} coin tarandı. Piyasa şu an normal, fırsat aramaya devam ediliyor..."
                        print(ara_mesaj)
                        send_telegram_message(ara_mesaj)
                
                döngü_bitis = f"✅ **TÜM PİYASA TARANDI ({toplam_coin} Coin)**\nBot 5 dakika dinleniyor ve açık işlemleri izliyor...\n➖➖➖➖➖➖➖➖➖➖"
                print("Tarama bitti. Dinlenmeye geçildi.")
                send_telegram_message(döngü_bitis)
                
                son_genel_tarama = time.time()
            
            time.sleep(TAKIP_ARALIGI)

    except Exception as e:
        hata = f"🚨 **BOT ÇÖKTÜ!**\n\nDetay:\n{traceback.format_exc()}"
        send_telegram_message(hata)
        print(hata)
        raise e
