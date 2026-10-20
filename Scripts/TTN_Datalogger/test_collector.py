"""
Automated unit and integration test for TTN Data Collector.
Tests event parsing, SQLite persistence, latency/RTT calculations, and CSV/Excel export.
"""

import json
from pathlib import Path
import tempfile
import unittest

from data_processor import process_uplink_event, process_downlink_event, parse_iso_timestamp, parse_duration_seconds
from db_storage import Database
from csv_exporter import DataExporter


class TestTTNDataCollector(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory for tests
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_ttn.db"
        self.db = Database(self.db_path)
        self.exporter = DataExporter(self.db, self.test_dir)

    def tearDown(self):
        # Clean up files in temp directory
        import shutil
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_timestamp_and_duration_parsing(self):
        # ISO timestamp with Z
        dt1 = parse_iso_timestamp("2026-08-15T20:48:59.500Z")
        self.assertIsNotNone(dt1)
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.second, 59)

        # ISO timestamp with nanoseconds
        dt2 = parse_iso_timestamp("2026-08-15T20:48:59.123456789Z")
        self.assertIsNotNone(dt2)

        # Airtime parsing
        self.assertAlmostEqual(parse_duration_seconds("0.056576s"), 0.056576)
        self.assertAlmostEqual(parse_duration_seconds("0.120s"), 0.120)
        self.assertAlmostEqual(parse_duration_seconds(0.061), 0.061)

    def test_uplink_event_processing(self):
        sample_uplink = {
            "name": "as.up.data.forward",
            "time": "2026-08-15T20:49:00.100Z",
            "identifiers": [{"device_ids": {"device_id": "sensor-tulcan-01"}}],
            "correlation_ids": ["as:up:01E191YN5F2HMBQCBCVRF731VY", "gs:conn:01E..."],
            "data": {
                "end_device_ids": {"device_id": "sensor-tulcan-01"},
                "received_at": "2026-08-15T20:49:00.050Z",
                "uplink_message": {
                    "f_cnt": 42,
                    "f_port": 1,
                    "confirmed": True,
                    "frm_payload": "AQIDBA==",
                    "decoded_payload": {"temperature": 23.4, "humidity": 65.2},
                    "consumed_airtime": "0.056576s",
                    "rx_metadata": [
                        {
                            "gateway_ids": {"gateway_id": "gw-tulcan-campus"},
                            "time": "2026-08-15T20:48:59.500Z",
                            "timestamp": 3313328983,
                            "rssi": -78.0,
                            "snr": 8.5,
                            "channel_index": 4
                        }
                    ],
                    "settings": {
                        "data_rate": {
                            "lora": {
                                "bandwidth": 125000,
                                "spreading_factor": 7
                            }
                        },
                        "coding_rate": "4/5",
                        "frequency": 915200000
                    }
                }
            }
        }

        processed = process_uplink_event(sample_uplink)
        self.assertEqual(processed["device_id"], "sensor-tulcan-01")
        self.assertEqual(processed["gateway_id"], "gw-tulcan-campus")
        self.assertEqual(processed["rssi_dbm"], -78.0)
        self.assertEqual(processed["snr_db"], 8.5)
        self.assertEqual(processed["sf"], 7)
        self.assertEqual(processed["bw_hz"], 125000)
        self.assertEqual(processed["frequency_hz"], 915200000)
        self.assertEqual(processed["f_cnt"], 42)
        self.assertEqual(processed["correlation_id"], "as:up:01E191YN5F2HMBQCBCVRF731VY")
        self.assertAlmostEqual(processed["airtime_s"], 0.056576)
        self.assertAlmostEqual(processed["network_delay_s"], 0.550)  # 20:49:00.050 - 20:48:59.500
        self.assertAlmostEqual(processed["total_uplink_delay_s"], 0.606576, places=4)  # 0.056576 + 0.550

        # Insert to SQLite and verify
        row_id = self.db.insert_uplink(processed)
        self.assertGreater(row_id, 0)
        uplinks = self.db.fetch_all_uplinks()
        self.assertEqual(len(uplinks), 1)
        self.assertEqual(uplinks[0]["device_id"], "sensor-tulcan-01")
        self.assertAlmostEqual(uplinks[0]["total_uplink_delay_s"], 0.606576, places=4)

    def test_downlink_ack_and_rtt_view(self):
        cid = "as:up:test-rtt-correlation-123"

        # 1. Insert confirmed uplink
        uplink_data = {
            "timestamp_utc": "2026-08-15T20:00:00.000Z",
            "device_id": "sensor-01",
            "gateway_id": "gw-tulcan",
            "rssi_dbm": -82.0,
            "snr_db": 7.0,
            "gateway_time": "2026-08-15T20:00:00.000Z",
            "concentrator_us": 1000000,
            "received_at": "2026-08-15T20:00:00.500Z",
            "airtime_s": 0.061,
            "network_delay_s": 0.500,
            "sf": 7,
            "bw_hz": 125000,
            "coding_rate": "4/5",
            "frequency_hz": 915200000,
            "f_cnt": 10,
            "is_confirmed": 1,
            "correlation_id": cid
        }
        self.db.insert_uplink(uplink_data)

        # 2. Downlink lifecycle events for the same correlation_id
        # Step A: Schedule Attempt
        evt_attempt = {
            "name": "ns.down.data.schedule.attempt",
            "time": "2026-08-15T20:00:00.550Z",
            "correlation_ids": [cid],
            "data": {"end_device_ids": {"device_id": "sensor-01"}}
        }
        p_attempt = process_downlink_event(evt_attempt)
        self.db.insert_or_update_downlink(p_attempt)

        # Step B: Schedule Success
        evt_success = {
            "name": "ns.down.data.schedule.success",
            "time": "2026-08-15T20:00:00.650Z",
            "correlation_ids": [cid],
            "data": {"end_device_ids": {"device_id": "sensor-01"}}
        }
        p_success = process_downlink_event(evt_success)
        self.db.insert_or_update_downlink(p_success)

        # Step C: Gateway Send
        evt_send = {
            "name": "gs.down.send",
            "time": "2026-08-15T20:00:00.700Z",
            "correlation_ids": [cid],
            "data": {"end_device_ids": {"device_id": "sensor-01"}}
        }
        p_send = process_downlink_event(evt_send)
        self.db.insert_or_update_downlink(p_send)

        # Step D: Gateway TX Success (ACK sent over the air in RX1 at T+1.0s)
        evt_tx = {
            "name": "gs.down.tx.success",
            "time": "2026-08-15T20:00:01.000Z",
            "correlation_ids": [cid],
            "data": {"end_device_ids": {"device_id": "sensor-01"}}
        }
        p_tx = process_downlink_event(evt_tx)
        self.db.insert_or_update_downlink(p_tx)

        # Verify downlinks table
        downlinks = self.db.fetch_all_downlinks()
        self.assertEqual(len(downlinks), 1)
        self.assertEqual(downlinks[0]["correlation_id"], cid)
        self.assertEqual(downlinks[0]["schedule_attempt_at"], "2026-08-15T20:00:00.550Z")
        self.assertEqual(downlinks[0]["tx_success_at"], "2026-08-15T20:00:01.000Z")

        # Verify RTT SQL View calculation
        rtt_rows = self.db.fetch_rtt_view()
        self.assertEqual(len(rtt_rows), 1)
        # RTT = 20:00:01.000 - 20:00:00.000 = 1.000 second
        self.assertAlmostEqual(rtt_rows[0]["rtt_s"], 1.0, places=2)
        # Cloud Turnaround = 20:00:00.700 - 20:00:00.500 = 0.200 second
        self.assertAlmostEqual(rtt_rows[0]["cloud_turnaround_s"], 0.200, places=2)
        # NS Scheduling = 20:00:00.650 - 20:00:00.550 = 0.100 second
        self.assertAlmostEqual(rtt_rows[0]["ns_scheduling_s"], 0.100, places=2)
        # TX Delay = 20:00:01.000 - 20:00:00.700 = 0.300 second
        self.assertAlmostEqual(rtt_rows[0]["tx_delay_s"], 0.300, places=2)
        # Verify RTT Decomposition: 0.500 (uplink) + 0.200 (cloud) + 0.300 (downlink) = 1.000 (RTT)
        self.assertAlmostEqual(rtt_rows[0]["network_delay_s"] + rtt_rows[0]["cloud_turnaround_s"] + rtt_rows[0]["tx_delay_s"], 1.000, places=2)
        # Verify rtt_phy_complete = airtime_s + rtt_s + airtime_downlink_s
        expected_phy_rtt = rtt_rows[0]["airtime_s"] + rtt_rows[0]["rtt_s"] + rtt_rows[0]["airtime_downlink_s"]
        self.assertAlmostEqual(rtt_rows[0]["rtt_phy_complete"], expected_phy_rtt, places=4)
        # Verify effective_dl_window_delay_au915 = 5.000 - 1.000 = 4.000 s
        self.assertAlmostEqual(rtt_rows[0]["effective_dl_window_delay_au915"], 4.000, places=2)

    def test_export_csv_and_excel(self):
        # Insert test records
        for i in range(5):
            self.db.insert_uplink({
                "timestamp_utc": f"2026-08-15T20:0{i}:00Z",
                "device_id": f"sensor-{i}",
                "gateway_id": "gw-tulcan",
                "rssi_dbm": -70.0 - i,
                "snr_db": 9.0 - (i * 0.5),
                "gateway_time": f"2026-08-15T20:0{i}:00Z",
                "concentrator_us": 1000000 + i,
                "received_at": f"2026-08-15T20:0{i}:00.400Z",
                "airtime_s": 0.055,
                "network_delay_s": 0.400,
                "sf": 7,
                "bw_hz": 125000,
                "coding_rate": "4/5",
                "frequency_hz": 915200000,
                "f_cnt": i,
                "is_confirmed": 0,
                "correlation_id": f"as:up:cid-{i}"
            })

        self.db.insert_gateway_stats({
            "polled_at": "2026-08-15T20:00:00Z",
            "gateway_id": "gw-tulcan",
            "connected_at": "2026-08-15T18:00:00Z",
            "uplink_count": 150,
            "downlink_count": 25
        })

        results = self.exporter.export_all(prefix="test_export")
        self.assertIn("excel", results)
        self.assertTrue(results["excel"].exists())
        self.assertIn("csv_uplinks", results)
        self.assertTrue(results["csv_uplinks"].exists())
        self.assertIn("csv_gw_stats", results)
        self.assertTrue(results["csv_gw_stats"].exists())

        # Verify summary stats
        summary = self.db.get_summary_statistics()
        self.assertEqual(summary["total_uplinks"], 5)
        self.assertEqual(summary["min_rssi"], -74.0)
        self.assertEqual(summary["max_rssi"], -70.0)
        self.assertIn("global_pdr_percent", summary)
        self.assertIn("csv_pdr", results)
        self.assertTrue(results["csv_pdr"].exists())

    def test_pdr_calculation_with_gaps(self):
        # Simulate device sending frames 1, 2, 4, 5 (frame 3 was lost)
        # Expected: 5 packets (from 1 to 5), Received: 4 packets, Lost: 1, PDR: 80%
        for f in [1, 2, 4, 5]:
            self.db.insert_uplink({
                "timestamp_utc": f"2026-08-15T21:0{f}:00Z",
                "device_id": "sensor-pdr-test",
                "f_cnt": f,
                "rssi_dbm": -80.0,
                "snr_db": 8.0,
                "airtime_s": 0.05,
                "network_delay_s": 0.3
            })

        pdr_list = self.db.get_pdr_statistics()
        self.assertEqual(len(pdr_list), 1)
        dev_stat = pdr_list[0]
        self.assertEqual(dev_stat["device_id"], "sensor-pdr-test")
        self.assertEqual(dev_stat["min_fcnt"], 1)
        self.assertEqual(dev_stat["max_fcnt"], 5)
        self.assertEqual(dev_stat["expected_count"], 5)
        self.assertEqual(dev_stat["received_count"], 4)
        self.assertEqual(dev_stat["lost_count"], 1)
    def test_session_isolated_pdr(self):
        # Session 1: Frames 10, 11, 12, 13 (4 packets expected, 4 received -> 100% PDR)
        self.db.start_session("sess_01")
        for f in [10, 11, 12, 13]:
            self.db.insert_uplink({
                "timestamp_utc": f"2026-08-15T21:00:{f}Z",
                "device_id": "node-1",
                "f_cnt": f,
                "rssi_dbm": -60.0,
                "snr_db": 10.0
            }, session_id="sess_01")
        self.db.end_session("sess_01")

        pdr_sess1 = self.db.get_pdr_statistics(session_id="sess_01")
        self.assertEqual(len(pdr_sess1), 1)
        self.assertEqual(pdr_sess1[0]["received_count"], 4)
        self.assertEqual(pdr_sess1[0]["expected_count"], 4)
        self.assertEqual(pdr_sess1[0]["lost_count"], 0)
        self.assertAlmostEqual(pdr_sess1[0]["pdr_percent"], 100.0)

        # Gap occurs while app was NOT running: Frames 14..49 transmitted offline
        # Session 2 starts at Frame 50: Frames 50, 51, 52, 53, 54 (5 expected, 5 received -> 100% PDR)
        self.db.start_session("sess_02")
        for f in [50, 51, 52, 53, 54]:
            self.db.insert_uplink({
                "timestamp_utc": f"2026-08-15T22:00:{f-50}Z",
                "device_id": "node-1",
                "f_cnt": f,
                "rssi_dbm": -62.0,
                "snr_db": 9.5
            }, session_id="sess_02")
        self.db.end_session("sess_02")

        pdr_sess2 = self.db.get_pdr_statistics(session_id="sess_02")
        self.assertEqual(len(pdr_sess2), 1)
        self.assertEqual(pdr_sess2[0]["min_fcnt"], 50)
        self.assertEqual(pdr_sess2[0]["max_fcnt"], 54)
        self.assertEqual(pdr_sess2[0]["received_count"], 5)
        self.assertEqual(pdr_sess2[0]["expected_count"], 5)
        self.assertEqual(pdr_sess2[0]["lost_count"], 0)
        self.assertAlmostEqual(pdr_sess2[0]["pdr_percent"], 100.0)  # NOT penalizing offline gap!

        # Verify all sessions list
        sessions = self.db.fetch_all_sessions()
        self.assertEqual(len(sessions), 2)

    def test_pdr_with_counter_reset(self):
        # Scenario: Node sends frames 1765, 1766, 1768 (frame 1767 lost -> 1 loss)
        # Then node is rebooted and counter resets to 0:
        # Segment 2 sends frames 0, 1, 3 (frame 2 lost -> 1 loss)
        # Total expected: Segment 1 (1768-1765+1 = 4) + Segment 2 (3-0+1 = 4) = 8 expected
        # Total received: 3 (seg 1) + 3 (seg 2) = 6 received
        # Total lost: 2 packets
        # PDR = 6 / 8 = 75.0%
        for f in [1765, 1766, 1768, 0, 1, 3]:
            self.db.insert_uplink({
                "timestamp_utc": "2026-08-15T23:00:00Z",
                "device_id": "sensor-reboot",
                "f_cnt": f,
                "rssi_dbm": -70.0,
                "snr_db": 10.0
            })

        pdr_list = self.db.get_pdr_statistics()
        reboot_dev = [d for d in pdr_list if d["device_id"] == "sensor-reboot"][0]
        self.assertEqual(reboot_dev["resets_detected"], 1)
        self.assertEqual(reboot_dev["expected_count"], 8)
        self.assertEqual(reboot_dev["received_count"], 6)
        self.assertEqual(reboot_dev["lost_count"], 2)
        self.assertAlmostEqual(reboot_dev["pdr_percent"], 75.0)


if __name__ == "__main__":
    unittest.main()
