"""Fetch public market data and API-Football fixtures; preserve last good sections."""
import copy
import json
import math
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'data.json'


def now():
    return datetime.now(timezone.utc).isoformat()


def get(url, headers=None):
    req = Request(url, headers={'User-Agent': 'CharoosehDashboard/1.0', 'Accept': 'application/json', **(headers or {})})
    with urlopen(req, timeout=35) as response:
        return json.load(response)


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError('Invalid price')
    return number


def gold(symbol):
    raw = get('https://api.gold-api.com/price/' + symbol)
    return {'value': positive(raw['price']), 'source': 'Gold API',
            'sourceUrl': 'https://gold-api.com/', 'sourceTime': raw.get('updatedAt')}


def tether():
    raw = get('https://api.nobitex.ir/market/stats?' + urlencode({'srcCurrency': 'usdt', 'dstCurrency': 'rls'}))
    if raw.get('status') != 'ok':
        raise ValueError('Nobitex response error')
    # RLS is rial, not toman. Only use the explicitly identified USDT/RLS market.
    return {'value': positive(raw['stats']['usdt-rls']['latest']) / 10,
            'source': 'نوبیتکس؛ آخرین معامله', 'sourceUrl': 'https://nobitex.ir/'}


def football():
    key = os.getenv('FOOTBALL_API_KEY', '').strip()
    if not key:
        raise RuntimeError('missing-key')
    today = datetime.now(ZoneInfo('Asia/Tehran')).date()
    rows = []
    for day in (today - timedelta(days=1), today):
        raw = get('https://v3.football.api-sports.io/fixtures?' + urlencode({
            'date': day.isoformat(), 'timezone': 'Asia/Tehran'}), {'x-apisports-key': key})
        if raw.get('errors') or not isinstance(raw.get('response'), list):
            raise ValueError('Football provider rejected request')
        if raw.get('paging', {}).get('total', 1) > 1:
            raise ValueError('Unexpected paginated response')
        for item in raw['response']:
            rows.append({'id': item['fixture']['id'], 'date': item['fixture']['date'],
                         'status': item['fixture']['status']['short'],
                         'league': item['league']['name'], 'country': item['league']['country'],
                         'home': item['teams']['home']['name'], 'away': item['teams']['away']['name'],
                         'homeGoals': item['goals']['home'], 'awayGoals': item['goals']['away']})
    rows.sort(key=lambda x: x['date'])
    return {'matches': rows, 'dates': [(today - timedelta(days=1)).isoformat(), today.isoformat()],
            'source': 'API-Football', 'sourceUrl': 'https://www.api-football.com/'}


def refresh(data, name, fetch, error_text):
    previous = copy.deepcopy(data.get(name, {}))
    try:
        data[name] = {**fetch(), 'fetchedAt': now(), 'error': None}
    except Exception as exc:
        # Do not write API keys, provider response bodies or exception URLs to public data.
        print(f'{name}: update failed ({type(exc).__name__})')
        previous['error'] = error_text
        previous['lastAttempt'] = now()
        data[name] = previous


def main():
    data = json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {}
    data['lastAttempt'] = now()
    refresh(data, 'usdt', tether, 'دریافت نرخ تتر ناموفق بود؛ ممکن است منبع از محل اجرای گیت‌هاب در دسترس نباشد.')
    refresh(data, 'btc', lambda: gold('BTC'), 'دریافت قیمت بیت‌کوین ناموفق بود.')
    refresh(data, 'xau', lambda: gold('XAU'), 'دریافت قیمت اونس ناموفق بود.')
    xau = data.get('xau', {})
    if xau.get('value'):
        data['gold18'] = {**xau, 'value': xau['value'] / 31.1034768 * .75,
                          'source': 'محاسبه از اونس جهانی؛ Gold API'}
    else:
        data['gold18'] = {'error': 'برای محاسبه، قیمت معتبر اونس دریافت نشده است.'}
    message = ('کلید رایگان FOOTBALL_API_KEY هنوز در GitHub Secrets تنظیم نشده است.'
               if not os.getenv('FOOTBALL_API_KEY', '').strip() else
               'دریافت فوتبال ناموفق بود؛ دسترسی فصل جاری در پلن رایگان، سهمیه و اتصال را بررسی کنید.')
    refresh(data, 'football', football, message)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    temp = OUT.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    temp.replace(OUT)


if __name__ == '__main__':
    main()
