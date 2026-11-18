"""Source-separated, resumable H1 archive. H4/D1 use UTC boundaries.

No ticks, credentials or paid endpoints. A failed month is never silently filled
with another provider. Existing Yahoo files remain available to saved strategies.
"""
import calendar
import concurrent.futures
import datetime as dt
import json
import lzma
import os
from pathlib import Path
import struct
import threading
import time
import uuid
import requests
from contextlib import contextmanager

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent / 'data' / 'history'
COLUMNS = ['Open', 'High', 'Low', 'Close', 'Volume']
_http = threading.local()
_pace_lock = threading.Lock()
_next_request = 0.0
# Hourly binary prices: integer quotes / price scale (not broker pip sizes).
INSTRUMENTS = {
    'XAUUSD': ('XAUUSD', 1000, 'Spot gold / USD'),
    'NASDAQ': ('USATECHIDXUSD', 1000, 'Nasdaq 100 index CFD'),
    'EURUSD': ('EURUSD', 100000, 'EUR / USD'),
    'USDCAD': ('USDCAD', 100000, 'USD / CAD'),
    'USDJPY': ('USDJPY', 1000, 'USD / JPY'),
    'AUDUSD': ('AUDUSD', 100000, 'AUD / USD'),
    'GBPUSD': ('GBPUSD', 100000, 'GBP / USD'),
    'US30': ('USA30IDXUSD', 1000, 'Dow Jones 30 index CFD'),
    'SPXUSD': ('USA500IDXUSD', 1000, 'S&P 500 index CFD'),
    'BTCUSD': ('btcusd', 1, 'Bitcoin / USD spot, Bitstamp'),
}


def source_for(symbol):
    return 'bitstamp' if symbol == 'BTCUSD' else 'dukascopy'


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    replace_file(tmp, path)


def atomic_frame(path, frame):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex[:8] + '.tmp')
    frame.to_parquet(tmp, compression='zstd')
    replace_file(tmp, path)


def replace_file(tmp, path):
    # Windows readers / OneDrive briefly hold destination handles without delete sharing.
    for attempt in range(9):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 8:
                raise
            time.sleep(min(.05 * 2 ** attempt, 1.))


@contextmanager
def download_lock(root):
    """OS lock released on crash; the CLI and web cannot write one archive twice."""
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / '.download.lock').open('a+b')
    handle.seek(0)
    handle.write(b'0')
    handle.flush()
    handle.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        raise RuntimeError('Another historical download is already running')
    try:
        yield
    finally:
        handle.close()


def fetch(url, attempts=4):
    global _next_request
    if not hasattr(_http, 'session'):
        _http.session = requests.Session()
    for attempt in range(attempts):
        try:
            with _pace_lock:
                delay = max(0., _next_request - time.monotonic())
                _next_request = max(_next_request, time.monotonic()) + .5
            if delay:
                time.sleep(delay)
            response = _http.session.get(url, timeout=(8, 20), headers={'User-Agent': 'Stratix-History/1.0'})
            if response.status_code == 429:
                try:
                    pause = max(30 * (attempt + 1), float(response.headers.get('Retry-After', 0)))
                except ValueError:
                    pause = 60.
                if pause > 300:
                    raise RuntimeError('Provider rate limit: wait before resuming the import')
                with _pace_lock:
                    _next_request = max(_next_request, time.monotonic() + pause)
            response.raise_for_status()
            return response.content
        except requests.HTTPError as exc:
            if exc.response.status_code == 404:
                raise
            if attempt == attempts - 1:
                raise
        except requests.RequestException:
            if attempt == attempts - 1:
                raise
        time.sleep(min(2 ** attempt, 8))


def decode_dukascopy(payload, year, month, scale):
    raw = lzma.decompress(payload)
    if not raw or len(raw) % 24:
        raise ValueError('Invalid hourly .bi5 payload')
    rows = list(struct.iter_unpack('>5If', raw))
    frame = pd.DataFrame(rows, columns=['seconds', 'Open', 'Close', 'Low', 'High', 'Volume'])
    max_seconds = calendar.monthrange(year, month)[1] * 86400
    if (frame.seconds % 3600 != 0).any() or (frame.seconds >= max_seconds).any():
        raise ValueError('Hourly timestamps outside month')
    frame.index = pd.DatetimeIndex(pd.Timestamp(year=year, month=month, day=1, tz='UTC')
                                   + pd.to_timedelta(frame.pop('seconds'), unit='s'), name='Date')
    frame[['Open', 'High', 'Low', 'Close']] /= scale
    # Provider pads closed markets with zero-volume flat bars. Do not invent trades.
    frame = frame.loc[~((frame.Volume == 0) & (frame.High == frame.Low)), COLUMNS]
    return validate(frame)


