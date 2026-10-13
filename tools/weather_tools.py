"""天气查询工具：体现智能体「调用外部 API」的能力。

使用 wttr.in 的公开 JSON 接口，无需申请 Key（作业演示友好）。
网络不可用时自动降级为本地样例数据，并在返回值中明确标注 source，
保证演示不会中断、也不会伪造"真实数据"。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List

import config
from .registry import tool

# 常见城市中文名 -> wttr.in 可识别的查询串
CITY_MAP: Dict[str, str] = {
    "北京": "Beijing", "上海": "Shanghai", "广州": "Guangzhou", "深圳": "Shenzhen",
    "杭州": "Hangzhou", "南京": "Nanjing", "苏州": "Suzhou", "成都": "Chengdu",
    "重庆": "Chongqing", "武汉": "Wuhan", "西安": "Xian", "天津": "Tianjin",
    "长沙": "Changsha", "郑州": "Zhengzhou", "青岛": "Qingdao", "厦门": "Xiamen",
    "大连": "Dalian", "宁波": "Ningbo", "无锡": "Wuxi", "合肥": "Hefei",
    "福州": "Fuzhou", "济南": "Jinan", "昆明": "Kunming", "哈尔滨": "Harbin",
    "沈阳": "Shenyang", "南昌": "Nanchang", "贵阳": "Guiyang", "南宁": "Nanning",
    "石家庄": "Shijiazhuang", "太原": "Taiyuan", "兰州": "Lanzhou", "乌鲁木齐": "Urumqi",
}

DESC_ZH = {
    "Sunny": "晴", "Clear": "晴", "Partly cloudy": "局部多云", "Cloudy": "多云",
    "Overcast": "阴", "Mist": "薄雾", "Fog": "雾", "Light rain": "小雨",
    "Moderate rain": "中雨", "Heavy rain": "大雨", "Light drizzle": "毛毛雨",
    "Patchy rain possible": "可能有雨", "Patchy rain nearby": "周边有雨",
    "Light rain shower": "阵雨", "Moderate or heavy rain shower": "强阵雨",
    "Thundery outbreaks possible": "可能有雷阵雨", "Snow": "雪", "Light snow": "小雪",
    "Sleet": "雨夹雪", "Blowing snow": "吹雪", "Freezing drizzle": "冻雨",
    "Light freezing rain": "小冻雨", "Smoky haze": "烟霾", "Haze": "霾",
}

# 接口的 lang_zh 字段对部分天气词条没有中文译文，直接按 WW 天气码映射最可靠
WWCODE_ZH = {
    "113": "晴", "116": "多云", "119": "阴", "122": "阴天",
    "143": "薄雾", "145": "雾", "248": "雾", "260": "冻雾",
    "176": "局部有雨", "179": "局部有雪", "182": "局部雨夹雪", "185": "局部冻雨",
    "200": "可能有雷阵雨", "227": "吹雪", "230": "暴风雪",
    "263": "零星毛毛雨", "266": "毛毛雨", "281": "冻毛毛雨", "284": "强冻毛毛雨",
    "293": "局部小雨", "296": "小雨", "299": "间歇中雨", "302": "中雨",
    "305": "间歇大雨", "308": "大雨", "311": "小冻雨", "314": "中到大冻雨",
    "317": "小雨夹雪", "320": "中到大雨夹雪",
    "323": "局部小雪", "326": "小雪", "329": "局部中雪", "332": "中雪",
    "335": "局部大雪", "338": "大雪", "350": "冰粒",
    "353": "小阵雨", "356": "中到大阵雨", "359": "暴雨",
    "362": "小冰雨", "365": "中到大冰雨",
    "368": "小阵雪", "371": "中到大阵雪",
    "374": "小冰粒", "377": "中到大冰粒",
    "386": "局部雷阵雨", "389": "中到大雷阵雨",
    "392": "局部雷阵雪", "395": "中到大雷阵雪",
}

# 离线演示数据（仅在网络不可用时使用）
OFFLINE_SAMPLE: Dict[str, Any] = {
    "current": {"temp": "21", "feels_like": "20", "desc": "多云", "humidity": "48",
                "wind": "12", "wind_dir": "NE", "visibility": "10"},
    "forecast": [
        {"date": "今天", "min": "14", "max": "23", "rain_chance": "20", "desc": "多云"},
        {"date": "明天", "min": "15", "max": "25", "rain_chance": "10", "desc": "晴"},
        {"date": "后天", "min": "16", "max": "24", "rain_chance": "40", "desc": "局部有雨"},
    ],
}


def _pick_desc(node: Dict[str, Any]) -> str:
    """优先用 WW 天气码查中文表；退而取接口的中文字段；最后查英文词典。"""
    code = str(node.get("weatherCode") or "").strip()
    if code in WWCODE_ZH:
        return WWCODE_ZH[code]
    for key in ("lang_zh", "weatherDesc"):
        values = node.get(key)
        if isinstance(values, list) and values:
            text = str(values[0].get("value") or "").strip()
            if not text:
                continue
            if re.search(r"[\u4e00-\u9fff]", text):
                return text
            return DESC_ZH.get(text, text)
    return "未知"


def _fetch(query: str) -> Dict[str, Any]:
    url = f"https://wttr.in/{urllib.parse.quote(query)}?format=j1&lang=zh"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "curl/8.4.0", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=config.WEATHER_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", "ignore"))


def _parse(city_label: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    current_node = (raw.get("current_condition") or [{}])[0]

    # 接口回传的是英文地名，对外统一展示用户输入的城市中文名
    resolved = ""
    areas = raw.get("nearest_area") or []
    if areas:
        names = areas[0].get("areaName") or []
        if names:
            resolved = str(names[0].get("value") or "")

    current = {
        "temp": current_node.get("temp_C", "?"),
        "feels_like": current_node.get("FeelsLikeC", "?"),
        "desc": _pick_desc(current_node),
        "humidity": current_node.get("humidity", "?"),
        "wind": current_node.get("windspeedKmph", "?"),
        "wind_dir": current_node.get("winddir16Point", ""),
        "visibility": current_node.get("visibility", "?"),
    }

    forecast: List[Dict[str, Any]] = []
    for day in (raw.get("weather") or [])[:3]:
        hourly = day.get("hourly") or []
        noon = hourly[4] if len(hourly) > 4 else (hourly[0] if hourly else {})
        forecast.append(
            {
                "date": day.get("date", ""),
                "min": day.get("mintempC", "?"),
                "max": day.get("maxtempC", "?"),
                "rain_chance": noon.get("chanceofrain", "?"),
                "desc": _pick_desc(noon) if noon else "未知",
            }
        )
    return {"city": city_label, "resolved_area": resolved, "current": current, "forecast": forecast}


def _advice(city: str, data: Dict[str, Any]) -> str:
    cur = data["current"]
    temps = [int(f["max"]) for f in data["forecast"] if str(f.get("max", "")).isdigit()]
    rains = [int(f["rain_chance"]) for f in data["forecast"] if str(f.get("rain_chance", "")).isdigit()]
    tips: List[str] = []
    if rains and max(rains) >= 50:
        tips.append("未来几天有较高降雨概率，**记得带伞**。")
    if temps and max(temps) >= 30:
        tips.append("气温偏高，注意防晒补水。")
    if temps and min(temps) <= 8:
        tips.append("气温较低，建议加一件外套。")
    if not tips:
        tips.append("天气整体平稳，适合正常出行。")
    return f"{city}当前 {cur['desc']}，{cur['temp']}℃（体感 {cur['feels_like']}℃）。" + "".join(tips)


@tool(
    name="weather_query",
    description="查询指定城市的实时天气与未来三天预报。当用户询问天气、气温、是否下雨、出行穿搭建议时调用。",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "城市中文名，例如“北京”“杭州”。用户没说城市时可默认北京。",
            }
        },
        "required": ["city"],
    },
)
def weather_query(city: str) -> Dict[str, Any]:
    city = (city or "").strip() or "北京"
    query = CITY_MAP.get(city, city)
    try:
        raw = _fetch(query)
        data = _parse(city, raw)
        data["source"] = "wttr.in 实时接口"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        data = {
            "city": city,
            "current": OFFLINE_SAMPLE["current"],
            "forecast": OFFLINE_SAMPLE["forecast"],
            "source": "offline-sample（网络不可用，以下为内置示例数据，非实时）",
            "network_error": f"{type(exc).__name__}: {exc}",
        }
    data["advice"] = _advice(city, data)
    return data


def resolve_city(text: str) -> str:
    """规则模式下从自然语言里抽取城市名。"""
    for name in CITY_MAP:
        if name in (text or ""):
            return name
    return ""
