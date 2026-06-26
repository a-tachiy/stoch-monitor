import streamlit as st
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
import pandas as pd
from datetime import datetime
import time
import altair as alt
import requests
from bs4 import BeautifulSoup

# ページ設定
st.set_page_config(
    page_title="リアルタイム株価監視ダッシュボード",
    page_icon="📈",
    layout="wide"
)

# カスタムCSSの追加 (モダンなUIのため)
st.markdown("""
<style>
    .stApp {
        background-color: #e6f3ff;
    }
    .metric-card {
        background-color: #1e1e1e;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        border: 1px solid #333;
    }
    .metric-title {
        color: #888;
        font-size: 14px;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #fff;
    }
    .metric-change {
        font-weight: bold;
    }
    .metric-change.positive {
        color: #4CAF50;
    }
    .metric-change.negative {
        color: #F44336;
    }
    .metric-change.neutral {
        color: #888;
    }
</style>
""", unsafe_allow_html=True)

# 監視対象銘柄の定義
STOCKS = [
    ("IMV", "7760.T"),
    ("塩水港精糖", "2112.T"),
    ("ソフトバンク", "9434.T"),
    ("東レ", "3402.T"),
    ("双日", "2768.T"),
    ("エスペック", "6859.T"),
    ("Cisco Systems", "CSCO"),
    ("PAYP", "PAYP")
]

# 1分(60000ミリ秒)ごとに自動リフレッシュ
count = st_autorefresh(interval=60000, limit=None, key="stock_autorefresh")

@st.cache_data(ttl=60) # 60秒間キャッシュ
def fetch_stock_data(ticker_symbol):
    """yfinanceを使用して株価データを取得する"""
    try:
        ticker = yf.Ticker(ticker_symbol)
        
        # yfinanceのhistory取得時に例外が出る場合があるのでリトライ
        for _ in range(3):
            try:
                hist = ticker.history(period="1d")
                if not hist.empty:
                    break
            except Exception:
                time.sleep(1)
        else:
             hist = pd.DataFrame() # リトライ失敗時は空のDataFrame

        if hist.empty:
            # データが取得できない場合（休場やエラーなど）
            # 直近のデータを取得してみる
            hist = ticker.history(period="5d")
            if hist.empty:
                return None
            
        # 最新のデータを取得
        current_data = hist.iloc[-1]
        
        # 現在値と当日高値
        current_price = float(current_data['Close'])
        daily_high = float(current_data['High'])
        
        # 前日終値を取得して前日比を計算
        info = ticker.info
        previous_close = info.get('previousClose', None)
        
        change_amount = 0.0
        if previous_close:
            change_amount = current_price - float(previous_close)
            change_percent = (change_amount / float(previous_close)) * 100
        else:
            # infoからpreviousCloseが取れない場合のフォールバック
            if len(hist) >= 2:
                previous_close_hist = float(hist.iloc[-2]['Close'])
                change_amount = current_price - previous_close_hist
                change_percent = (change_amount / previous_close_hist) * 100
            else:
                change_percent = 0.0
                
        # 日本株か米国株か為替かで通貨を判定
        currency = "¥" if ticker_symbol.endswith(".T") or ticker_symbol.endswith("JPY=X") else "$"
        
        # 当日のチャートデータを取得 (分足)
        try:
            hist_intra = ticker.history(period="1d", interval="5m")
            chart_data = hist_intra['Close'] if not hist_intra.empty else pd.Series()
        except Exception:
            chart_data = pd.Series()
        
        return {
            "current_price": current_price,
            "daily_high": daily_high,
            "change_amount": change_amount,
            "change_percent": change_percent,
            "currency": currency,
            "chart_data": chart_data,
            "previous_close": previous_close
        }
    except Exception as e:
        st.error(f"Error fetching data for {ticker_symbol}: {e}")
        return None

