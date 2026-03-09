import ccxt
import pandas as pd
import pandas_ta as ta
import requests
import time
import os
import gc
from flask import Flask
from threading import Thread

# --- FLASK (SUNUCU UYUTMAMA) AYARLARI ---
app = Flask('')

@app.route('/')
def home():
    return "🚀 Bot Canavar Gibi Ayakta!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- BOT GENEL AYARLARI ---
TELEGRAM_TOKEN = os.environ.get("GIZLI_TOKEN", "HAYALET_AVCISI")
CHAT_ID = "@rhksinyal"
MAX_ACIK_ISLEM = 3  

# --- BORSAYA BAĞLANTI (BİNANCE FUTURES) ---
exchange = ccxt.binance({
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# --- BOT HAFIZASI ---
aktif_islemler = {}  
son_update_id = 0

# --- YARDIMCI FONKSİYONLAR ---
def send_telegram_message(message):
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "HAYALET_AVCISI": return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        pass

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
        hata_metni = str(e)
        if "418" in hata_metni or "banned" in hata_metni.lower():
            send_telegram_message("🛑 **BİNANCE IP BANI DEVREDE!**\nBinance çok fazla istekten dolayı IP'yi engelledi. Spam döngüsüne girmemek için bot **15 Dakika** uykuya alınıyor...")
            time.sleep(900) 
        else:
            send_telegram_message(f"⚠️ Coin listesi çekilemedi, 1 dakika bekleniyor...\nDetay: {e}")
            time.sleep(60)
        return [] # Hata varsa boş liste döndür ki bot fren yapsın

# --- MANUEL ÖZEL ANALİZ ---
def ozel_analiz_yap(symbol):
    try:
        if symbol not in exchange.markets:
            kisa_ad = symbol.split("/")[0]
            send_telegram_message(f"⚠️ Hata: {kisa_ad} coini Binance Vadeli İşlemler'de (Futures) bulunmuyor.")
            return

        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=150)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df[:-1]

        bbands = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bbands], axis=1)
        df['ema'] = ta.ema(df['close'], length=99)
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['vol_sma'] = ta.sma(df['volume'], length=20)

        bbu_sutun = [c for c in df.columns if 'BBU' in c][0]
        bbl_sutun = [c for c in df.columns if 'BBL' in c][0]

        son_mum = df.iloc[-1]
        
        kapanis = float(son_mum['close'])
        ust_bant = float(son_mum[bbu_sutun])
        alt_bant = float(son_mum[bbl_sutun])
        rsi = float(son_mum['rsi'])
        ema = float(son_mum['ema'])
        hacim = float(son_mum['volume'])
        ort_hacim = float(son_mum['vol_sma'])

        trend_yonu = "🟢 YÜKSELİŞ" if kapanis > ema else "🔴 DÜŞÜŞ"
        hacim_durumu = "✅ Yeterli" if hacim > (ort_hacim * 1.2) else "❌ Yetersiz"
        
        mesafe_ust = ust_bant - kapanis
        mesafe_alt = kapanis - alt_bant

        if kapanis > ema:
            if kapanis > ust_bant: durum_yorumu = "🔥 Üst bant kırılmış! LONG eğilimli ancak RSI şişkinliğine dikkat et."
            elif mesafe_ust < mesafe_alt: durum_yorumu = "📈 Fiyat üst banda yakın. Trend yukarı olduğu için LONG'a daha yakın."
            else: durum_yorumu = "⏳ Fiyat dinleniyor. Ancak trend yükselişte olduğu için yön LONG eğilimli."
        else:
            if kapanis < alt_bant: durum_yorumu = "💥 Alt bant kırılmış! SHORT eğilimli ancak dipten dönme riskine dikkat et."
            elif mesafe_alt < mesafe_ust: durum_yorumu = "📉 Fiyat alt banda yakın. Trend aşağı olduğu için SHORT'a daha yakın."
            else: durum_yorumu = "⏳ Fiyat dinleniyor. Ancak trend düşüşte olduğu için yön SHORT eğilimli."

        mesaj = f"🔎 **{symbol} ÖZEL ANALİZ RAPORU** 🔎\n\n💰 **Fiyat:** {kapanis:.4f}\n📊 **Trend (EMA99):** {trend_yonu}\n📈 **RSI:** {rsi:.1f} (İdeal: 30-70)\n🌊 **Hacim:** {hacim_durumu}\n\n🎯 **Bantlar:**\nÜst: {ust_bant:.4f} | Alt: {alt_bant:.4f}\n\n🤖 **Yorum:** {durum_yorumu}"
        send_telegram_message(mesaj)
        
    except Exception as e:
        send_telegram_message(f"⚠️ {symbol} için analiz sırasında bir sorun oluştu.\n**Gizli Hata:** `{e}`")

