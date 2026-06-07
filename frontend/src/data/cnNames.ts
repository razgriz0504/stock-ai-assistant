/**
 * 美股中文名称映射（标普500 + 纳斯达克100 常见股票）
 */
export const CN_NAMES: Record<string, string> = {
  "AAPL":"苹果","ABBV":"艾伯维","ABT":"雅培","ACN":"埃森哲","ADBE":"Adobe","ADI":"亚德诺",
  "ADP":"自动数据处理","ADSK":"欧特克","AEP":"美国电力","AFL":"美国家庭人寿","AIG":"美国国际集团",
  "AMAT":"应用材料","AMD":"超微半导体","AMGN":"安进","AMP":"美国金融集团","AMT":"美国电塔",
  "AMZN":"亚马逊","ANET":"Arista网络","ANSS":"Ansys","AON":"怡安","APD":"空气化工",
  "APH":"安费诺","AVGO":"博通","AXP":"美国运通","AZO":"汽车地带","BA":"波音",
  "BAC":"美国银行","BDX":"碧迪医疗","BK":"纽约梅隆","BKNG":"Booking","BLK":"贝莱德",
  "BMY":"百时美施贵宝","BRK-B":"伯克希尔B","BSX":"波士顿科学","C":"花旗集团",
  "CAT":"卡特彼勒","CB":"丘博保险","CDNS":"铿腾电子","CL":"高露洁","CMCSA":"康卡斯特",
  "CME":"芝商所","COP":"康菲石油","COST":"好市多","CPB":"金宝汤","CRM":"赛富时","CSCO":"思科",
  "CVS":"CVS健康","CVX":"雪佛龙","D":"道明尼能源","DE":"迪尔","DHR":"丹纳赫",
  "DIS":"迪士尼","DOW":"陶氏","DTE":"DTE能源","DUK":"杜克能源","ECL":"艺康","EL":"雅诗兰黛",
  "EMR":"艾默生","ENPH":"昂菲能源","EOG":"EOG资源","EQIX":"Equinix","ETN":"伊顿",
  "EW":"爱德华兹生命科学","EXC":"爱克斯龙","F":"福特","FDX":"联邦快递",
  "FIS":"富达信息","FISV":"Fiserv","FTV":"福迪威","GD":"通用动力","GE":"通用电气",
  "GEHC":"GE医疗","GILD":"吉利德","GIS":"通用磨坊","GM":"通用汽车",
  "GOOG":"谷歌C","GOOGL":"谷歌A","GPN":"环球支付","GS":"高盛","GWW":"固安捷",
  "HD":"家得宝","HON":"霍尼韦尔","HPQ":"惠普","HUM":"哈门那",
  "IBM":"IBM","ICE":"洲际交易所","IDXX":"爱德士","INCY":"因赛特","INTC":"英特尔","INTU":"财捷",
  "ISRG":"直觉外科","ITW":"伊利诺伊工具","JNJ":"强生","JPM":"摩根大通",
  "KDP":"Keurig Dr Pepper","KHC":"卡夫亨氏","KMB":"金佰利","KO":"可口可乐",
  "LIN":"林德","LLY":"礼来","LMT":"洛克希德马丁","LOW":"劳氏","LRCX":"泛林集团",
  "MA":"万事达","MCD":"麦当劳","MCHP":"微芯科技","MCK":"麦克森","MCO":"穆迪",
  "MDLZ":"亿滋国际","MDT":"美敦力","MET":"大都会人寿","META":"Meta",
  "MMM":"3M","MO":"奥驰亚","MRK":"默沙东","MS":"摩根士丹利","MSCI":"明晟",
  "MSFT":"微软","MSI":"摩托罗拉","MU":"美光科技","NEE":"NextEra能源",
  "NFLX":"奈飞","NKE":"耐克","NOC":"诺斯罗普格鲁曼","NOW":"ServiceNow",
  "NSC":"诺福克南方","NVDA":"英伟达","NVR":"NVR地产","ORCL":"甲骨文",
  "ORLY":"奥莱利汽车","OXY":"西方石油","PANW":"帕洛阿尔托网络","PAYC":"Paycom",
  "PCAR":"帕卡","PCG":"太平洋煤电","PEP":"百事","PFE":"辉瑞","PG":"宝洁","PGR":"前进保险","PH":"帕克汉尼汾",
  "PLD":"安博","PM":"菲利普莫里斯","PNC":"PNC金融","PNW":"品尼高西部","PSA":"公共存储",
  "PYPL":"PayPal","QCOM":"高通","REGN":"再生元","ROP":"罗珀科技",
  "ROST":"罗斯百货","RTX":"雷神","SBUX":"星巴克","SCHW":"嘉信理财",
  "SHW":"宣伟","SLB":"斯伦贝谢","SNPS":"新思科技","SO":"南方电力",
  "SPG":"西蒙地产","SPGI":"标普全球","SRE":"桑普拉能源","SYK":"史赛克",
  "T":"AT&T","TFC":"Truist金融","TGT":"塔吉特","TMO":"赛默飞","TMUS":"T-Mobile",
  "TRV":"旅行者集团","TSLA":"特斯拉","TSN":"泰森食品","TXN":"德州仪器",
  "UNH":"联合健康","UNP":"联合太平洋","UPS":"联合包裹","URI":"联合租赁",
  "USB":"美国合众银行","V":"Visa","VFC":"威富集团","VRTX":"福泰制药",
  "VZ":"威瑞森","WBA":"沃尔格林","WFC":"富国银行","WM":"废物管理",
  "WMB":"威廉姆斯","WMT":"沃尔玛","XOM":"埃克森美孚","ZTS":"硕腾",
  "ABNB":"爱彼迎","ARM":"ARM","ASML":"阿斯麦","CCEP":"可口可乐欧洲","COO":"库珀医疗",
  "CRWD":"CrowdStrike","DASH":"DoorDash","DDOG":"Datadog","FTNT":"飞塔网络","KLAC":"科磊",
  "LULU":"露露柠檬","MAR":"万豪","MELI":"MercadoLibre","MNST":"怪兽饮料",
  "MRNA":"Moderna","MRVL":"Marvell","NXPI":"恩智浦","ODFL":"Old Dominion",
  "ON":"安森美","PDD":"拼多多","SMCI":"超微电脑","TEAM":"Atlassian",
  "TTD":"Trade Desk","TTWO":"Take-Two","WDAY":"Workday",
  "CEG":"星座能源","LHX":"L3哈里斯","CPRT":"Copart",
}

/**
 * 板块英文→中文映射
 */
export const SECTOR_CN: Record<string, string> = {
  "Technology": "科技",
  "Healthcare": "医疗健康",
  "Financial Services": "金融",
  "Consumer Cyclical": "可选消费",
  "Communication Services": "通信服务",
  "Industrials": "工业",
  "Consumer Defensive": "必需消费",
  "Energy": "能源",
  "Utilities": "公用事业",
  "Real Estate": "房地产",
  "Basic Materials": "基础材料",
}

/** 获取股票中文名，无则返回英文名 */
export function getCnName(symbol: string, fallback?: string): string {
  return CN_NAMES[symbol] || fallback || symbol
}

/** 获取板块中文名，无则返回英文名 */
export function getCnSector(sector: string): string {
  return SECTOR_CN[sector] || sector
}
