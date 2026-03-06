import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import traceback
import os
import gc

from flask import Flask
from threading import Thread
import os

app = Flask('')

@app.route('/')
def home():
    return "🚀 Bot Canavar Gibi Ayakta!"

def run():
    # Render'ın otomatik atadığı kapıyı (PORT) bulur, uyumsuzluğu bitirir!
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- AYARLAR ---
TELEGRAM_TOKEN = os.environ.get("GIZLI_TOKEN", "HAYALET_AVCISI")
CHAT_ID = "@rhksinyal"
TIMEFRAME = "15m"
LIMIT = 1001
MAX_ACIK_ISLEM = 3  # Bot aynı anda en fazla kaç coine girsin?


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

def get_all_usdt_futures():
    try:
        exchange.load_markets()
        symbols = []
        for symbol in exchange.markets:
            market = exchange.markets[symbol]
            if market.get('active') and market.get('linear') and market.get('quote') == 'USDT':
                symbols.append(symbol)
        return symbols
    except Exception as e:
        send_telegram_message(f"⚠️ Coin listesi çekilemedi!\nDetay: {e}")
        return ["BTC/USDT:USDT", "ETH/USDT:USDT"]

def aktif_islemi_takip_et(symbol):
    """15 saniyede bir işlemde olduğumuz coini denetler ve ATR bazlı dinamik takip yapar"""
    try:
        ticker = exchange.fetch_ticker(symbol)
        guncel_fiyat = ticker['last']
        
        islem = aktif_islemler[symbol]
        yon = islem['yon']
        giris = islem['giris_fiyati']
        atr = islem['atr'] # Coinin o anki özel dalgalanma boyutu
        
        # Dinamik Kâr Koruma Ayarları (ATR'ye göre esner)
        kar_koruma_hedefi = 1.0 * atr  # Fiyat girişten 1 ATR kadar kâra geçerse kalkan açılır
        kar_koruma_esnekligi = 0.5 * atr # Zirveden yarım ATR kadar düşerse "kârı al kaç" der
        
        kar_zarar = "🟢 KÂRDA" if (yon == 'LONG' and guncel_fiyat > giris) or (yon == 'SHORT' and guncel_fiyat < giris) else "🔴 ZARARDA"
        
        canli_mesaj = (f"⏱️ **CANLI TAKİP: {symbol} ({yon})**\n"
                       f"Durum: {kar_zarar}\n"
                       f"Güncel Fiyat: {guncel_fiyat:.4f}\n"
                       f"Giriş: {giris:.4f} | En İyi: {islem['en_iyi_fiyat']:.4f}\n"
                       f"----------------------------")
        send_telegram_message(canli_mesaj)
        
        if yon == 'LONG':
            if guncel_fiyat > islem['en_iyi_fiyat']:
                aktif_islemler[symbol]['en_iyi_fiyat'] = guncel_fiyat
            
            en_iyi = aktif_islemler[symbol]['en_iyi_fiyat']
            
            # 1. KÂR AL (Take Profit)
            if guncel_fiyat >= islem['hedef']:
                mesaj = f"🎯 **BAŞARI: HEDEFE ULAŞILDI! (LONG)** 🎯\n{symbol} Dinamik Kâr Hedefi Vuruldu!\nGüncel Fiyat: {guncel_fiyat:.4f}\n👉 İşlemi kârla kapatın!"
                send_telegram_message(mesaj)
                del aktif_islemler[symbol] 
                
            # 2. ZARAR KES (Stop Loss)
            elif guncel_fiyat <= islem['stop']:
                mesaj = f"🛑 **STOP PATLADI (LONG)**\n{symbol} Dinamik Stop seviyesine değdi.\nKapanış: {guncel_fiyat:.4f}\nSağlık olsun, işlemi kapatın."
                send_telegram_message(mesaj)
                del aktif_islemler[symbol]
                
            # 3. DİNAMİK KÂRI KORU (Erken Çıkış)
            elif en_iyi >= giris + kar_koruma_hedefi: 
                if guncel_fiyat <= en_iyi - kar_koruma_esnekligi: 
                    mesaj = f"⚠️ **KÂRI AL VE KAÇ! (LONG)**\n{symbol} hedefe gidemeden dönüşe geçti.\nZirve: {en_iyi:.4f} | Çıkış: {guncel_fiyat:.4f}\n👉 Kârdan zarar etmemek için işlemi kapatın!"
                    send_telegram_message(mesaj)
                    del aktif_islemler[symbol]

        elif yon == 'SHORT':
            if guncel_fiyat < islem['en_iyi_fiyat']:
                aktif_islemler[symbol]['en_iyi_fiyat'] = guncel_fiyat
                
            en_iyi = aktif_islemler[symbol]['en_iyi_fiyat']
            
            # 1. KÂR AL
            if guncel_fiyat <= islem['hedef']:
                mesaj = f"🎯 **BAŞARI: HEDEFE ULAŞILDI! (SHORT)** 🎯\n{symbol} Dinamik Kâr Hedefi Vuruldu!\nGüncel Fiyat: {guncel_fiyat:.4f}\n👉 İşlemi kârla kapatın!"
                send_telegram_message(mesaj)
                del aktif_islemler[symbol]
                
            # 2. ZARAR KES
            elif guncel_fiyat >= islem['stop']:
                mesaj = f"🛑 **STOP PATLADI (SHORT)**\n{symbol} Dinamik Stop seviyesine değdi.\nKapanış: {guncel_fiyat:.4f}\nSağlık olsun, işlemi kapatın."
                send_telegram_message(mesaj)
                del aktif_islemler[symbol]
                
            # 3. DİNAMİK KÂRI KORU
            elif en_iyi <= giris - kar_koruma_hedefi:
                if guncel_fiyat >= en_iyi + kar_koruma_esnekligi:
                    mesaj = f"⚠️ **KÂRI AL VE KAÇ! (SHORT)**\n{symbol} hedefe gidemeden yükselişe geçti.\nDip: {en_iyi:.4f} | Çıkış: {guncel_fiyat:.4f}\n👉 Kârdan zarar etmemek için işlemi kapatın!"
                    send_telegram_message(mesaj)
                    del aktif_islemler[symbol]

    except Exception as e:
        hata_mesaji = f"⚠️ **TAKİP HATASI ({symbol})**\nArka planda sorun var, çalışmaya devam ediliyor.\nDetay: `{e}`"
        send_telegram_message(hata_mesaji)
        print(f"Takip hatası ({symbol}): {e}")

