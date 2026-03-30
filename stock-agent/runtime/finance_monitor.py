#!/usr/bin/env python3
import json
import os
import socket
import time
import hashlib
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path('/home/kent/.openclaw/workspace/stock-agent')
POSITIONS_JSON = ROOT / 'positions.json'
WATCHLIST_JSON = ROOT / 'watchlist.json'
LEDGER_MD = ROOT / 'review-ledger-live.md'
CACHE_JSON = ROOT / 'runtime' / 'last_snapshot.json'
ALERT_STATE_JSON = ROOT / 'runtime' / 'alert_state.json'
RUNTIME_CONFIG_JSON = ROOT / 'runtime' / 'runtime_config.json'

socket.setdefaulttimeout(15)
AKSHARE_SPOT_CACHE = None
AKSHARE_SPOT_CACHE_TS = None


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def http_get(url, retry=3):
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=20) as response:
                raw = response.read().decode('utf-8')
                return json.loads(raw)
        except Exception as e:
            if i < retry - 1:
                time.sleep(1)
                continue
            return {'error': str(e)}
    return {'error': 'max retry'}


def should_use_llm(mode, alerts, config):
    if not config.get('enableLlmSummary'):
        return False
    llm_modes = config.get('llmEnabledModes', ['盘前', '收盘'])
    if mode in llm_modes:
        return True
    high_risk = any(a.get('level') == '高' for a in alerts)
    return high_risk and config.get('llmOnHighRiskOnly', True)


def call_minimax_summary(prompt, config):
    provider_cfg = load_json(Path('/home/kent/.openclaw/agents/finance/agent/models.json'), {}).get('providers', {}).get('minimax', {})
    api_key = provider_cfg.get('apiKey') or os.environ.get('MINIMAX_API_KEY')
    base_url = provider_cfg.get('baseUrl', 'https://api.minimaxi.com/anthropic')
    model = config.get('preferredSummaryModel', 'minimax/MiniMax-M2.7').split('/')[-1]
    if not api_key:
        return None
    payload = {
        'model': model,
        'max_tokens': 800,
        'messages': [
            {
                'role': 'user',
                'content': prompt
            }
        ]
    }
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{base_url}/v1/messages",
        data=body,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
            'x-api-key': api_key,
            'anthropic-version': '2023-06-01'
        },
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            parts = data.get('content') or []
            text = ''.join([p.get('text', '') for p in parts if isinstance(p, dict)])
            return text.strip() or None
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode('utf-8')
        except Exception:
            detail = str(e)
        return f"[LLM总结失败] {detail[:300]}"
    except Exception as e:
        return f"[LLM总结失败] {str(e)[:300]}"


def secid(code):
    return f"1.{code}" if code.startswith(('5', '6')) else f"0.{code}"


def normalize_eastmoney_price(value):
    if value in (None, '-', ''):
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if abs(v) >= 10000:
        v = v / 1000
    elif abs(v) >= 1000:
        v = v / 100
    return round(v, 3)


def normalize_eastmoney_pct(value):
    if value in (None, '-', ''):
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if abs(v) > 1000:
        v = v / 100
    return round(v, 2)


def normalize_numeric(value, digits=2):
    if value in (None, '-', ''):
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return None


def quote_quality(quote):
    if quote.get('error'):
        return 'bad'
    price = quote.get('price')
    high = quote.get('high')
    low = quote.get('low')
    pct = quote.get('changePct')
    if price is None or price <= 0:
        return 'bad'
    if high is not None and low is not None and high < low:
        return 'bad'
    if high is not None and price > high * 1.12:
        return 'bad'
    if low is not None and price < low * 0.88:
        return 'bad'
    if pct is not None and abs(pct) > 25:
        return 'suspicious'
    return 'good'


def get_quote_eastmoney(code):
    url = f"https://push2.eastmoney.com/api/qt/stock/get?fltt=2&invt=2&fields=f43,f44,f45,f46,f47,f48,f57,f58,f116,f117,f162,f168,f170&secid={secid(code)}"
    data = http_get(url, retry=5)
    if data.get('error') or not data.get('data'):
        return {'error': data.get('error', 'no data'), 'source': 'eastmoney'}
    d = data['data']
    quote = {
        'source': 'eastmoney',
        'price': normalize_eastmoney_price(d.get('f43')),
        'high': normalize_eastmoney_price(d.get('f44')),
        'low': normalize_eastmoney_price(d.get('f45')),
        'open': normalize_eastmoney_price(d.get('f46')),
        'volume': d.get('f47'),
        'amount': d.get('f48'),
        'turnover': normalize_numeric(d.get('f168'), 2),
        'changePct': normalize_eastmoney_pct(d.get('f170')),
    }
    quote['quality'] = quote_quality(quote)
    return quote


