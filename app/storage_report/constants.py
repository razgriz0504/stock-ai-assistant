"""存储行业研究报告 - 常量与机构化指标口径字典（DRAM/NAND/HBM/SSD/HDD）"""

# ── 品类（含中文名） ──
CATEGORIES: dict[str, str] = {
    "DRAM": "DRAM 动态随机存储器",
    "NAND": "NAND Flash 闪存",
    "HBM": "HBM 高带宽存储器",
    "SSD": "SSD 固态硬盘",
    "HDD": "HDD 机械硬盘",
}

# ── 景气度八大主题 ──
THEMES: dict[str, str] = {
    "price": "价格",
    "demand": "需求",
    "supply": "供给",
    "inventory": "库存",
    "profit": "盈利",
    "investment": "投资",
    "dynamics": "动态",
    "technology": "技术",
}

# ── 厂商追踪主体 ──
VENDORS: dict[str, str] = {
    "Samsung": "三星电子",
    "SK Hynix": "SK 海力士",
    "Micron": "美光科技",
    "Kioxia": "铠侠",
    "Western Digital": "西部数据",
    "Nanya": "南亚科技",
    "CXMT": "长鑫存储",
    "YMTC": "长江存储",
    "Seagate": "希捷",
}

# ── 机构化指标口径库 ──
# 每项：key / name / unit / definition（口径解释）/ source_hint（常见发布机构）
METRIC_DICT: list[dict] = [
    {
        "key": "contract_price",
        "name": "合约价 (Contract Price)",
        "unit": "USD",
        "definition": "存储原厂与大客户按月/季签订的长约成交价，反映主流出货价格，波动相对平滑，是景气度的核心风向标。",
        "source_hint": "TrendForce/集邦咨询、DRAMeXchange",
    },
    {
        "key": "spot_price",
        "name": "现货价 (Spot Price)",
        "unit": "USD",
        "definition": "现货市场即时成交价格，反应最灵敏，通常领先合约价，用于观察短期供需拐点。",
        "source_hint": "DRAMeXchange、CFM 闪存市场",
    },
    {
        "key": "dxi",
        "name": "DXI 指数 (DRAM Exchange Index)",
        "unit": "指数",
        "definition": "DRAMeXchange 编制的 DRAM 现货综合价格指数，衡量整体 DRAM 现货市场景气强弱。",
        "source_hint": "DRAMeXchange",
    },
    {
        "key": "bit_shipment",
        "name": "Bit 出货量 (Bit Shipment)",
        "unit": "% QoQ/YoY",
        "definition": "以位元（bit）为单位统计的出货量环比/同比增速，剔除单价影响衡量真实需求放量。",
        "source_hint": "各厂财报、TrendForce",
    },
    {
        "key": "bit_demand_growth",
        "name": "Bit 需求增速 (Bit Demand Growth)",
        "unit": "% YoY",
        "definition": "终端对存储容量的位元需求年增速，衡量结构性需求（AI/服务器/手机）强度。",
        "source_hint": "TrendForce、各厂业绩说明会",
    },
    {
        "key": "utilization",
        "name": "稼动率 (Utilization Rate)",
        "unit": "%",
        "definition": "晶圆厂实际产出与满产产能之比，反映原厂供给策略（减产/满产），是价格拐点先行信号。",
        "source_hint": "各厂财报、TrendForce",
    },
    {
        "key": "inventory_weeks",
        "name": "库存周数 (Weeks of Inventory)",
        "unit": "周",
        "definition": "厂商及渠道库存可供销售的周数，高库存压制价格、低库存支撑涨价。",
        "source_hint": "各厂财报、渠道调研",
    },
    {
        "key": "cost_per_bit",
        "name": "位元成本 (Cost per Bit)",
        "unit": "USD/Gb",
        "definition": "单位位元的制造成本，随制程微缩/层数堆叠逐年下降，决定原厂盈利拐点。",
        "source_hint": "各厂财报、TechInsights",
    },
    {
        "key": "capex",
        "name": "资本开支 (Capex)",
        "unit": "USD",
        "definition": "存储原厂用于扩产/技术升级的资本支出，领先供给约 1-2 年，是中期供需的关键变量。",
        "source_hint": "各厂财报、投资者说明会",
    },
    {
        "key": "gross_margin",
        "name": "毛利率 (Gross Margin)",
        "unit": "%",
        "definition": "存储业务毛利占营收比例，随价格周期大幅波动，衡量盈利景气位置。",
        "source_hint": "各厂财报",
    },
    {
        "key": "hbm_bit_share",
        "name": "HBM 位元占比 (HBM Bit Share)",
        "unit": "%",
        "definition": "HBM 在 DRAM 总位元产出中的占比，衡量 AI 需求对产能的挤占程度。",
        "source_hint": "TrendForce、各厂财报",
    },
]

METRIC_KEYS = {m["key"] for m in METRIC_DICT}


def get_metric(key: str) -> dict | None:
    """按 key 查询指标口径定义"""
    for m in METRIC_DICT:
        if m["key"] == key:
            return m
    return None
