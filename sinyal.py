import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time

# --- AYARLAR ---
TELEGRAM_TOKEN = "7968551890:AAFmtuxAvIEhpYVg7m8NL2TjROLQPgJxvzA"
CHAT_ID = "@rhksinyal"

# Botun hangi mumda mesaj attığını aklında tutması için hafıza
son_sinyal_zamanlari = {}

def analyze_and_signal(symbol):
    """Belirtilen coin için hafızalı analiz yapar"""
    print(f"🔍 {symbol} taranıyor...")
    
    try:
        # Verileri çek
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # RSI Hesapla
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        # Anlık/Hareketli muma (-1) bakıyoruz
        # ÖNEMLİ: Mumun kimlik numarası (zaman damgası) burasıdır
        latest_timestamp = df['timestamp'].iloc[-1] 
        latest_rsi = df['RSI'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        
        print(f"   -> Fiyat: {latest_close} | RSI: {latest_rsi:.2f}")

        # --- HAFIZALI SİNYAL MANTIĞI ---
        
        # 1. AL SİNYALİ (RSI <= 30)
        if latest_rsi <= 30:
            # Hafızayı Kontrol Et: Bu muma daha önce mesaj attık mı?
            if son_sinyal_zamanlari.get(symbol) != latest_timestamp:
                mesaj = f"🟢 **ERKEN AL SİNYALİ (DİP)**\n\nCoin: {symbol}\nFiyat: {latest_close}\nRSI: {latest_rsi:.2f}\nDurum: Anlık Aşırı Satım!"
                send_telegram_message(mesaj)
                print(f"   -> ✅ AL Sinyali gönderildi: {symbol}")
                
                # Mesajı attık, hafızayı güncelle (Artık bu mumu tanıyoruz)
                son_sinyal_zamanlari[symbol] = latest_timestamp
            else:
                print(f"   -> ⏳ {symbol} için bu mumda zaten mesaj atıldı. Bekleniyor.")

        # 2. SAT SİNYALİ (RSI >= 70)
        elif latest_rsi >= 70:
            # Hafızayı Kontrol Et: Bu muma daha önce mesaj attık mı?
            if son_sinyal_zamanlari.get(symbol) != latest_timestamp:
                mesaj = f"🔴 **ERKEN SAT SİNYALİ (TEPE)**\n\nCoin: {symbol}\nFiyat: {latest_close}\nRSI: {latest_rsi:.2f}\nDurum: Anlık Aşırı Alım!"
                send_telegram_message(mesaj)
                print(f"   -> ✅ SAT Sinyali gönderildi: {symbol}")
                
                # Mesajı attık, hafızayı güncelle
                son_sinyal_zamanlari[symbol] = latest_timestamp
            else:
                print(f"   -> ⏳ {symbol} için bu mumda zaten mesaj atıldı. Bekleniyor.")
                
    except Exception as e:
        print(f"   -> {symbol} analiz edilirken hata: {e}")

# İzlemek istediğiniz coinleri buraya ekleyebilirsiniz
SYMBOLS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "BIO/USDT"]

TIMEFRAME = "15m"  # 15 dakikalık mumlar
LIMIT = 200       # Analiz için geriye dönük 200 mum

# Binance bağlantısı
exchange = ccxt.binance()

def send_telegram_message(message):
    """Telegram'a mesaj gönderir"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Mesaj gönderme hatası: {e}")

def analyze_and_signal(symbol):
    """Belirtilen coin için analiz yapar"""
    print(f"🔍 {symbol} taranıyor...")
    
    try:
        # Verileri çek
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # RSI Hesapla
        df['RSI'] = ta.rsi(df['close'], length=14)
        
        # Son kapanmış muma bakıyoruz (Güvenli yöntem: -2)
        latest_rsi = df['RSI'].iloc[-1]
        latest_close = df['close'].iloc[-1]
        
        # Konsola bilgi yaz (Hata ayıklamak için)
        print(f"   -> Fiyat: {latest_close} | RSI: {latest_rsi:.2f}")

       # --- SİNYAL MANTIĞI ---
        if latest_rsi < 30:
            mesaj = f"🟢 **AL SİNYALİ (DİP)**\n\nCoin: {symbol}\nFiyat: {latest_close}\nRSI: {latest_rsi:.2f}\nDurum: Aşırı Satım Bölgesi!"
            send_telegram_message(mesaj)
            print(f"   -> AL Sinyali gönderildi: {symbol}")
            
        elif latest_rsi > 70:
            mesaj = f"🔴 **SAT SİNYALİ (TEPE)**\n\nCoin: {symbol}\nFiyat: {latest_close}\nRSI: {latest_rsi:.2f}\nDurum: Aşırı Alım Bölgesi!"
            send_telegram_message(mesaj)
            print(f"   -> SAT Sinyali gönderildi: {symbol}")
            
        else:
            # BURADAKİ {SYMBOL} YERİNE {symbol} KULLANDIK
            mesaj = f"ℹ️ **DURUM RAPORU**\nParite: {symbol} | Fiyat: {latest_close} | RSI: {latest_rsi:.2f}\nDurum: Piyasa normal, sinyal yok."
            send_telegram_message(mesaj)
            print(f"   -> {symbol} için durum raporu gönderildi.")
            
    except Exception as e:
        print(f"   -> {symbol} analiz edilirken hata: {e}")

# --- ANA DÖNGÜ ---
import traceback # En üste eklediğinden emin ol

# ... diğer fonksiyonların ...

# --- ANA DÖNGÜ ---
if __name__ == "__main__":
    try: # <--- İşte eksik olan bu!
        baslangic_mesaji = f"🚀 **BOT BAŞLATILDI**\nİzlenen Coin Sayısı: {len(SYMBOLS)}\n---------------------------------"
        print(baslangic_mesaji)
        send_telegram_message(baslangic_mesaji)
        
        while True:
            # Döngü başlarken ayırıcı bir mesaj atalım
            döngü_baslangic = "\n🔄 **YENİ TARAMA BAŞLIYOR**\n➖➖➖➖➖➖➖➖➖➖"
            print("--- Yeni Tarama Döngüsü Başlıyor ---")
            send_telegram_message(döngü_baslangic)
            
            # Listedeki her bir coini sırayla kontrol et
            for symbol in SYMBOLS:
                analyze_and_signal(symbol)
                time.sleep(1)
                
            # Döngü bittiğinde bilgi mesajı atalım
            döngü_bitis = "✅ **LİSTE TARANDI**\nBot 1 dakika dinleniyor...\n➖➖➖➖➖➖➖➖➖➖"
            print("Tüm liste tarandı. 1 dakika bekleniyor...")
            send_telegram_message(döngü_bitis)
            
            # Bekleme süresi
            time.sleep(60)

    except Exception as e:
        # Hata anında Telegram'a detaylı mesaj at
        hata_mesaji = f"🚨 **BOT ÇÖKTÜ!**\n\nHata Detayı:\n{traceback.format_exc()}"
        send_telegram_message(hata_mesaji)
        print(hata_mesaji)
        raise e # Botu tamamen durdur ki Railway restart atabilsin