def load_akshare_spot_table():
    global AKSHARE_SPOT_CACHE, AKSHARE_SPOT_CACHE_TS
    now = time.time()
    if AKSHARE_SPOT_CACHE is not None and AKSHARE_SPOT_CACHE_TS and now - AKSHARE_SPOT_CACHE_TS < 60:
        return AKSHARE_SPOT_CACHE
    try:
        import akshare as ak  # type: ignore
    except Exception:
        return None
    try:
        df = ak.stock_zh_a_spot_em()
        AKSHARE_SPOT_CACHE = df
        AKSHARE_SPOT_CACHE_TS = now
        return df
    except Exception:
        return None


def get_quote_akshare(code):
    df = load_akshare_spot_table()
    if df is None:
        return {'error': 'akshare unavailable', 'source': 'akshare'}
    try:
        row = df[df['代码'].astype(str) == str(code)]
        if row.empty:
            return {'error': 'symbol not found', 'source': 'akshare'}
        r = row.iloc[0]
        quote = {
            'source': 'akshare',
            'price': normalize_numeric(r.get('最新价'), 3),
            'high': normalize_numeric(r.get('最高'), 3),
            'low': normalize_numeric(r.get('最低'), 3),
            'open': normalize_numeric(r.get('今开'), 3),
            'volume': r.get('成交量'),
            'amount': r.get('成交额'),
            'turnover': normalize_numeric(r.get('换手率'), 2),
            'changePct': normalize_numeric(r.get('涨跌幅'), 2),
        }
        quote['quality'] = quote_quality(quote)
        return quote
    except Exception as e:
        return {'error': str(e), 'source': 'akshare'}


def choose_best_quote(candidates, config):
    priority = config.get('quoteSourcePriority', ['eastmoney', 'akshare'])
    def score(item):
        quality = item.get('quality')
        source = item.get('source')
        try:
            source_bonus = max(0, len(priority) - priority.index(source))
        except Exception:
            source_bonus = 0
        if quality == 'good':
            return 30 + source_bonus
        if quality == 'suspicious':
            return 20 + source_bonus
        if item.get('error'):
            return 0
        return 10 + source_bonus

    ranked = sorted(candidates, key=score, reverse=True)
    best = ranked[0] if ranked else {'error': 'no candidate'}
    if best.get('error'):
        return best
    best['diagnostics'] = [{
        'source': c.get('source'),
        'quality': c.get('quality'),
        'price': c.get('price'),
        'changePct': c.get('changePct'),
        'error': c.get('error')
    } for c in candidates]
    return best


def get_quote(code, config, mode='巡检'):
    candidates = [get_quote_eastmoney(code)]
    akshare_modes = config.get('akshareEnabledModes', ['盘前', '收盘'])
    enable_ak = config.get('enableAkshare') or os.environ.get('FINANCE_ENABLE_AKSHARE', '0') == '1'
    if enable_ak and mode in akshare_modes:
        candidates.append(get_quote_akshare(code))
    return choose_best_quote(candidates, config)


def get_indices():
    url = 'https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&invt=2&fields=f2,f3,f12,f14&secids=1.000001,0.399001,0.399006,1.000688'
    data = http_get(url)
    result = []
    for item in data.get('data', {}).get('diff', []) or []:
        result.append({
            'name': item.get('f14'),
            'price': normalize_eastmoney_price(item.get('f2')),
            'changePct': normalize_eastmoney_pct(item.get('f3')),
        })
    return result


def market_bias(indices):
    vals = [x['changePct'] for x in indices if isinstance(x.get('changePct'), (int, float))]
    if not vals:
        return '未知'
    avg = sum(vals) / len(vals)
    if avg >= 1.2:
        return '偏多'
    if avg >= 0.2:
        return '中性偏多'
    if avg > -0.5:
        return '中性'
    if avg > -1.2:
        return '中性偏空'
    return '偏空'


def alert_key(kind, symbol, action, summary):
    raw = f"{kind}|{symbol}|{action}|{summary}"
    return hashlib.md5(raw.encode('utf-8')).hexdigest()


def should_send_alert(state, key, dedup_minutes):
    now = datetime.now()
    last = state.get('lastSent', {}).get(key)
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(last)
    except Exception:
        return True
    return now - ts >= timedelta(minutes=dedup_minutes)


