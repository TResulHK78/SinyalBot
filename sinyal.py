import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import traceback

# --- AYARLAR ---
TELEGRAM_TOKEN = "7968551890:AAFmtuxAvIEhpYVg7m8NL2TjROLQPgJxvzA"
CHAT_ID = "@rhksinyal"
SYMBOLS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "USDC/USDT"]
TIMEFRAME = "15m"
LIMIT = 1000  # EMA 200 için en az 200-250 mum

# Bağlantılar
exchange = ccxt.binance()
son_sinyal_zamanlari = {}

def send_telegram_message(message):
    """Telegram'a mesaj gönderir"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Mesaj gönderme hatası: {e}")

def analyze_and_signal(symbol):
    """Tüm analiz, raporlama ve sinyal işlemlerini tek çatı altında yapar"""
    print(f"🔍 {symbol} taranıyor...")
    try:
        # Veri çek
        bars = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=LIMIT)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Göstergeleri Hesapla
        df['RSI'] = ta.rsi(df['close'], length=14)
        df['EMA_200'] = ta.ema(df['close'], length=200)
        df['VOL_SMA'] = ta.sma(df['volume'], length=20)
        
        latest = df.iloc[-1]
        is_uptrend = latest['close'] > latest['EMA_200']
        is_high_volume = latest['volume'] > latest['VOL_SMA']
        
        # 1. DURUM RAPORU (Her taramada atar)
        rapor_mesaji = (f"📊 *{symbol} Durum Raporu*\n"
                        f"----------------------------\n"
                        f"Fiyat: {latest['close']:.4f}\n"
                        f"RSI: {latest['RSI']:.2f}\n"
                        f"Trend: {'🟢 YUKARI' if is_uptrend else '🔴 AŞAĞI'}\n"
                        f"Hacim: {'💪 GÜÇLÜ' if is_high_volume else '📉 DÜŞÜK'}\n"
                        f"----------------------------")
        send_telegram_message(rapor_mesaji)

        # 2. SİNYAL KONTROLÜ (Sadece sinyal oluşursa atar)
        # AL SİNYALİ
        if latest['RSI'] <= 30 and is_uptrend and is_high_volume:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                mesaj = (f"🟢 **GÜÇLÜ AL SİNYALİ**\n"
                         f"----------------------------\n"
                         f"Coin: {symbol}\n"
                         f"Fiyat: {latest['close']:.4f}\n"
                         f"RSI: {latest['RSI']:.2f} (Aşırı Satım)\n"
                         f"Trend: YUKARI (EMA200 üstü)\n"
                         f"Hacim: GÜÇLÜ (Ort. Üstü)\n"
                         f"----------------------------")
                send_telegram_message(mesaj)
                son_sinyal_zamanlari[symbol] = latest['timestamp']
        
        # SAT SİNYALİ
        elif latest['RSI'] >= 70 and not is_uptrend and is_high_volume:
            if son_sinyal_zamanlari.get(symbol) != latest['timestamp']:
                mesaj = (f"🔴 **GÜÇLÜ SAT SİNYALİ**\n"
                         f"----------------------------\n"
                         f"Coin: {symbol}\n"
                         f"Fiyat: {latest['close']:.4f}\n"
                         f"RSI: {latest['RSI']:.2f} (Aşırı Alım)\n"
                         f"Trend: AŞAĞI (EMA200 altı)\n"
                         f"Hacim: GÜÇLÜ (Ort. Üstü)\n"
                         f"----------------------------")
                send_telegram_message(mesaj)
                son_sinyal_zamanlari[symbol] = latest['timestamp']
                
    except Exception as e:
        print(f"Analiz hatası ({symbol}): {e}")

# --- ANA DÖNGÜ ---
if __name__ == "__main__":
    try:
        baslangic_mesaji = f"🚀 **BOT BAŞLATILDI**\nİzlenen Coin Sayısı: {len(SYMBOLS)}\n---------------------------------"
        print(baslangic_mesaji)
        send_telegram_message(baslangic_mesaji)
        
        while True:
            # Döngü başlarken bildirim
            döngü_baslangic = "\n🔄 **YENİ TARAMA BAŞLIYOR**\n➖➖➖➖➖➖➖➖➖➖"
            print("--- Yeni Tarama Döngüsü Başlıyor ---")
            send_telegram_message(döngü_baslangic)
            
            for symbol in SYMBOLS:
                analyze_and_signal(symbol)
                time.sleep(1) # API limitleri için kısa bekleme
                
            # Döngü biterken bildirim
            döngü_bitis = "✅ **LİSTE TARANDI**\nBot 5 dakika dinleniyor...\n➖➖➖➖➖➖➖➖➖➖"
            print("Tüm liste tarandı. 300 saniye bekleniyor...")
            send_telegram_message(döngü_bitis)
            
            time.sleep(300)

    except Exception as e:
        hata_mesaji = f"🚨 **BOT ÇÖKTÜ!**\n\nHata Detayı:\n{traceback.format_exc()}"
        send_telegram_message(hata_mesaji)
        print(hata_mesaji)
        raise e


