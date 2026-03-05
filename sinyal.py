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

app = Flask(__name__)

@app.route('/')
def home():
    return "🚀 Keskin Nişancı Botu 7/24 Aktif ve Çalışıyor!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- AYARLAR ---
TOKEN = os.environ.get("GIZLI_TOKEN", "HAYALET_AVCISI")
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
    """Gerçek Kırılımları ADX (Trend Gücü) ile Doğrulayan Bot"""
    
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
            
        df['BBL'] = bb.iloc[:, 0] 
        df['BBU'] = bb.iloc[:, 2] 
        
        df['EMA_100'] = ta.ema(df['close'], length=100)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['VOL_SMA'] = ta.sma(df['volume'], length=20) 
        
        # 🛡️ YENİ KALKAN: ADX (Trend Gücü Dedektörü)
        adx_df = ta.adx(df['high'], df['low'], df['close'], length=14)
        if adx_df is not None and not adx_df.empty:
            df['ADX'] = adx_df.iloc[:, 0] # ADX değerini alıyoruz
        else:
            return # ADX hesaplanamazsa pas geç
        
        previous = df.iloc[-2]
        latest = df.iloc[-1]
        
        if pd.isna(latest['ATR']) or pd.isna(latest['BBU']) or pd.isna(latest['EMA_100']) or pd.isna(latest['ADX']):
            return

        atr_degeri = latest['ATR']
        
        is_uptrend = latest['close'] > latest['EMA_100']
        is_downtrend = latest['close'] < latest['EMA_100']
        is_high_volume = latest['volume'] > latest['VOL_SMA']
        
        # 🛡️ ADX KURALI: Trend gücü 25'nin üzerindeyse bu gerçek bir harekettir! (Testere piyasasını eler)
        is_strong_trend = latest['ADX'] > 25

        # 🚀 GERÇEK MOMENTUM LONG
        if previous['close'] <= previous['BBU'] and latest['close'] > latest['BBU'] and is_uptrend and is_high_volume and is_strong_trend:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                
                stop_loss = latest['close'] - (atr_degeri * 1.5)
                take_profit = latest['close'] + (atr_degeri * 3.0)
                
                mesaj = (f"🚀 **GÜÇLÜ KIRILIM: LONG SİNYALİ**\n"
                         f"----------------------------\n"
                         f"Parite: {symbol}\n"
                         f"Giriş: {latest['close']:.4f}\n\n"
                         f"🎯 Hedef: {take_profit:.4f}\n"
                         f"🛑 Stop: {stop_loss:.4f}\n\n"
                         f"🛡️ ADX: {latest['ADX']:.1f} (Trend Güçlü)\n"
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
        
        # 🩸 GERÇEK ŞELALE SHORT
        elif previous['close'] >= previous['BBL'] and latest['close'] < latest['BBL'] and is_downtrend and is_high_volume and is_strong_trend:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                
                stop_loss = latest['close'] + (atr_degeri * 1.5)
                take_profit = latest['close'] - (atr_degeri * 3.0)
                
                mesaj = (f"🩸 **GÜÇLÜ KIRILIM: SHORT SİNYALİ**\n"
                         f"----------------------------\n"
                         f"Parite: {symbol}\n"
                         f"Giriş: {latest['close']:.4f}\n\n"
                         f"🎯 Hedef: {take_profit:.4f}\n"
                         f"🛑 Stop: {stop_loss:.4f}\n\n"
                         f"🛡️ ADX: {latest['ADX']:.1f} (Trend Güçlü)\n"
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

# --- ANA DÖNGÜ (Zamanlayıcı Motoru) ---
if __name__ == "__main__":
    keep_alive() 
    
    print("🤖 HİBRİT BOT BAŞLATILDI. Telegram'a bağlanıyor...")
    try:
        send_telegram_message("🚀 **Sistem Başlatıldı!**\nBollinger Momentum stratejisi ve Dinamik ATR Kalkanı ile tüm piyasa taranıyor.")
        print("✅ TELEGRAM BAŞARILI! Mesaj atıldı, tarama başlıyor...")
    except Exception as e:
        print(f"❌ TELEGRAM HATASI! Render Environment (GIZLI_TOKEN) ayarını kontrol et! Hata detayı: {e}")
    
    son_genel_tarama = 0
    TARAMA_ARALIGI = 300 
    TAKIP_ARALIGI = 15   
    
    while True:
        try:
            import time
            su_an = time.time()
            
            if aktif_islemler:
                for symbol in list(aktif_islemler.keys()):
                    aktif_islemi_takip_et(symbol)
        
            if su_an - son_genel_tarama >= TARAMA_ARALIGI:
                guncel_coin_listesi = get_all_usdt_futures()
                toplam_coin = len(guncel_coin_listesi)
            
                try: send_telegram_message(f"\n🔄 **YENİ TARAMA BAŞLIYOR**\nHedef: Tüm Piyasa ({toplam_coin} Coin)")
                except: pass
            
                tarama_sayaci = 0  
                for symbol in guncel_coin_listesi:
                    if symbol not in aktif_islemler: 
                        analyze_and_signal(symbol)
                        time.sleep(1.5) 
                        
                    tarama_sayaci += 1 
                    if tarama_sayaci % 50 == 0:
                        try: send_telegram_message(f"⏳ **ARA RAPOR:** {tarama_sayaci} / {toplam_coin} coin tarandı...")
                        except: pass
            
                try: send_telegram_message(f"✅ **TÜM PİYASA TARANDI ({toplam_coin} Coin)**\nBot açık işlemleri izliyor...")
                except: pass
                
                son_genel_tarama = time.time()
                import gc
                gc.collect()
        
            time.sleep(TAKIP_ARALIGI)

        except Exception as e:
            print(f"⚠️ Hata yakalandı, bot çökmekten kurtarıldı! Hata: {e}")
            import time
            time.sleep(10)