def mark_sent(state, key):
    state.setdefault('lastSent', {})[key] = datetime.now().isoformat()


def score_watch_item(item, quote):
    score = 0
    reasons = []
    pct = quote.get('changePct')
    stop = item.get('stop')
    price = quote.get('price')
    priority = item.get('priority', 'C')
    style = item.get('style', '')
    quality = quote.get('quality')

    if quality == 'suspicious':
        score -= 2
        reasons.append('数据可疑')
    elif quality == 'bad':
        score -= 4
        reasons.append('数据不可用')

    if priority == 'A':
        score += 2
        reasons.append('A级观察')
    elif priority == 'B':
        score += 1
        reasons.append('B级观察')

    if style == '事件驱动':
        score += 2
        reasons.append('事件驱动')

    if pct is not None and pct >= 5:
        score += 3
        reasons.append('涨幅强')
    elif pct is not None and pct >= 2:
        score += 2
        reasons.append('走势偏强')
    elif pct is not None and pct <= -3:
        score -= 1
        reasons.append('走势偏弱')

    if stop is not None and price is not None and price <= stop:
        score -= 3
        reasons.append('接近止损')

    return max(score, 0), reasons


def build_position_alerts(positions, last_snapshot, config, mode):
    alerts = []
    current_snapshot = {}
    detailed = []
    for p in positions:
        quote = get_quote(p['symbol'], config, mode)
        time.sleep(0.2)
        current_snapshot[p['symbol']] = quote
        detail = {'symbol': p['symbol'], 'name': p['name'], 'quote': quote, 'cost': p.get('cost'), 'hardStop': p.get('hardStop')}
        detailed.append(detail)

        if quote.get('error') or quote.get('quality') == 'bad':
            alerts.append({'kind': 'position', 'symbol': p['symbol'], 'name': p['name'], 'level': '中', 'action': '观察', 'summary': f"{p['name']} 行情质量不足，暂不做强判断。来源：{quote.get('source', 'unknown')}。"})
            continue

        price = quote.get('price')
        pct = quote.get('changePct')
        stop = p.get('hardStop')
        last_price = (last_snapshot.get(p['symbol']) or {}).get('price')

        if quote.get('quality') == 'suspicious':
            alerts.append({'kind': 'position', 'symbol': p['symbol'], 'name': p['name'], 'level': '中', 'action': '人工复核', 'summary': f"{p['name']} 行情存在异常值风险，现价 {price}，涨跌 {pct}% ，建议人工复核后再决策。"})
            continue

        if price is not None and stop is not None and price <= stop:
            alerts.append({'kind': 'position', 'symbol': p['symbol'], 'name': p['name'], 'level': '高', 'action': '减仓/止损', 'summary': f"{p['name']} 现价 {price} 已接近或跌破硬止损 {stop}，优先防守。"})
        elif pct is not None and pct <= config.get('dropAlertPct', -5):
            alerts.append({'kind': 'position', 'symbol': p['symbol'], 'name': p['name'], 'level': '中', 'action': '重点观察', 'summary': f"{p['name']} 当日跌幅 {pct}% ，需警惕弱势延续。"})
        elif pct is not None and pct >= config.get('surgeAlertPct', 5):
            alerts.append({'kind': 'position', 'symbol': p['symbol'], 'name': p['name'], 'level': '中', 'action': '观察/分批止盈', 'summary': f"{p['name']} 当日涨幅 {pct}% ，若冲高回落需防兑现。"})
        elif last_price and price and abs(price - last_price) / last_price * 100 >= config.get('priceMoveThresholdPct', 3):
            direction = '上行' if price > last_price else '下行'
            alerts.append({'kind': 'position', 'symbol': p['symbol'], 'name': p['name'], 'level': '低', 'action': '观察', 'summary': f"{p['name']} 较上次快照明显{direction}，现价 {price}。"})
    return alerts[:config.get('positionMaxAlerts', 6)], current_snapshot, detailed