def validate(frame):
    if frame.empty:
        raise ValueError('No active hourly bars')
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError('Unsorted or duplicate timestamps')
    if frame[COLUMNS].isna().any().any() or (frame.Volume < 0).any():
        raise ValueError('Invalid OHLCV values')
    if (frame.Low > frame[['Open', 'Close', 'High']].min(axis=1)).any() or \
       (frame.High < frame[['Open', 'Close', 'Low']].max(axis=1)).any() or (frame.Low <= 0).any():
        raise ValueError('Invalid OHLC envelope')
    return frame


def resample_closed(frame, rule, end):
    result = frame.resample(rule, origin='start_day', label='left', closed='left').agg(
        {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'}).dropna()
    return result.loc[result.index + pd.Timedelta(rule) <= end]


class HistoricalArchive:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.lock = threading.Lock()
        self.state = {'status': 'idle', 'completed': 0, 'total': 0, 'errors': []}
        self.thread = None

    def path(self, symbol, timeframe, source=None):
        source = source or source_for(symbol)
        if source not in ('dukascopy', 'bitstamp') or symbol not in INSTRUMENTS or timeframe not in ('1h', '4h', '1d'):
            raise ValueError('Unsupported historical dataset')
        return self.root / source / symbol / f'{timeframe}.parquet'

    def metadata(self, symbol):
        path = self.path(symbol, '1h').parent / 'manifest.json'
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except FileNotFoundError:
            return None

    def status(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self, symbols=None):
        symbols = list(dict.fromkeys(symbols or INSTRUMENTS))
        if not symbols or any(s not in INSTRUMENTS for s in symbols):
            raise ValueError('Unsupported symbols')
        with self.lock:
            if self.state['status'] == 'running':
                return False
            self.state = {'status': 'running', 'completed': 0, 'total': 0, 'errors': [], 'symbols': symbols}
        self.thread = threading.Thread(target=self._run, args=(symbols,), daemon=True)
        self.thread.start()
        return True

    def _month(self, symbol, stamp, end):
        source = source_for(symbol)
        instrument, scale, _ = INSTRUMENTS[symbol]
        path = self.path(symbol, '1h').parent / 'months' / f'{stamp:%Y-%m}.parquet'
        next_month = stamp + pd.offsets.MonthBegin(1)
        # Refresh current and previous month, allowing provider corrections.
        immutable_before = end.normalize().replace(day=1) - pd.offsets.MonthBegin(1)
        if path.exists() and stamp < immutable_before:
            return pd.read_parquet(path)
        if source == 'dukascopy':
            url = f'http://datafeed.dukascopy.com/datafeed/{instrument}/{stamp.year}/{stamp.month-1:02d}/BID_candles_hour_1.bi5'
            try:
                frame = decode_dukascopy(fetch(url), stamp.year, stamp.month, scale)
            except requests.HTTPError as exc:
                # A few legacy monthly files also return persistent 503. Recover
                # from daily candles, keeping the same provider and quote side.
                if exc.response.status_code not in (404, 503):
                    raise
                if exc.response.status_code == 404 and next_month <= end:
                    raise
                frame = self._current_month(symbol, stamp, min(end, next_month), scale)
        else:
            # A calendar month fits within Bitstamp's 1000-bar endpoint limit.
            upper = min(next_month, end)
            url = (f'https://www.bitstamp.net/api/v2/ohlc/btcusd/?step=3600&limit=1000'
                   f'&start={int(stamp.timestamp())}&end={int(upper.timestamp())-1}&exclude_current_candle=true')
            rows = json.loads(fetch(url))['data']['ohlc']
            frame = pd.DataFrame(rows)
            if frame.empty:
                raise ValueError('Bitstamp returned no bars')
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop('timestamp').astype('int64'), unit='s', utc=True), name='Date')
            frame = frame.rename(columns=str.title)[COLUMNS].astype(float)
            frame = validate(frame.loc[(frame.index >= stamp) & (frame.index < upper)])
        frame = frame.loc[frame.index + pd.Timedelta(hours=1) <= end]
        if next_month <= end:
            atomic_frame(path, frame)
        # Do not cache a partial current month as an immutable month.
        return frame

    def _current_month(self, symbol, stamp, end, scale):
        """The legacy monthly archive is published after month-end.

        For the open month, aggregate daily minute quotes from the SAME provider.
        Only hourly aggregates are persisted, never minute/tick history.
        """
        frames = []
        instrument = INSTRUMENTS[symbol][0]
        for day in pd.date_range(stamp, end.normalize() - pd.Timedelta(days=1), freq='D'):
            path = self.path(symbol, '1h').parent / 'days' / f'{day:%Y-%m-%d}.parquet'
            if path.exists() and day < end.normalize() - pd.Timedelta(days=1):
                frames.append(pd.read_parquet(path))
                continue
            url = f'http://datafeed.dukascopy.com/datafeed/{instrument}/{day.year}/{day.month-1:02d}/{day.day:02d}/BID_candles_min_1.bi5'
            try:
                raw = lzma.decompress(fetch(url))
            except requests.HTTPError as exc:
                # Saturdays have no forex/index quotes. Sundays may have a session.
                if exc.response.status_code == 404 and day.dayofweek == 5:
                    continue
                raise
            if not raw:
                continue
            if len(raw) % 24:
                raise ValueError('Invalid daily minute payload')
            minute = pd.DataFrame(struct.iter_unpack('>5If', raw), columns=['seconds','Open','Close','Low','High','Volume'])
            if (minute.seconds >= 86400).any() or (minute.seconds % 60 != 0).any():
                raise ValueError('Invalid minute timestamps')
            minute.index = pd.DatetimeIndex(day + pd.to_timedelta(minute.pop('seconds'), unit='s'), name='Date')
            minute[['Open','High','Low','Close']] /= scale
            minute = minute.loc[~((minute.Volume == 0) & (minute.High == minute.Low)), COLUMNS]
            if minute.empty:
                continue
            minute = validate(minute)
            hour = resample_closed(minute, '1h', end)
            if day < end.normalize():
                atomic_frame(path, hour)
            frames.append(hour)
        if not frames:
            raise ValueError('No current-month quotes available')
        return validate(pd.concat(frames).sort_index())

    def _run(self, symbols):
        try:
            self.download(symbols)
        except Exception as exc:
            with self.lock:
                self.state['status'] = 'failed'
                self.state['errors'].append(str(exc))
                snapshot = dict(self.state)
            atomic_json(self.root / 'progress.json', snapshot)

    def download(self, symbols, end=None):
        with download_lock(self.root):
            return self._download(symbols, end)

    def _download(self, symbols, end=None):
        # Refresh once per completed UTC day; today's archive is still forming.
        end = pd.Timestamp(end or dt.datetime.now(dt.timezone.utc)).normalize()
        start = end.normalize() - pd.DateOffset(years=10)
        months = pd.date_range(start.replace(day=1), end.normalize().replace(day=1), freq='MS')
        with self.lock:
            self.state.update(status='running', total=len(months)*len(symbols), completed=0, errors=[], start=str(start), end=str(end))
        for symbol in symbols:
            frames, missing = [], []
            with self.lock:
                self.state['current_symbol'] = symbol
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures = {pool.submit(self._month, symbol, month, end): month for month in months}
                for future in concurrent.futures.as_completed(futures):
                    month = futures[future]
                    try:
                        frames.append(future.result())
                    except Exception as exc:
                        missing.append(f'{month:%Y-%m}')
                        with self.lock:
                            self.state['errors'].append({'symbol': symbol, 'month': f'{month:%Y-%m}', 'error': str(exc)})
                    with self.lock:
                        self.state['completed'] += 1
                        snapshot = dict(self.state)
                    atomic_json(self.root / 'progress.json', snapshot)
            if not frames:
                continue
            frame = pd.concat(frames).sort_index()
            frame = validate(frame.loc[(frame.index >= start) & (frame.index + pd.Timedelta(hours=1) <= end)])
            previous = self.metadata(symbol)
            if missing and previous and previous['status'] == 'complete':
                # Preserve last known complete dataset if an incremental update fails.
                previous['last_update_missing_months'] = sorted(missing)
                atomic_json(self.path(symbol, '1h').parent / 'manifest.json', previous)
                continue
            source = source_for(symbol)
            data = {'1h': frame, '4h': resample_closed(frame, '4h', end), '1d': resample_closed(frame, '1d', end)}
            # Keep incomplete imports visible in their source directory but do not activate them.
            meta = {'symbol': symbol, 'source': source, 'instrument': INSTRUMENTS[symbol][0],
                    'description': INSTRUMENTS[symbol][2], 'price_side': 'bid' if source == 'dukascopy' else 'trade',
                    'timezone': 'UTC', 'requested_start': str(start), 'requested_end': str(end),
                    'updated_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                    'status': 'complete' if not missing else 'partial', 'missing_months': sorted(missing),
                    'volume_kind': 'provider_quote_volume' if source == 'dukascopy' else 'BTC_traded',
                    'aggregation': 'UTC, left-closed; market closures not filled; final open bars excluded',
                    'timeframes': {}}
            for tf, df in data.items():
                path = self.path(symbol, tf)
                atomic_frame(path, df)
                # Missing hours include scheduled market closures; not a claim of data loss.
                meta['timeframes'][tf] = {'bars': len(df), 'start': str(df.index[0]), 'end': str(df.index[-1]),
                                           'bytes': path.stat().st_size}
            # Cash index CFDs use one USD/point here; broker execution uses its own contract specs.
            if symbol in ('NASDAQ', 'US30', 'SPXUSD'):
                meta['point_value'] = 1.0
            atomic_json(self.path(symbol, '1h').parent / 'manifest.json', meta)
        with self.lock:
            self.state['status'] = 'completed' if not self.state['errors'] else 'partial'
            snapshot = dict(self.state)
        atomic_json(self.root / 'progress.json', snapshot)
        return snapshot


historical_archive = HistoricalArchive()

if __name__ == '__main__':
    historical_archive._run(list(INSTRUMENTS))
    print(json.dumps(historical_archive.status(), ensure_ascii=False), flush=True)