MAX_ACIK_ISLEM = 3  # Bot aynı anda en fazla kaç coine girsin? (Kasa Koruması)

def analyze_and_signal(symbol):
    """Gerçek Kırılımları Bulan, Kasa Korumalı Keskin Nişancı"""
    
    # 🛡️ KOTA KONTROLÜ: Eğer 3 işlem açıksa, yenilerine bakma!
    if len(aktif_islemler) >= MAX_ACIK_ISLEM:
        return
        
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
        
        if len(bars) < 100:
            return 
            
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        bb = ta.bbands(df['close'], length=20, std=2)
        if bb is None or bb.empty:
            return 
            
        df['BBL'] = bb.iloc[:, 0] # Alt Bant
        df['BBU'] = bb.iloc[:, 2] # Üst Bant
        
        df['EMA_100'] = ta.ema(df['close'], length=100)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['VOL_SMA'] = ta.sma(df['volume'], length=20) # Hacim filtresi GERİ GELDİ!
        
        # Sadece son muma değil, bir önceki muma da bakacağız (Gerçek kırılım için)
        previous = df.iloc[-2]
        latest = df.iloc[-1]
        
        if pd.isna(latest['ATR']) or pd.isna(latest['BBU']) or pd.isna(latest['EMA_100']):
            return

        atr_degeri = latest['ATR']
        
        is_uptrend = latest['close'] > latest['EMA_100']
        is_downtrend = latest['close'] < latest['EMA_100']
        is_high_volume = latest['volume'] > latest['VOL_SMA']

        # 🚀 GERÇEK MOMENTUM LONG: Önceki mum bandın altındaydı, ŞİMDİKİ kırdı! VE Hacim yüksek.
        if previous['close'] <= previous['BBU'] and latest['close'] > latest['BBU'] and is_uptrend and is_high_volume:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                
                stop_loss = latest['close'] - (atr_degeri * 1.5)
                take_profit = latest['close'] + (atr_degeri * 3.0)
                
                mesaj = (f"🚀 **GERÇEK KIRILIM: LONG SİNYALİ**\n"
                         f"----------------------------\n"
                         f"Parite: {symbol}\n"
                         f"Giriş: {latest['close']:.4f}\n\n"
                         f"🎯 Hedef: {take_profit:.4f}\n"
                         f"🛑 Stop: {stop_loss:.4f}\n\n"
                         f"🛡️ Hacim Onaylı | ATR Dinamik Stop\n"
                         f"----------------------------")
                send_telegram_message(mesaj)
                son_sinyal_zamanlari[symbol] = latest['timestamp']
                
                aktif_islemler[symbol] = {
                    'yon': 'LONG',
                    'giris_fiyati': latest['close'],
                    'en_iyi_fiyat': latest['close'],
                    'hedef': take_profit,
                    'stop': stop_loss,
                    'atr': atr_degeri
                }
        
        # 🩸 GERÇEK ŞELALE SHORT: Önceki mum bandın üstündeydi, ŞİMDİKİ aşağı kırdı! VE Hacim yüksek.
        elif previous['close'] >= previous['BBL'] and latest['close'] < latest['BBL'] and is_downtrend and is_high_volume:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                
                stop_loss = latest['close'] + (atr_degeri * 1.5)
                take_profit = latest['close'] - (atr_degeri * 3.0)
                
                mesaj = (f"🩸 **GERÇEK KIRILIM: SHORT SİNYALİ**\n"
                         f"----------------------------\n"
                         f"Parite: {symbol}\n"
                         f"Giriş: {latest['close']:.4f}\n\n"
                         f"🎯 Hedef: {take_profit:.4f}\n"
                         f"🛑 Stop: {stop_loss:.4f}\n\n"
                         f"🛡️ Hacim Onaylı | ATR Dinamik Stop\n"
                         f"----------------------------")
                send_telegram_message(mesaj)
                son_sinyal_zamanlari[symbol] = latest['timestamp']
                
                aktif_islemler[symbol] = {
                    'yon': 'SHORT',
                    'giris_fiyati': latest['close'],
                    'en_iyi_fiyat': latest['close'],
                    'hedef': take_profit,
                    'stop': stop_loss,
                    'atr': atr_degeri
                }
                
    except Exception as e:
        pass 
        
        son_update_id = 0

