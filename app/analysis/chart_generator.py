import os
import uuid
import logging

import matplotlib
matplotlib.use('Agg')  # 无头模式，服务器不需要 GUI
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates

from config import settings
from app.analysis.stock_analyzer import StockAnalyzer

logger = logging.getLogger(__name__)


def generate_chart(symbol: str, period: str = "1y") -> str:
    """
    生成 K 线 + 技术指标图表，保存为图片文件。

    Returns:
        图片文件绝对路径
    """
    analyzer = StockAnalyzer(symbol, period)
    analyzer.fetch_data()
    analyzer.calculate_all_indicators()

    plot_df = analyzer.data.tail(100)
    dates = plot_df.index

    fig = None
    try:
        fig = plt.figure(figsize=(14, 10))
        gs = gridspec.GridSpec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.3)

        # --- 主图: 价格 + 均线 + 布林带 ---
        ax1 = fig.add_subplot(gs[0])
        ax1.set_title(f"{symbol} Technical Analysis", fontsize=14, fontweight='bold')
        ax1.plot(dates, plot_df['Close'], label='Price', color='black', linewidth=1.5)
        ax1.plot(dates, plot_df['SMA_5'], label='SMA5', color='#FF9800', linestyle='--', linewidth=1)
        ax1.plot(dates, plot_df['SMA_20'], label='SMA20', color='#2196F3', linewidth=1.5)
        if 'SMA_60' in plot_df.columns:
            ax1.plot(dates, plot_df['SMA_60'], label='SMA60', color='#4CAF50', linewidth=1.5, alpha=0.7)

        ax1.fill_between(dates, plot_df['BBU_20_2.0_2.0'], plot_df['BBL_20_2.0_2.0'], alpha=0.1, color='gray', label='Bollinger')
        ax1.legend(loc='upper left', fontsize=8)
        ax1.grid(True, alpha=0.3)
        ax1.set_ylabel("Price ($)")

        # --- 副图1: 成交量 ---
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        colors = ['#4CAF50' if c >= o else '#F44336'
                  for c, o in zip(plot_df['Close'], plot_df['Open'])]
        ax2.bar(dates, plot_df['Volume'], color=colors, alpha=0.7, width=0.8)
        ax2.plot(dates, plot_df['Vol_SMA_5'], color='orange', linewidth=1, label='Vol SMA5')
        ax2.set_ylabel("Volume")
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper left', fontsize=7)

        # --- 副图2: RSI ---
        ax3 = fig.add_subplot(gs[2], sharex=ax1)
        ax3.plot(dates, plot_df['RSI_14'], color='purple', linewidth=1, label='RSI(14)')
        ax3.axhline(70, color='red', linestyle='--', alpha=0.5)
        ax3.axhline(30, color='green', linestyle='--', alpha=0.5)
        ax3.fill_between(dates, plot_df['RSI_14'], 70,
                         where=(plot_df['RSI_14'] >= 70), facecolor='red', alpha=0.3)
        ax3.fill_between(dates, plot_df['RSI_14'], 30,
                         where=(plot_df['RSI_14'] <= 30), facecolor='green', alpha=0.3)
        ax3.set_ylabel("RSI")
        ax3.set_ylim(0, 100)
        ax3.grid(True, alpha=0.3)
        ax3.legend(loc='upper left', fontsize=7)

        # --- 副图3: MACD ---
        ax4 = fig.add_subplot(gs[3], sharex=ax1)
        macd_colors = ['#4CAF50' if v >= 0 else '#F44336' for v in plot_df['MACDh_12_26_9']]
        ax4.bar(dates, plot_df['MACDh_12_26_9'], color=macd_colors, alpha=0.7, width=0.8)
        ax4.plot(dates, plot_df['MACD_12_26_9'], color='blue', linewidth=1, label='DIF')
        ax4.plot(dates, plot_df['MACDs_12_26_9'], color='orange', linewidth=1, label='DEA')
        ax4.axhline(0, color='gray', linewidth=0.5)
        ax4.set_ylabel("MACD")
        ax4.grid(True, alpha=0.3)
        ax4.legend(loc='upper left', fontsize=7)

        # 日期格式
        ax4.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax4.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45, fontsize=8)

        # 隐藏上面子图的 x 轴标签
        for ax in [ax1, ax2, ax3]:
            plt.setp(ax.get_xticklabels(), visible=False)

        # 保存图片
        os.makedirs(settings.charts_dir, exist_ok=True)
        filename = f"{symbol}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(settings.charts_dir, filename)
        fig.savefig(filepath, dpi=120, bbox_inches='tight', facecolor='white')
        logger.info(f"Chart saved: {filepath}")
        return os.path.abspath(filepath)

    finally:
        # 显式释放内存
        if fig is not None:
            fig.clf()
        plt.close('all')