def build_watchlist_alerts(items, config, mode):
    alerts = []
    detailed = []
    for item in items:
        quote = get_quote(item['symbol'], config, mode)
        time.sleep(0.2)
        if quote.get('error'):
            continue
        score, reasons = score_watch_item(item, quote)
        detailed.append({'item': item, 'quote': quote, 'score': score, 'reasons': reasons})
        price = quote.get('price')
        pct = quote.get('changePct')
        stop = item.get('stop')
        if quote.get('quality') == 'suspicious':
            alerts.append({'kind': 'watchlist', 'symbol': item['symbol'], 'name': item['name'], 'level': '中', 'action': '人工复核', 'summary': f"观察池 {item['name']} 数据存在异常值风险，先复核再决定是否提升优先级。"})
        elif score >= 7:
            alerts.append({'kind': 'watchlist', 'symbol': item['symbol'], 'name': item['name'], 'level': '中', 'action': '重点观察', 'summary': f"观察池 {item['name']} 评分 {score}/10，{','.join(reasons)}，留意触发条件是否成立。"})
        elif stop is not None and price is not None and price <= stop:
            alerts.append({'kind': 'watchlist', 'symbol': item['symbol'], 'name': item['name'], 'level': '中', 'action': '移出观察/谨慎', 'summary': f"观察池 {item['name']} 现价 {price} 接近/跌破观察止损 {stop}，逻辑需重审。"})
        elif pct is not None and pct >= 5:
            alerts.append({'kind': 'watchlist', 'symbol': item['symbol'], 'name': item['name'], 'level': '低', 'action': '继续观察', 'summary': f"观察池 {item['name']} 涨幅 {pct}% ，强度提升，但尚未达到重点推荐阈值。"})
    return alerts[:config.get('watchlistMaxAlerts', 3)], detailed


def dedup_alerts(alerts, state, config, mode):
    if mode == '收盘':
        return alerts
    kept = []
    dedup_minutes = config.get('dedupMinutes', state.get('dedupMinutes', 120))
    for a in alerts:
        key = alert_key(a['kind'], a['symbol'], a['action'], a['summary'])
        if should_send_alert(state, key, dedup_minutes):
            kept.append(a)
            mark_sent(state, key)
    return kept


def format_position_review(details):
    lines = []
    for d in details:
        quote = d['quote']
        if quote.get('error') or quote.get('quality') == 'bad':
            lines.append(f"- {d['name']}({d['symbol']})：行情失败或质量不足，待复核")
            continue
        price = quote.get('price')
        pct = quote.get('changePct')
        stop = d.get('hardStop')
        cost = d.get('cost')
        if quote.get('quality') == 'suspicious':
            action = '数据复核优先'
        elif price is not None and stop is not None and price <= stop:
            action = '防守/减仓'
        elif pct is not None and pct >= 5:
            action = '强势观察，防冲高回落'
        elif pct is not None and pct <= -5:
            action = '弱势防守'
        else:
            action = '继续跟踪'
        pnl = None
        if price is not None and cost:
            pnl = round((price - cost) / cost * 100, 2)
        pnl_text = f"，相对成本 {pnl}%" if pnl is not None else ''
        quality_text = '' if quote.get('quality') == 'good' else f"，数据质量 {quote.get('quality')}"
        lines.append(f"- {d['name']}({d['symbol']})：现价 {price}，当日 {pct}%{pnl_text}{quality_text}，建议：{action}")
    return lines


def format_watchlist_review(details):
    if not details:
        return ['- 暂无观察池数据']
    details = sorted(details, key=lambda x: x['score'], reverse=True)
    lines = []
    for d in details[:5]:
        item = d['item']
        quote = d['quote']
        quality = quote.get('quality')
        qtxt = '' if quality == 'good' else f'，数据质量 {quality}'
        lines.append(f"- {item['name']}({item['symbol']})：评分 {d['score']}/10，涨跌 {quote.get('changePct')}%{qtxt}，理由：{','.join(d['reasons']) or '暂无'}")
    return lines


def build_data_quality_summary(position_details, watchlist_details):
    qualities = []
    for d in position_details:
        qualities.append(d['quote'].get('quality', 'bad'))
    for d in watchlist_details:
        qualities.append(d['quote'].get('quality', 'bad'))
    good = sum(1 for q in qualities if q == 'good')
    suspicious = sum(1 for q in qualities if q == 'suspicious')
    bad = sum(1 for q in qualities if q == 'bad')
    return f"数据质量：良好 {good}，可疑 {suspicious}，不可用 {bad}"


def build_llm_prompt(mode, indices, bias, alerts, positions, position_details, watchlist_details, structured_message):
    facts = {
        'mode': mode,
        'bias': bias,
        'indices': indices,
        'alerts': alerts,
        'positions': positions,
        'position_details': position_details,
        'watchlist_details': watchlist_details,
        'structured_message': structured_message,
    }
    return (
        '你是A股交易情报官。请基于给定结构化事实，输出一版更准确、更简洁、交易含义更强的中文总结。\n'
        '要求：\n'
        '1. 必须先给结论\n'
        '2. 只基于给定事实，不得编造公告/新闻\n'
        '3. 按“结论-原因-关键位-动作”表达\n'
        '4. 若数据质量可疑，明确提示人工复核\n'
        '5. 控制在 350 字内\n\n'
        f'结构化事实：\n{json.dumps(facts, ensure_ascii=False)}'
    )


