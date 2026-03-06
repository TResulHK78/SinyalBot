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

def analyze_and_signal(symbol):
    try:
        # 1. VERİ ÇEKME
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=250)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 🚨 KAPANMAMIŞ MUMU ÇÖPE AT! (Sahte sinyal tuzağı iptal)
        df = df[:-1]

        # 2. İNDİKATÖR HESAPLAMALARI
        bbands = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bbands], axis=1)
        
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ema'] = ta.ema(df['close'], length=200) # Uzun vade
        df['sma'] = ta.sma(df['close'], length=50)  # Orta vade
        df['rsi'] = ta.rsi(df['close'], length=14)
        
        # 🚨 YENİ FİLTRE: HACİM ORTALAMASI (Sahte kırılımları avlamak için)
        df['vol_sma'] = ta.sma(df['volume'], length=20)

        # Güncel verileri çek
        son_mum = df.iloc[-1]
        bir_onceki_mum = df.iloc[-2]

        kapanis = son_mum['close']
        ust_bant = son_mum['BBU_20_2.0']
        alt_bant = son_mum['BBL_20_2.0']
        atr = son_mum['atr']
        rsi = son_mum['rsi']
        ema = son_mum['ema']
        sma = son_mum['sma']
        hacim = son_mum['volume']
        ort_hacim = son_mum['vol_sma']

        # Veri eksikse atla
        if pd.isna(atr) or pd.isna(ust_bant) or pd.isna(ema) or pd.isna(ort_hacim):
            return

        # 3. KESKİN NİŞANCI SİNYAL ONAYI (Aşama Aşama Filtreler)
        
        # 🟢 LONG (ALIM) ŞARTLARI 🟢
        # 1. Bollinger Kırılımı:
        bollinger_long = kapanis > ust_bant and bir_onceki_mum['close'] <= bir_onceki_mum['BBU_20_2.0']
        # 2. Trend Onayı (50 SMA, 200 EMA'nın üzerinde olacak ve fiyat da bunların üstünde olacak):
        trend_long = sma > ema and kapanis > sma
        # 3. Hacim Onayı (Patlama şart! Hacim, ortalamanın %50 üzerinde olmalı):
        hacim_long = hacim > (ort_hacim * 1.5)
        # 4. RSI Onayı (RSI 50'den büyük olup momentumu doğrulamalı, ama 75'i geçip şişmiş olmamalı):
        rsi_long = 50 < rsi < 75

        if bollinger_long and trend_long and hacim_long and rsi_long:
            stop_loss = kapanis - (atr * 2.0) 
            take_profit = kapanis + (atr * 3.0) 
            
            aktif_islemler[symbol] = {
                'yon': 'LONG',
                'giris': kapanis,
                'stop': stop_loss,
                'hedef': take_profit,
                'zaman': time.time()
            }
            
            mesaj = f"🟢 **YENİ İŞLEM (LONG)** 🟢\n\n📌 Coin: {symbol}\n💰 Giriş: {kapanis}\n🛡️ Stop Loss: {stop_loss:.4f}\n🎯 Hedef (TP): {take_profit:.4f}\n📊 RSI: {rsi:.1f}\n🚀 Durum: Yüksek Hacim & Trend Onaylı!"
            send_telegram_message(mesaj)

        # 🔴 SHORT (SATIŞ) ŞARTLARI 🔴
        bollinger_short = kapanis < alt_bant and bir_onceki_mum['close'] >= bir_onceki_mum['BBL_20_2.0']
        trend_short = sma < ema and kapanis < sma
        hacim_short = hacim > (ort_hacim * 1.5)
        rsi_short = 25 < rsi < 50

        if bollinger_short and trend_short and hacim_short and rsi_short:
            stop_loss = kapanis + (atr * 2.0)
            take_profit = kapanis - (atr * 3.0)
            
            aktif_islemler[symbol] = {
                'yon': 'SHORT',
                'giris': kapanis,
                'stop': stop_loss,
                'hedef': take_profit,
                'zaman': time.time()
            }
            
            mesaj = f"🔴 **YENİ İŞLEM (SHORT)** 🔴\n\n📌 Coin: {symbol}\n💰 Giriş: {kapanis}\n🛡️ Stop Loss: {stop_loss:.4f}\n🎯 Hedef (TP): {take_profit:.4f}\n📊 RSI: {rsi:.1f}\n🚀 Durum: Yüksek Hacim & Trend Onaylı!"
            send_telegram_message(mesaj)

    except Exception as e:
        pass

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

