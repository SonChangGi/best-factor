import copy
import datetime as dt
import unittest
from unittest import mock
from best_factor.data import _completed_session_rows, fetch_resilient_prices
from best_factor.cli import build_parser, run
from pathlib import Path
import tempfile

class LiveFreshnessTests(unittest.TestCase):
    def test_stale_available_ticker_is_recovered_and_history_is_consistent(self):
        old = {'ticker': 'AAA', 'date': dt.date(2026, 9, 18), 'adj_close': 5.0}
        fresh = {'ticker': 'AAA', 'date': dt.date(2026, 9, 21), 'adj_close': 10.0}
        with mock.patch('best_factor.data.fetch_yfinance_prices', return_value=([old], {})), mock.patch(
            'best_factor.data.fetch_yahoo_chart_prices', return_value=([old, fresh], {})) as recovery:
            rows, meta = fetch_resilient_prices(['AAA'], '5y', expected_end_date=fresh['date'])
        self.assertEqual(recovery.call_args.args[0], ['AAA'])
        self.assertEqual(meta['stale_recovered_tickers'], ['AAA'])
        self.assertEqual(rows, [old, fresh])

    def test_one_day_recovery_rejects_intraday_wrong_session_missing_adjustment_and_invalid_ohlc(self):
        end = int(dt.datetime(2026, 9, 21, 20, tzinfo=dt.UTC).timestamp())
        result = {'meta': {'currentTradingPeriod': {'regular': {'end': end}}},
            'timestamp': [end + 1], 'indicators': {'quote': [{'open':[10], 'high':[12], 'low':[9], 'close':[11], 'volume':[100]}], 'adjclose':[{'adjclose':[11]}]}}
        payload={'chart': {'result':[result]}}
        expected=dt.date(2026,9,21)
        self.assertEqual(len(_completed_session_rows('AAA',payload,expected,'2026-09-22T01:00:00Z')),1)
        next_session = copy.deepcopy(payload)
        next_session['chart']['result'][0]['meta']['currentTradingPeriod']['regular']['end'] = end + 86400
        self.assertEqual(len(_completed_session_rows('AAA',next_session,expected,'2026-09-22T04:01:00Z')),1)
        self.assertEqual(_completed_session_rows('AAA',next_session,expected,'2026-09-21T19:00:00Z'),[])

        self.assertEqual(_completed_session_rows('AAA',payload,expected,'2026-09-21T19:00:00Z'),[])
        self.assertEqual(_completed_session_rows('AAA',payload,dt.date(2026,9,18),'2026-09-22T01:00:00Z'),[])
        for field in ['adjclose','high']:
            bad=copy.deepcopy(payload)
            if field=='adjclose':bad['chart']['result'][0]['indicators']['adjclose']=[]
            else:bad['chart']['result'][0]['indicators']['quote'][0]['high']=[8]
            self.assertEqual(_completed_session_rows('AAA',bad,expected,'2026-09-22T01:00:00Z'),[])

    def test_stale_dataset_is_rejected_before_analysis(self):
        fixture=Path(__file__).parent/'fixtures'/'prices.csv'
        with tempfile.TemporaryDirectory() as temp:
            args=build_parser().parse_args(['run','--provider','csv','--prices-file',str(fixture),'--output-dir',temp,'--expected-data-end-date','2026-09-21'])
            with self.assertRaisesRegex(ValueError,'Stale prices'):
                run(args)
            self.assertFalse((Path(temp)/'metadata.json').exists())

    def test_live_run_rejects_stale_benchmark_even_when_stock_prices_are_current(self):
        with tempfile.TemporaryDirectory() as temp:
            args=build_parser().parse_args(['run','--provider','yfinance_yahoo_chart','--tickers','AAA','--benchmark-tickers','QQQ','--output-dir',temp,'--expected-data-end-date','2026-09-21'])
            stocks=[{'ticker':'AAA','date':dt.date(2026,9,21)}]
            benchmark=[{'ticker':'QQQ','date':dt.date(2026,9,18)}]
            with mock.patch('best_factor.cli._fetch_live_prices',side_effect=[(stocks,{}),(benchmark,{})]):
                with self.assertRaisesRegex(ValueError,'No benchmark reaches completed session'):
                    run(args)

    def test_one_day_bulk_retry_recovers_stale_symbols_without_chart_requests(self):
        old = {'ticker': 'AAA', 'date': dt.date(2026, 9, 18), 'adj_close': 5.0}
        fresh = {'ticker': 'AAA', 'date': dt.date(2026, 9, 21), 'adj_close': 10.0}
        with mock.patch('best_factor.data.fetch_yfinance_prices', side_effect=[([old], {}), ([fresh], {})]) as bulk, mock.patch('best_factor.data.fetch_yahoo_chart_prices') as chart:
            rows, meta = fetch_resilient_prices(['AAA'], '5y', expected_end_date=fresh['date'])
        chart.assert_not_called()
        self.assertEqual(bulk.call_args_list[1].args[1], '1d')
        self.assertEqual(meta['bounded_session_recovered_tickers'], ['AAA'])
        self.assertEqual([row['date'] for row in rows], [old['date'], fresh['date']])