# --- İŞLEM TAKİP FONKSİYONU (SESSİZ MOD) ---
def aktif_islemi_takip_et(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        guncel_fiyat = ticker['last']
        
        islem = aktif_islemler[symbol]
        yon = islem['yon']
        giris = islem['giris'] 
        atr = islem['atr'] 
        
        kar_koruma_hedefi = 1.0 * atr  
        kar_koruma_esnekligi = 0.5 * atr 
        
        if yon == 'LONG':
            if guncel_fiyat > islem['en_iyi_fiyat']:
                aktif_islemler[symbol]['en_iyi_fiyat'] = guncel_fiyat
            en_iyi = aktif_islemler[symbol]['en_iyi_fiyat']
            
            if guncel_fiyat >= islem['hedef']:
                send_telegram_message(f"🎯 **HEDEFE ULAŞILDI! (LONG)** 🎯\n{symbol} Kâr Hedefi Vuruldu!\n👉 İşlemi kapatın!")
                del aktif_islemler[symbol] 
            elif guncel_fiyat <= islem['stop']:
                send_telegram_message(f"🛑 **STOP PATLADI (LONG)**\n{symbol} Stop seviyesine değdi.\n👉 İşlemi kapatın.")
                del aktif_islemler[symbol]
            elif en_iyi >= giris + kar_koruma_hedefi: 
                if guncel_fiyat <= en_iyi - kar_koruma_esnekligi: 
                    send_telegram_message(f"⚠️ **KÂRI AL VE KAÇ! (LONG)**\n{symbol} dönüşe geçti.\n👉 Kârı korumak için işlemi kapatın!")
                    del aktif_islemler[symbol]

        elif yon == 'SHORT':
            if guncel_fiyat < islem['en_iyi_fiyat']:
                aktif_islemler[symbol]['en_iyi_fiyat'] = guncel_fiyat
            en_iyi = aktif_islemler[symbol]['en_iyi_fiyat']
            
            if guncel_fiyat <= islem['hedef']:
                send_telegram_message(f"🎯 **HEDEFE ULAŞILDI! (SHORT)** 🎯\n{symbol} Kâr Hedefi Vuruldu!\n👉 İşlemi kapatın!")
                del aktif_islemler[symbol]
            elif guncel_fiyat >= islem['stop']:
                send_telegram_message(f"🛑 **STOP PATLADI (SHORT)**\n{symbol} Stop seviyesine değdi.\n👉 İşlemi kapatın.")
                del aktif_islemler[symbol]
            elif en_iyi <= giris - kar_koruma_hedefi:
                if guncel_fiyat >= en_iyi + kar_koruma_esnekligi:
                    send_telegram_message(f"⚠️ **KÂRI AL VE KAÇ! (SHORT)**\n{symbol} yükselişe geçti.\n👉 Kârı korumak için işlemi kapatın!")
                    del aktif_islemler[symbol]

    except Exception as e:
        pass 

# --- TARAMA VE SİNYAL FONKSİYONU ---
def analyze_and_signal(symbol):
    try:
        bars = exchange.fetch_ohlcv(symbol, timeframe='15m', limit=150)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        for c in ['open', 'high', 'low', 'close', 'volume']:
            df[c] = pd.to_numeric(df[c], errors='coerce')
        df = df[:-1]

        bbands = ta.bbands(df['close'], length=20, std=2)
        df = pd.concat([df, bbands], axis=1)
        
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['ema'] = ta.ema(df['close'], length=99)  
        df['sma'] = ta.sma(df['close'], length=50)  
        df['rsi'] = ta.rsi(df['close'], length=14)
        df['vol_sma'] = ta.sma(df['volume'], length=20)

        bbu_sutun = [c for c in df.columns if 'BBU' in c][0]
        bbl_sutun = [c for c in df.columns if 'BBL' in c][0]

        son_mum = df.iloc[-1]
        bir_onceki_mum = df.iloc[-2]

        kapanis = float(son_mum['close'])
        ust_bant = float(son_mum[bbu_sutun])
        alt_bant = float(son_mum[bbl_sutun])
        atr = float(son_mum['atr'])
        rsi = float(son_mum['rsi'])
        ema = float(son_mum['ema'])
        hacim = float(son_mum['volume'])
        ort_hacim = float(son_mum['vol_sma'])

        if pd.isna(atr) or pd.isna(ust_bant) or pd.isna(ema) or pd.isna(ort_hacim):
            return

        bollinger_long = kapanis > ust_bant and float(bir_onceki_mum['close']) <= float(bir_onceki_mum[bbu_sutun])
        trend_long = kapanis > ema 
        hacim_long = hacim > (ort_hacim * 1.2)
        rsi_long = rsi < 75

        if bollinger_long and trend_long and hacim_long and rsi_long:
            stop_loss = kapanis - (atr * 2.0) 
            take_profit = kapanis + (atr * 3.0) 
            
            aktif_islemler[symbol] = {
                'yon': 'LONG',
                'giris': kapanis,
                'en_iyi_fiyat': kapanis,
                'stop': stop_loss,
                'hedef': take_profit,
                'atr': atr,
                'zaman': time.time()
            }
            send_telegram_message(f"🟢 **YENİ İŞLEM (LONG)** 🟢\n📌 Coin: {symbol}\n💰 Giriş: {kapanis:.4f}\n🛡️ Stop: {stop_loss:.4f}\n🎯 Hedef: {take_profit:.4f}\n📊 RSI: {rsi:.1f}")

        bollinger_short = kapanis < alt_bant and float(bir_onceki_mum['close']) >= float(bir_onceki_mum[bbl_sutun])
        trend_short = kapanis < ema 
        hacim_short = hacim > (ort_hacim * 1.2)
        rsi_short = rsi > 25

        if bollinger_short and trend_short and hacim_short and rsi_short:
            stop_loss = kapanis + (atr * 2.0)
            take_profit = kapanis - (atr * 3.0)
            
            aktif_islemler[symbol] = {
                'yon': 'SHORT',
                'giris': kapanis,
                'en_iyi_fiyat': kapanis,
                'stop': stop_loss,
                'hedef': take_profit,
                'atr': atr,
                'zaman': time.time()
            }
            send_telegram_message(f"🔴 **YENİ İŞLEM (SHORT)** 🔴\n📌 Coin: {symbol}\n💰 Giriş: {kapanis:.4f}\n🛡️ Stop: {stop_loss:.4f}\n🎯 Hedef: {take_profit:.4f}\n📊 RSI: {rsi:.1f}")

    except Exception as e:
        pass

# --- TELEGRAM KULAKLIĞI ---
def telegram_emri_dinle():
    global son_update_id, aktif_islemler
    if not TELEGRAM_TOKEN or TELEGRAM_TOKEN == "HAYALET_AVCISI": return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    
    try:
        cevap = requests.get(url, params={'offset': son_update_id + 1, 'timeout': 1}).json()
        if cevap.get("ok") and cevap.get("result"):
            for guncelleme in cevap["result"]:
                son_update_id = guncelleme["update_id"]
                
                mesaj_data = guncelleme.get("message") or guncelleme.get("channel_post")
                if not mesaj_data or "text" not in mesaj_data:
                    continue 
                    
                metin = mesaj_data["text"].strip().upper() 
                
                if metin.startswith("/KAPAT"):
                    parcalar = metin.split()
                    if len(parcalar) >= 2:
                        hedef = parcalar[1].replace("USDT", "").replace("/", "").replace(":", "")
                        silinecek_key = next((k for k in aktif_islemler.keys() if k.startswith(hedef + "/")), None)
                        
                        if silinecek_key:
                            del aktif_islemler[silinecek_key]
                            send_telegram_message(f"🛠️ **MANUEL MÜDAHALE** 🛠️\n{silinecek_key} kapatıldı! Kasa rahatladı.")
                        else:
                            mevcut_liste = ", ".join(aktif_islemler.keys()) if aktif_islemler else "Açık işlem yok."
                            send_telegram_message(f"⚠️ Hata: Sistemde '{parcalar[1]}' adında bir işlem yok.\n📌 Açıklar: {mevcut_liste}")
                            
                elif metin.startswith("/ANALIZ") or metin.startswith("/BAK"):
                    parcalar = metin.split()
                    if len(parcalar) >= 2:
                        hedef = parcalar[1].replace("USDT", "").replace("/", "").replace(":", "")
                        aranan_symbol = f"{hedef}/USDT:USDT"
                        send_telegram_message(f"⏳ {hedef} grafikleri inceleniyor...")
                        ozel_analiz_yap(aranan_symbol)
    except Exception as e:
        pass 

# --- ANA DÖNGÜ (HAYALET MODU) ---
if __name__ == "__main__":
    keep_alive() 
    print("🤖 HİBRİT BOT BAŞLATILDI. Telegram'a bağlanıyor...")
    try:
        send_telegram_message("🚀 **Sistem Başlatıldı! (Sessiz Hayalet Modu)**\nAnti-Ban kalkanı devrede.\n`/kapat COIN` ile işlem silebilir, `/analiz COIN` ile piyasa özeti alabilirsiniz.")
    except Exception as e:
        print(f"❌ TELEGRAM HATASI! {e}")
    
    TAKIP_ARALIGI = 15   
    
    while True:
        try:
            telegram_emri_dinle()
            
            # --- 1. AŞAMA: AÇIK İŞLEMLERİ TAKİP ET ---
            if aktif_islemler:
                for symbol in list(aktif_islemler.keys()):
                    aktif_islemi_takip_et(symbol)
                    time.sleep(2) # 🚨 ANTİ-BAN: Takipler arası 2 saniye nefes
                    
            # --- 2. AŞAMA: BOŞLUK VARSA TARAMA YAP ---
            if len(aktif_islemler) < MAX_ACIK_ISLEM:
                guncel_coin_listesi = get_all_usdt_futures()
                
                # 🚨 FREN: Eğer liste boş döndüyse (IP ban) başa dön ve uykuya geç
                if not guncel_coin_listesi:
                    continue
                
                try: send_telegram_message(f"\n🔄 **TARAMA BAŞLIYOR** | Boş Yer: {MAX_ACIK_ISLEM - len(aktif_islemler)}")
                except: pass
            
                son_takip = time.time() 
                
                for symbol in guncel_coin_listesi:
                    if time.time() - son_takip >= TAKIP_ARALIGI:
                        telegram_emri_dinle() 
                        if aktif_islemler:
                            for aktif_sym in list(aktif_islemler.keys()):
                                aktif_islemi_takip_et(aktif_sym)
                                time.sleep(2)
                        son_takip = time.time()

                    if len(aktif_islemler) >= MAX_ACIK_ISLEM:
                        break 
                        
                    if symbol not in aktif_islemler: 
                        analyze_and_signal(symbol)
                        time.sleep(3) # 🚨 ANTİ-BAN: Tarama hızı düşürüldü (3 saniye)
            
                gc.collect()
            else:
                # --- 3. AŞAMA: LİMİT DOLUYSA BEKLE ---
                time.sleep(TAKIP_ARALIGI)

        except Exception as e:
            print(f"⚠️ Hata yakalandı! Hata: {e}")
            time.sleep(10)