def format_message(mode, indices, bias, alerts, positions, position_details, watchlist_details, config):
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    lines = [f"【Finance {mode}】{now}", f"市场环境：{bias}"]
    if indices:
        idx_line = '；'.join([f"{x['name']} {x['changePct']}%" for x in indices if x.get('changePct') is not None])
        lines.append(f"指数：{idx_line}")
    lines.append(build_data_quality_summary(position_details, watchlist_details))

    if mode == '盘前':
        lines.append('持仓计划：')
        for p in positions:
            lines.append(f"- {p['name']}({p['symbol']})：硬止损 {p.get('hardStop')}，优先按纪律处理")
    elif mode == '午间':
        lines.append('午间判断：看上午强弱是否延续，优先修正风险判断。')
    elif mode == '收盘':
        lines.append('持仓复盘：')
        lines.extend(format_position_review(position_details))
        lines.append('观察池复盘：')
        lines.extend(format_watchlist_review(watchlist_details))
        lines.append('明日原则：先看风险，再决定是否进攻。')
        structured = '\n'.join(lines)
        llm = call_minimax_summary(build_llm_prompt(mode, indices, bias, alerts, positions, position_details, watchlist_details, structured), config) if should_use_llm(mode, alerts, config) else None
        return f"{structured}\n\nLLM总结：\n{llm}" if llm else structured

    if alerts:
        lines.append('重点变化：')
        for a in alerts:
            prefix = '持仓' if a['kind'] == 'position' else '观察池'
            lines.append(f"- [{prefix}] {a['name']}：{a['summary']} | 建议：{a['action']} | 风险：{a['level']}")
    else:
        lines.append('重点变化：暂无显著增量信号，维持原计划。')

    lines.append('原则：先风险，后机会；持仓优先。')
    structured = '\n'.join(lines)
    llm = call_minimax_summary(build_llm_prompt(mode, indices, bias, alerts, positions, position_details, watchlist_details, structured), config) if should_use_llm(mode, alerts, config) else None
    return f"{structured}\n\nLLM总结：\n{llm}" if llm else structured


def append_ledger(mode, alerts, bias, position_details, watchlist_details):
    LEDGER_MD.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_MD.exists():
        LEDGER_MD.write_text('# 实时复盘台账\n\n', encoding='utf-8')
    with LEDGER_MD.open('a', encoding='utf-8') as f:
        f.write(f"\n## {datetime.now().strftime('%Y-%m-%d %H:%M')} {mode} | 市场环境：{bias}\n")
        f.write(f"- {build_data_quality_summary(position_details, watchlist_details)}\n")
        if mode == '收盘':
            f.write('### 持仓复盘\n')
            for line in format_position_review(position_details):
                f.write(f"{line}\n")
            f.write('### 观察池复盘\n')
            for line in format_watchlist_review(watchlist_details):
                f.write(f"{line}\n")
            return
        if not alerts:
            f.write('- 无显著增量信号，维持原计划。\n')
            return
        for a in alerts:
            f.write(f"- [{a['kind']}] {a['symbol']} {a['name']} | 建议：{a['action']} | 风险：{a['level']} | {a['summary']}\n")


def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else '巡检'
    config = load_json(RUNTIME_CONFIG_JSON, {})
    state = load_json(ALERT_STATE_JSON, {'lastSent': {}, 'dedupMinutes': 120, 'version': 1})
    positions_data = load_json(POSITIONS_JSON, {'positions': []})
    watchlist_data = load_json(WATCHLIST_JSON, {'items': []})
    positions = positions_data.get('positions', [])
    watch_items = watchlist_data.get('items', [])
    last_snapshot = load_json(CACHE_JSON, {})
    indices = get_indices()
    bias = market_bias(indices)
    position_alerts, current_snapshot, position_details = build_position_alerts(positions, last_snapshot, config, mode)
    watchlist_alerts, watchlist_details = build_watchlist_alerts(watch_items, config, mode)
    alerts = dedup_alerts(position_alerts + watchlist_alerts, state, config, mode)
    msg = format_message(mode, indices, bias, alerts, positions, position_details, watchlist_details, config)
    append_ledger(mode, alerts, bias, position_details, watchlist_details)
    save_json(CACHE_JSON, current_snapshot)
    save_json(ALERT_STATE_JSON, state)
    print(msg)


if __name__ == '__main__':
    main()
