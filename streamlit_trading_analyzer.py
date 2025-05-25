import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Dict
import requests

def calculate_average_purchase_price(df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    df = df.copy()
    df['取引金額'] = df['数量'] * df['価格']
    df = df.sort_index()  # 時系列順に並んでいる前提

    results = {}

    for currency_pair in df['通貨ペア'].unique():
        pair_data = df[df['通貨ペア'] == currency_pair].copy()
        pair_data = pair_data.reset_index(drop=True)

        buys = []
        remaining_quantity = 0.0

        for idx, row in pair_data.iterrows():
            qty = row['数量']
            price = row['価格']
            amount = row['取引金額']
            side = row['売/買'].lower()

            if side == 'buy':
                # 残量付きで記録
                buys.append({'quantity': qty, 'price': price, 'amount': amount})
                remaining_quantity += qty
            elif side == 'sell':
                sell_qty = qty
                remaining_quantity -= sell_qty
                # FIFOで消化
                i = 0
                while sell_qty > 0 and i < len(buys):
                    buy = buys[i]
                    if buy['quantity'] <= sell_qty:
                        # 全部消費
                        sell_qty -= buy['quantity']
                        buys.pop(i)
                    else:
                        # 一部消費
                        buy['quantity'] -= sell_qty
                        buy['amount'] = buy['quantity'] * buy['price']
                        sell_qty = 0

        # 残っている分で平均を計算
        remaining_total_qty = sum(b['quantity'] for b in buys)
        remaining_total_amount = sum(b['amount'] for b in buys)
        average_price = remaining_total_amount / remaining_total_qty if remaining_total_qty > 0 else 0

        buy_data = pair_data[pair_data['売/買'].str.lower() == 'buy']
        sell_data = pair_data[pair_data['売/買'].str.lower() == 'sell']

        results[currency_pair] = {
            'average_purchase_price': round(average_price, 2),
            'total_purchase_quantity': round(sum(b['quantity'] for b in buys), 8),
            'total_purchase_amount': round(sum(b['amount'] for b in buys), 2),
            'purchase_count': len(buy_data),
            'sell_count': len(sell_data),
            'total_transactions': len(pair_data),
            'min_price': round(pair_data['価格'].min(), 2),
            'max_price': round(pair_data['価格'].max(), 2),
            'current_holdings': round(remaining_total_qty, 8)
        }

    return results

def create_summary_dataframe(results: Dict[str, Dict[str, float]]) -> pd.DataFrame:
    summary_data = []
    for currency_pair, stats in results.items():
        base_currency = currency_pair.split('_')[0].upper()
        summary_data.append({
            '通貨ペア': currency_pair.upper(),
            '平均購入単価': f"¥{stats['average_purchase_price']:,.0f}",
            '購入数量合計': f"{stats['total_purchase_quantity']:.8f} {base_currency}",
            '購入金額合計': f"¥{stats['total_purchase_amount']:,.0f}",
            '現在保有量': f"{stats['current_holdings']:.8f} {base_currency}",
            '購入回数': f"{stats['purchase_count']}回",
            '売却回数': f"{stats['sell_count']}回",
            '価格レンジ': f"¥{stats['min_price']:,.0f} - ¥{stats['max_price']:,.0f}",
            '現在価格': f"¥{stats.get('current_price', 0):,.0f}" if stats.get('current_price') else "取得失敗",
            '評価額': f"¥{stats.get('valuation', 0):,.0f}"
        })
    return pd.DataFrame(summary_data)

def create_charts(results: Dict[str, Dict[str, float]], df: pd.DataFrame):
    currency_pairs = list(results.keys())
    
    holdings_value = []
    labels = []
    for pair in currency_pairs:
        stats = results[pair]
        value = stats['current_holdings'] * stats['average_purchase_price']
        if value > 0:
            holdings_value.append(value)
            labels.append(pair.upper())
    
    fig_pie = px.pie(values=holdings_value, names=labels, title="現在保有資産の分布（購入単価ベース）") if holdings_value else None

    df['取引金額'] = df['数量'] * df['価格']
    fig_scatter = px.scatter(
        df,
        x='数量',
        y='価格',
        color='通貨ペア',
        size='取引金額',
        title="取引の価格と数量の関係",
        labels={'数量': '数量', '価格': '価格 (¥)'},
        hover_data=['取引金額']
    )
    
    return fig_pie, fig_scatter

def fetch_current_prices(pairs):
    prices = {}
    for pair in pairs:
        try:
            response = requests.get(f"https://public.bitbank.cc/{pair}/ticker")
            response.raise_for_status()
            data = response.json()
            prices[pair] = float(data['data']['last'])
        except Exception as e:
            prices[pair] = None
    return prices

def main():
    st.set_page_config(page_title="仮想通貨利益計算アプリ", page_icon="₿", layout="wide")
    st.title("₿ 仮想通貨利益計算アプリ")
    st.markdown("**平均購入単価**を正確に算出し、投資パフォーマンスを分析します")
    st.markdown("---")
    
    st.sidebar.header("📁 ファイルアップロード")
    uploaded_file = st.sidebar.file_uploader("取引履歴CSVファイルを選択してください", type=['csv'])

    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)

            results = calculate_average_purchase_price(df)

            # 現在価格と評価額計算後に利益金額を計算
            for pair, stats in results.items():
                purchase = stats.get('total_purchase_amount', 0.0)
                valuation = stats.get('valuation', 0.0)
                profit = valuation - purchase
                stats['profit'] = round(profit, 2)

            # 現在価格の取得
            current_prices = fetch_current_prices(results.keys())

            # 評価額計算
            for pair, stats in results.items():
                current_price = current_prices.get(pair)
                if current_price is not None:
                    results[pair]['current_price'] = round(current_price, 2)
                    results[pair]['valuation'] = round(current_price * stats['current_holdings'], 2)
                else:
                    results[pair]['current_price'] = None
                    results[pair]['valuation'] = 0.0


            st.subheader("💰 合計")
            # cols = st.columns(5)
            total_current_purchase_amount = sum(stats['total_purchase_amount'] for stats in results.values())
            total_valuation = sum(stats.get('valuation', 0.0) for stats in results.values())

            st.metric(
                label="現在の評価額合計",
                value=f"¥{total_valuation:,.0f}",
                delta=round((total_valuation - total_current_purchase_amount), 0),  # 利益
                delta_color="normal"  # 正なら緑、負なら赤に自動対応
            )
            st.metric("合計購入金額", f"¥{total_current_purchase_amount:,.0f}")

            st.subheader("📊 現在評価＆利益額")
            cols = st.columns(len(results))
            for i, (currency_pair, stats) in enumerate(results.items()):
                if i < len(cols):
                    purchase_amount = stats['total_purchase_amount']
                    valuation = stats.get('valuation', 0.0)
                    profit = round(valuation - purchase_amount, 0)
                    with cols[i]:
                        st.metric(
                            label=f"{currency_pair.upper()} 評価＆利益額",
                            value=f"¥{stats.get('valuation', 0):,.0f}",  # 評価額
                            delta=profit,       # 利益
                            delta_color="normal"                          # 正なら緑、負なら赤に自動対応
                        )

            cols = st.columns(len(results))
            for i, (currency_pair, stats) in enumerate(results.items()):
                if i < len(cols):
                    with cols[i]:
                        st.metric(
                            label=f"{currency_pair.upper()} 購入金額",
                            value=f"¥{stats['total_purchase_amount']:,.0f}"
                        )

            st.subheader("📈 平均購入単価")
            cols = st.columns(len(results))
            for i, (currency_pair, stats) in enumerate(results.items()):
                if i < len(cols):
                    base_currency = currency_pair.split('_')[0].upper()
                    with cols[i]:
                        st.metric(
                            f"{base_currency} 平均購入単価",
                            f"¥{stats['average_purchase_price']:,.0f}",
                            help=f"購入数量: {stats['total_purchase_quantity']:.8f} {base_currency}"
                        )

            st.subheader("🎯 平均購入単価サマリー")
            summary_df = create_summary_dataframe(results)
            st.dataframe(summary_df, use_container_width=True)


            st.header("📊 データ可視化")
            fig_pie, _ = create_charts(results, df)

            col1, _ = st.columns(2)
            with col1:
                if fig_pie:
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.info("保有資産がないため、円グラフは表示されません")

        except Exception as e:
            st.error(f"CSVファイルの読み込み中にエラーが発生しました: {e}")

if __name__ == '__main__':
    main()
