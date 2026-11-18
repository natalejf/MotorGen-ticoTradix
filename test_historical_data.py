import json
import lzma
import struct

import pandas as pd
import pytest

from backend import data_manager as dm
from backend.historical_data import HistoricalArchive, decode_dukascopy, resample_closed, atomic_frame, atomic_json
from backend.strategy import Strategy


def sample(start='2016-11-18', periods=48):
    index = pd.date_range(start, periods=periods, freq='h', tz='UTC', name='Date')
    return pd.DataFrame({'Open': 100., 'High': 102., 'Low': 99., 'Close': 101., 'Volume': 3.}, index=index)


def test_binary_quote_order_scale_and_closed_market_filter():
    payload = lzma.compress(b''.join(struct.pack('>5If', *row) for row in [
        (0, 108000, 108100, 107900, 108200, 5.),
        (3600, 108100, 108100, 108100, 108100, 0.)]))
    frame = decode_dukascopy(payload, 2016, 11, 100000)
    assert len(frame) == 1 and frame.iloc[0].Close == 1.081
    assert frame.iloc[0].Low == 1.079 and frame.iloc[0].High == 1.082
    assert str(frame.index[0]) == '2016-11-01 00:00:00+00:00'


def test_invalid_binary_envelope_and_payload_are_rejected():
    bad = lzma.compress(struct.pack('>5If', 0, 100, 101, 110, 105, 1.))
    with pytest.raises(ValueError, match='envelope'):
        decode_dukascopy(bad, 2016, 11, 1)
    with pytest.raises(ValueError):
        decode_dukascopy(lzma.compress(b'bad'), 2016, 11, 1)


def test_resampling_uses_utc_and_excludes_open_bar_without_filling_weekends():
    frame = sample(periods=7)
    end = pd.Timestamp('2016-11-18 07:00', tz='UTC')
    result = resample_closed(frame, '4h', end)
    assert len(result) == 1 and result.iloc[0].Volume == 12.
    assert resample_closed(frame, '1d', end).empty
    separated = pd.concat([sample('2016-11-18', 24), sample('2016-11-21', 24)])
    daily = resample_closed(separated, '1d', pd.Timestamp('2016-11-22', tz='UTC'))
    assert len(daily) == 2


def test_source_paths_are_isolated_and_saved_strategy_keeps_original_source(tmp_path):
    manager = dm.DataManager(str(tmp_path))
    original = sample()
    original.to_parquet(manager.get_file_path('NASDAQ', '1h', 'yahoo'))
    archive = manager.archive
    long_frame = original * 2
    atomic_frame(archive.path('NASDAQ', '1h'), long_frame)
    atomic_json(archive.path('NASDAQ', '1h').parent / 'manifest.json', {
        'status': 'complete', 'point_value': 1., 'missing_months': []})
    assert manager.load_data('NASDAQ', source='yahoo').iloc[0].Open == 100
    active = manager.load_data('NASDAQ')
    assert active.iloc[0].Open == 200 and active.attrs['symbol_metadata']['point_value'] == 1
    assert active.attrs['data_source'] == 'dukascopy'
    strategy = Strategy(data_source='dukascopy')
    assert Strategy.from_dict(strategy.to_dict()).data_source == 'dukascopy'
    assert Strategy.from_dict({'symbol':'NASDAQ'}).data_source == 'yahoo'


def test_replaced_file_invalidates_memory_cache(tmp_path):
    manager = dm.DataManager(str(tmp_path))
    path = manager.get_file_path('EURUSD', '1h', 'yahoo')
    atomic_frame(path, sample())
    assert manager.load_data('EURUSD').iloc[0].Close == 101
    atomic_frame(path, sample() * 2)
    assert manager.load_data('EURUSD').iloc[0].Close == 202


def test_failed_month_is_reported_and_not_activated(tmp_path, monkeypatch):
    archive = HistoricalArchive(tmp_path / 'history')
    def month(symbol, stamp, end):
        if stamp == pd.Timestamp('2020-01-01', tz='UTC'):
            raise OSError('provider unavailable')
        return sample(stamp, 24)
    monkeypatch.setattr(archive, '_month', month)
    result = archive.download(['EURUSD'], end='2026-11-18T12:00:00Z')
    meta = archive.metadata('EURUSD')
    assert result['status'] == 'partial'
    assert meta['missing_months'] == ['2020-01'] and meta['status'] == 'partial'
    assert meta['requested_start'].startswith('2016-11-18')
    manager = dm.DataManager(str(tmp_path))
    assert manager.get_file_path('EURUSD', '1h').endswith('EURUSD_1h.parquet')
    with pytest.raises(ValueError, match='Incomplete'):
        manager.load_data('EURUSD', source='dukascopy')


def test_catalogue_contains_only_requested_ten_assets():
    assert set(dm.SUPPORTED_SYMBOLS) == {'XAUUSD','NASDAQ','BTCUSD','EURUSD','USDCAD','USDJPY','AUDUSD','GBPUSD','US30','SPXUSD'}
    assert 'USDCHF' in dm.ALL_SYMBOLS  # old saved strategies remain readable


def test_missing_explicit_source_never_falls_back_to_yahoo(tmp_path, monkeypatch):
    manager = dm.DataManager(str(tmp_path))
    monkeypatch.setattr(manager, 'download_symbol_history', lambda *a: pytest.fail('silent fallback'))
    with pytest.raises(FileNotFoundError):
        manager.load_data('EURUSD', source='dukascopy')