def telegram_emri_dinle():
    global son_update_id, aktif_islemler
    import os
    import requests
    
    # Render'a kaydettiğin şifreyi alıyoruz
    token = os.environ.get("GIZLI_TOKEN") 
    if not token:
        return
        
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    
    try:
        # Sadece yeni mesajları okumak için offset kullanıyoruz
        params = {'offset': son_update_id + 1, 'timeout': 1}
        cevap = requests.get(url, params=params).json()
        
        if cevap.get("ok") and cevap.get("result"):
            for mesaj in cevap["result"]:
                son_update_id = mesaj["update_id"]
                
                if "message" in mesaj and "text" in mesaj["message"]:
                    # Mesajı al ve büyük harfe çevir (Örn: /kapat btcusdt -> /KAPAT BTCUSDT)
                    metin = mesaj["message"]["text"].strip().upper() 
                    
                    if metin.startswith("/KAPAT"):
                        parcalar = metin.split()
                        if len(parcalar) == 2:
                            coin = parcalar[1] # Örn: BTCUSDT
                            
                            if coin in aktif_islemler:
                                del aktif_islemler[coin] # İşlemi hafızadan SİL!
                                try: send_telegram_message(f"🛠️ **MANUEL MÜDAHALE** 🛠️\n{coin} işlemi senin emrinle kapatıldı/silindi! Kasa rahatladı, boşluğu doldurmak için tarama başlatılıyor...")
                                except: pass
                            else:
                                try: send_telegram_message(f"⚠️ Hata: Sistemde {coin} adında açık bir işlem bulunamadı.")
                                except: pass
                        else:
                            try: send_telegram_message("⚠️ Hatalı komut! Doğru kullanım: /KAPAT BTCUSDT")
                            except: pass
    except Exception as e:
        pass # Hata olursa bot çökmesin, sessizce geçsin