@st.cache_data(ttl=60) # 60秒キャッシュ
def fetch_bot_jpy_data():
    """台湾銀行のウェブサイトから日本円の為替レートを取得する"""
    url = "https://rate.bot.com.tw/xrt?Lang=zh-TW"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        rows = soup.find_all('tr')
        for row in rows:
            currency_div = row.find('div', class_='visible-phone')
            if currency_div and '日圓' in currency_div.text:
                cash_buy = row.find('td', {'data-table': '本行現金買入'})
                cash_sell = row.find('td', {'data-table': '本行現金賣出'})
                
                return {
                    "cash_buy": float(cash_buy.text.strip()) if cash_buy and cash_buy.text.strip() != '-' else None,
                    "cash_sell": float(cash_sell.text.strip()) if cash_sell and cash_sell.text.strip() != '-' else None,
                }
    except Exception as e:
        st.error(f"台湾銀行のデータ取得エラー: {e}")
    return None

# ヘッダーとコントロールパネル
col1, col2 = st.columns([3, 1])
with col1:
    st.title("📈 リアルタイム株価監視ダッシュボード")
with col2:
    st.write(f"最終更新: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if st.button("🔄 手動更新", use_container_width=True):
        st.cache_data.clear() # 手動更新時はキャッシュをクリア
        st.rerun()

st.markdown("---")

# ------------------ 為替レートセクション ------------------
st.subheader("💱 為替・両替情報")

# 3列で表示（USD/JPY, TWD/JPY, 台湾銀行 JPY）
col_cur1, col_cur2, col_cur3 = st.columns(3)

# 1. USD/JPY
with col_cur1:
    data = fetch_stock_data("USDJPY=X")
    if data:
        curr = data["currency"]
        price = data["current_price"]
        high = data["daily_high"]
        change_percent = data["change_percent"]
        change_amount = data["change_amount"]
        chart_data = data["chart_data"]
        prev_close = data["previous_close"]
        
        if change_amount > 0:
            change_class = "positive"
            change_str = f"▲ +{change_amount:,.2f}{curr} (+{change_percent:.2f}%)"
        elif change_amount < 0:
            change_class = "negative"
            change_str = f"▼ {change_amount:,.2f}{curr} ({change_percent:.2f}%)"
        else:
            change_class = "neutral"
            change_str = f"ー 0.00{curr} (0.00%)"
            
        prev_close_val = f"{curr}{float(prev_close):,.2f}" if prev_close else "不明"
        
        st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 5px; min-height: 180px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <div class="metric-title">USD/JPY (米ドル/日本円)</div>
                <div class="metric-value">{curr}{price:,.2f}</div>
                <div style="font-size: 14px; margin-top: 5px; color: #bbb;">
                    前日終値: {prev_close_val}
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 14px;">
                    <span style="color: #bbb;">高値: {curr}{high:,.2f}</span>
                    <span class="metric-change {change_class}">{change_str}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # チャート表示
        if not chart_data.empty:
            df_chart = chart_data.reset_index()
            df_chart.columns = ['Time', 'Price']
            line_color = '#4CAF50' if change_amount >= 0 else '#F44336'
            chart = alt.Chart(df_chart).mark_line(color=line_color).encode(
                x=alt.X('Time:T', axis=alt.Axis(title='時間', format='%H:%M')),
                y=alt.Y('Price:Q', scale=alt.Scale(zero=False), axis=alt.Axis(title='レート')),
                tooltip=[alt.Tooltip('Time:T', title='日時', format='%Y-%m-%d %H:%M'), alt.Tooltip('Price:Q', title='価格', format=',.2f')]
            ).properties(height=120).configure_view(strokeWidth=0)
            st.altair_chart(chart, use_container_width=True)
    else:
        st.error("USD/JPY のデータ取得に失敗しました")

# 2. TWD/JPY
with col_cur2:
    data = fetch_stock_data("TWDJPY=X")
    if data:
        curr = data["currency"]
        price = data["current_price"]
        high = data["daily_high"]
        change_percent = data["change_percent"]
        change_amount = data["change_amount"]
        chart_data = data["chart_data"]
        prev_close = data["previous_close"]
        
        if change_amount > 0:
            change_class = "positive"
            change_str = f"▲ +{change_amount:,.4f}{curr} (+{change_percent:.2f}%)"
        elif change_amount < 0:
            change_class = "negative"
            change_str = f"▼ {change_amount:,.4f}{curr} ({change_percent:.2f}%)"
        else:
            change_class = "neutral"
            change_str = f"ー 0.0000{curr} (0.00%)"
            
        prev_close_val = f"{curr}{float(prev_close):,.4f}" if prev_close else "不明"
        
        st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 5px; min-height: 180px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <div class="metric-title">TWD/JPY (台湾ドル/日本円)</div>
                <div class="metric-value">{curr}{price:,.4f}</div>
                <div style="font-size: 14px; margin-top: 5px; color: #bbb;">
                    前日終値: {prev_close_val}
                </div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 14px;">
                    <span style="color: #bbb;">高値: {curr}{high:,.4f}</span>
                    <span class="metric-change {change_class}">{change_str}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # チャート表示
        if not chart_data.empty:
            df_chart = chart_data.reset_index()
            df_chart.columns = ['Time', 'Price']
            line_color = '#4CAF50' if change_amount >= 0 else '#F44336'
            chart = alt.Chart(df_chart).mark_line(color=line_color).encode(
                x=alt.X('Time:T', axis=alt.Axis(title='時間', format='%H:%M')),
                y=alt.Y('Price:Q', scale=alt.Scale(zero=False), axis=alt.Axis(title='レート')),
                tooltip=[alt.Tooltip('Time:T', title='日時', format='%Y-%m-%d %H:%M'), alt.Tooltip('Price:Q', title='価格', format=',.4f')]
            ).properties(height=120).configure_view(strokeWidth=0)
            st.altair_chart(chart, use_container_width=True)
    else:
        st.error("TWD/JPY のデータ取得に失敗しました")

# 3. 台湾銀行 JPY (両替シミュレーター付き)
with col_cur3:
    bot_data = fetch_bot_jpy_data()
    if bot_data:
        buy_val = bot_data['cash_buy']
        sell_val = bot_data['cash_sell']
        
        # 両替シミュレーション計算
        twd_from_jpy = 10000 * buy_val if buy_val else 0.0
        jpy_from_twd = 1000 / sell_val if sell_val else 0.0
        
        buy_str = f"{buy_val:.4f}" if buy_val else "不明"
        sell_str = f"{sell_val:.4f}" if sell_val else "不明"
        
        st.markdown(f"""
        <div class="metric-card" style="margin-bottom: 5px; height: 310px; display: flex; flex-direction: column; justify-content: space-between;">
            <div>
                <div class="metric-title">台湾銀行 JPY (TWD/JPY 現金)</div>
                <div style="display: flex; justify-content: space-between; margin-top: 5px;">
                    <div>
                        <div style="font-size: 11px; color: #888;">本行現金買入 (現鈔)</div>
                        <div style="font-size: 20px; font-weight: bold; color: #4CAF50;">{buy_str}</div>
                    </div>
                    <div>
                        <div style="font-size: 11px; color: #888;">本行現金賣出 (現鈔)</div>
                        <div style="font-size: 20px; font-weight: bold; color: #F44336;">{sell_str}</div>
                    </div>
                </div>
                <div style="border-top: 1px solid #333; margin-top: 10px; padding-top: 10px;">
                    <div style="font-size: 12px; font-weight: bold; color: #aaa; margin-bottom: 5px;">両替シミュレーション</div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: #fff;">
                        <span>🇯🇵 10,000 円 ➔</span>
                        <span style="font-weight: bold; color: #4CAF50;">🇹🇼 {twd_from_jpy:,.1f} TWD</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 13px; color: #fff; margin-top: 3px;">
                        <span>🇹🇼 1,000 TWD ➔</span>
                        <span style="font-weight: bold; color: #F44336;">🇯🇵 {jpy_from_twd:,.0f} 円</span>
                    </div>
                </div>
            </div>
            <div style="text-align: center; margin-top: 10px;">
                <a href="https://rate.bot.com.tw/xrt?Lang=zh-TW" target="_blank" style="font-size: 12px; color: #0066cc; text-decoration: none;">台湾銀行 牌告匯率 🔗</a>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div class="metric-card" style="border-color: #f44336; opacity: 0.7; height: 310px; display: flex; flex-direction: column; justify-content: center; align-items: center;">
            <div class="metric-title">台湾銀行 JPY (TWD/JPY 現金)</div>
            <div style="color: #f44336; font-size: 18px;">データ取得エラー</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# ------------------ 監視対象株式セクション ------------------
st.subheader("📈 監視株式一覧")

# 4列でカード表示
cols = st.columns(4)

for i, (name, symbol) in enumerate(STOCKS):
    col_idx = i % 4
    
    with cols[col_idx]:
        data = fetch_stock_data(symbol)
        
        if data:
            curr = data["currency"]
            price = data["current_price"]
            high = data["daily_high"]
            change_percent = data["change_percent"]
            change_amount = data["change_amount"]
            chart_data = data["chart_data"]
            prev_close = data["previous_close"]
            
            # 変化率と変動額の色分け
            if change_amount > 0:
                change_class = "positive"
                change_str = f"▲ +{change_amount:,.2f}{curr} (+{change_percent:.2f}%)"
            elif change_amount < 0:
                change_class = "negative"
                change_str = f"▼ {change_amount:,.2f}{curr} ({change_percent:.2f}%)"
            else:
                change_class = "neutral"
                change_str = f"ー 0.00{curr} (0.00%)"
                
            # カードUIのレンダリング
            prev_close_val = f"{curr}{float(prev_close):,.2f}" if prev_close else "不明"
            st.markdown(f"""
            <div class="metric-card" style="margin-bottom: 5px; min-height: 180px; display: flex; flex-direction: column; justify-content: space-between;">
                <div>
                    <div class="metric-title">{name} ({symbol})</div>
                    <div class="metric-value">{curr}{price:,.2f}</div>
                    <div style="font-size: 14px; margin-top: 5px; color: #bbb;">
                        前日終値: {prev_close_val}
                    </div>
                    <div style="display: flex; justify-content: space-between; margin-top: 5px; font-size: 14px;">
                        <span style="color: #bbb;">高値: {curr}{high:,.2f}</span>
                        <span class="metric-change {change_class}">{change_str}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # チャート表示
            if not chart_data.empty:
                df_chart = chart_data.reset_index()
                df_chart.columns = ['Time', 'Price']
                line_color = '#4CAF50' if change_amount >= 0 else '#F44336'
                
                chart = alt.Chart(df_chart).mark_line(color=line_color).encode(
                    x=alt.X('Time:T', axis=alt.Axis(title='時間', format='%H:%M')),
                    y=alt.Y('Price:Q', scale=alt.Scale(zero=False), axis=alt.Axis(title='株価')),
                    tooltip=[alt.Tooltip('Time:T', title='日時', format='%Y-%m-%d %H:%M'), alt.Tooltip('Price:Q', title='価格', format=',.2f')]
                ).properties(
                    height=130
                ).configure_view(
                    strokeWidth=0
                )
                
                st.altair_chart(chart, use_container_width=True)
            else:
                st.caption("チャートデータがありません")
        else:
            # データ取得失敗時
            st.markdown(f"""
            <div class="metric-card" style="border-color: #f44336; opacity: 0.7; min-height: 180px; display: flex; flex-direction: column; justify-content: center; align-items: center;">
                <div class="metric-title">{name} ({symbol})</div>
                <div class="metric-value" style="color: #f44336; font-size: 18px;">データ取得エラー</div>
            </div>
            """, unsafe_allow_html=True)

# フッター
st.markdown("---")
st.caption("※ 自動更新は1分間隔で行われます。yfinanceのデータには遅延が含まれる場合があります。")