# --- ANA DÖNGÜ (Güvenli Terminatör Modu - Anti-Ban) ---
if __name__ == "__main__":
    keep_alive() 
    
    print("🤖 HİBRİT BOT BAŞLATILDI. Telegram'a bağlanıyor...")
    try:
        send_telegram_message("🚀 **Sistem Başlatıldı!**\nGüvenli Terminatör Modu: Binance Anti-Spam koruması devrede. Kasa dolana kadar güvenli hızda (1.5s) taranacak.")
        print("✅ TELEGRAM BAŞARILI! Tarama başlıyor...")
    except Exception as e:
        print(f"❌ TELEGRAM HATASI! Render Environment ayarını kontrol et! Hata: {e}")
    
    TAKIP_ARALIGI = 30   
    ISLEM_LIMITI = 3
    
      while True:
        try:
            import time
            
            # 👇 İŞTE BURAYA EKLİYORUZ: Bot her döngüde önce senin bir emrin var mı diye baksın! 👇
            telegram_emri_dinle()
            
            mevcut_islem_sayisi = len(aktif_islemler)
            # ... (Kodunun geri kalanı aynı şekilde devam ediyor) ...

            # --- 1. AŞAMA: AÇIK İŞLEMLERİ TAKİP ET ---
            if aktif_islemler:
                for symbol in list(aktif_islemler.keys()):
                    aktif_islemi_takip_et(symbol)
                    # 🚨 ANTI-BAN KALKANI 1: Açık işlemleri sorgularken araya 1 saniye koy!
                    time.sleep(1) 
                    
            mevcut_islem_sayisi = len(aktif_islemler)
        
            # --- 2. AŞAMA: BOŞLUK VARSA "DURMADAN" TARAMA YAP ---
            if mevcut_islem_sayisi < ISLEM_LIMITI:
                guncel_coin_listesi = get_all_usdt_futures()
                toplam_coin = len(guncel_coin_listesi)
            
                try: send_telegram_message(f"\n🔄 **GÜVENLİ TARAMA BAŞLIYOR**\nBoş Kontenjan: {ISLEM_LIMITI - mevcut_islem_sayisi} | Hedef: Tüm Piyasa")
                except: pass
            
                tarama_sayaci = 0  
                son_takip_zamani = time.time() 
                
                for symbol in guncel_coin_listesi:
                    # Tarama esnasında açık işlemleri kontrol etme vakti geldiyse
                    if time.time() - son_takip_zamani >= TAKIP_ARALIGI:
                        if aktif_islemler:
                            for aktif_sym in list(aktif_islemler.keys()):
                                aktif_islemi_takip_et(aktif_sym)
                                # 🚨 ANTI-BAN KALKANI 2: Tarama içindeki takipte de 1 saniye bekle!
                                time.sleep(1)
                        son_takip_zamani = time.time()

                    if len(aktif_islemler) >= ISLEM_LIMITI:
                        try: send_telegram_message("🛑 **İşlem Limiti (3/3) Doldu!**\nTarama bıçak gibi kesildi. Bot açık işlemleri pusuda izleyecek.")
                        except: pass
                        break 
                        
                    if symbol not in aktif_islemler: 
                        analyze_and_signal(symbol)
                        # 🚨 ANTI-BAN KALKANI 3: Binance engellemesin diye ana tarama hızı 1.7 saniye yapıldı!
                        time.sleep(1.7) 
                        
                    tarama_sayaci += 1 
                    if tarama_sayaci % 50 == 0:
                        try: send_telegram_message(f"⏳ **ARA RAPOR:** {tarama_sayaci} / {toplam_coin} coin tarandı...")
                        except: pass
            
                import gc
                gc.collect()
                
            else:
                # --- 3. AŞAMA: LİMİT DOLUYSA SADECE PUSUDA BEKLE ---
                # Pusuya yattığında Binance'e hiç soru sormaz, sadece 30 saniye dinlenir.
                time.sleep(TAKIP_ARALIGI)

        except Exception as e:
            print(f"⚠️ Hata yakalandı, bot çökmekten kurtarıldı! Hata: {e}")
            import time
            time.sleep(10)

