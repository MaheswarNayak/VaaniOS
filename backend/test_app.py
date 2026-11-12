"""
Unit and integration tests for VaaniOS Flask backend API and SQLite database.
"""

import os
import tempfile
import unittest
import json
from datetime import datetime, timedelta

import database
from app import app


class VaaniOSTestCase(unittest.TestCase):
    def setUp(self):
        # Create a temporary database file for isolated testing
        self.db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.environ["VAANIOS_DB_PATH"] = self.temp_db_path
        database.DB_PATH = self.temp_db_path

        # Initialize schema in temporary database
        database.init_db(self.temp_db_path)

        # Set up Flask test client
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    def test_health_check(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data, {"status": "ok"})

    def test_create_transaction_success(self):
        # Test sale creation
        sale_payload = {
            "type": "sale",
            "amount": 2500,
            "description": "Retail Sale - Item #402"
        }
        res = self.client.post("/api/transactions", json=sale_payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertIn("id", data)
        self.assertEqual(data["type"], "sale")
        self.assertEqual(data["amount"], 2500)
        self.assertEqual(data["description"], "Retail Sale - Item #402")
        self.assertIn("timestamp", data)

        # Test expense creation
        expense_payload = {
            "type": "expense",
            "amount": 450,
            "description": "Electricity Bill"
        }
        res_exp = self.client.post("/api/transactions", json=expense_payload)
        self.assertEqual(res_exp.status_code, 201)
        data_exp = res_exp.get_json()
        self.assertEqual(data_exp["type"], "expense")
        self.assertEqual(data_exp["amount"], 450)

    def test_create_transaction_validation_errors(self):
        # Invalid type
        res = self.client.post("/api/transactions", json={"type": "transfer", "amount": 100})
        self.assertEqual(res.status_code, 400)

        # Negative amount
        res = self.client.post("/api/transactions", json={"type": "sale", "amount": -50})
        self.assertEqual(res.status_code, 400)

        # Zero amount
        res = self.client.post("/api/transactions", json={"type": "sale", "amount": 0})
        self.assertEqual(res.status_code, 400)

        # Non-integer amount
        res = self.client.post("/api/transactions", json={"type": "sale", "amount": 99.99})
        self.assertEqual(res.status_code, 400)

        # Non-JSON payload
        res = self.client.post("/api/transactions", data="raw text", content_type="text/plain")
        self.assertEqual(res.status_code, 400)

    def test_get_transactions_limit_20(self):
        # Insert 25 transactions
        for i in range(1, 26):
            t_type = "sale" if i % 2 == 0 else "expense"
            database.insert_transaction(t_type, i * 10, f"Tx {i}", db_path=self.temp_db_path)

        res = self.client.get("/api/transactions")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("transactions", data)
        self.assertEqual(len(data["transactions"]), 20)
        # Verify ordering (latest first)
        self.assertEqual(data["transactions"][0]["id"], 25)

    def test_summary_today(self):
        # Initially 0
        res = self.client.get("/api/summary/today")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.get_json()["sales"], 0)
        self.assertEqual(res.get_json()["expenses"], 0)

        # Insert some transactions
        database.insert_transaction("sale", 1000, "Sale 1", db_path=self.temp_db_path)
        database.insert_transaction("sale", 500, "Sale 2", db_path=self.temp_db_path)
        database.insert_transaction("expense", 300, "Expense 1", db_path=self.temp_db_path)

        res2 = self.client.get("/api/summary/today")
        self.assertEqual(res2.status_code, 200)
        summary = res2.get_json()
        self.assertEqual(summary["sales"], 1500)
        self.assertEqual(summary["expenses"], 300)
        self.assertEqual(summary["net_balance"], 1200)

    def test_database_schema_constraints(self):
        # Verify SQLite-level CHECK constraints for invalid type and negative amount
        import sqlite3

        with self.assertRaises(sqlite3.IntegrityError):
            database.insert_transaction("invalid_type", 100, db_path=self.temp_db_path)

        with self.assertRaises(sqlite3.IntegrityError):
            database.insert_transaction("sale", -10, db_path=self.temp_db_path)

    def test_transcode_audio_to_wav_direct(self):
        from app import transcode_audio_to_wav
        import subprocess
        import imageio_ffmpeg

        # Read sample wav
        sample_path = os.path.join(os.path.dirname(__file__), "test_vaani_sample.wav")
        with open(sample_path, "rb") as f:
            sample_wav = f.read()

        # Generate mock WebM bytes
        cmd_webm = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", "pipe:0", "-f", "webm", "pipe:1"]
        proc = subprocess.Popen(cmd_webm, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        webm_bytes, _ = proc.communicate(input=sample_wav)

        # Transcode WebM to WAV
        wav_out = transcode_audio_to_wav(webm_bytes)
        self.assertTrue(wav_out.startswith(b"RIFF"))
        self.assertEqual(wav_out[8:12], b"WAVE")

        # Test empty bytes raises ValueError
        with self.assertRaises(ValueError):
            transcode_audio_to_wav(b"")

    def test_voice_command_multipart_transcoding(self):
        from unittest.mock import patch
        import io
        import subprocess
        import imageio_ffmpeg

        sample_path = os.path.join(os.path.dirname(__file__), "test_vaani_sample.wav")
        with open(sample_path, "rb") as f:
            sample_wav = f.read()

        # Generate WebM audio as sent by MediaRecorder
        cmd_webm = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", "pipe:0", "-f", "webm", "pipe:1"]
        proc = subprocess.Popen(cmd_webm, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        webm_bytes, _ = proc.communicate(input=sample_wav)

        with patch("gnani_client.transcribe_audio") as mock_stt, \
             patch("gnani_client.synthesize_speech") as mock_tts:

            # Ensure mock returns valid response
            mock_stt.return_value = {
                "success": True,
                "transcript": "pachees sau rupaye ki sale hui"
            }
            mock_tts.return_value = {
                "success": True,
                "audio_bytes": b"RIFFsynthesizedwav",
                "content_type": "audio/wav"
            }

            # Send multipart upload as a .webm file from browser MediaRecorder
            data = {
                "audio_file": (io.BytesIO(webm_bytes), "recording.webm", "audio/webm"),
                "auto_commit": "true"
            }
            response = self.client.post(
                "/api/voice/command",
                data=data,
                content_type="multipart/form-data"
            )
            self.assertEqual(response.status_code, 200)

            # CRITICAL VERIFICATION:
            # gnani_client.transcribe_audio must receive standard WAV bytes (starts with RIFF),
            # NOT raw WebM bytes!
            self.assertTrue(mock_stt.called)
            passed_kwargs = mock_stt.call_args.kwargs
            passed_audio_bytes = passed_kwargs["audio_bytes"]
            self.assertTrue(passed_audio_bytes.startswith(b"RIFF"))
            self.assertEqual(passed_audio_bytes[8:12], b"WAVE")
            self.assertEqual(passed_kwargs["filename"], "command.wav")

            # Verify parsed response
            json_data = response.get_json()
            self.assertTrue(json_data["success"])
            self.assertTrue(json_data["executed"])
            self.assertTrue(json_data["transaction_saved"])
            self.assertEqual(json_data["parsed"]["amount"], 2500)

    def test_voice_command_requires_confirmation_generates_action_id(self):
        from app import PENDING_ACTIONS
        from unittest.mock import patch

        with patch("gnani_client.synthesize_speech") as mock_tts:
            mock_tts.return_value = {
                "success": True,
                "audio_bytes": b"RIFFmock",
                "content_type": "audio/wav"
            }

            # Unclear amount triggers clarification_needed and requires_confirmation
            payload = {"transcript": "aaj paanch ka maal gaya"}
            res = self.client.post("/api/voice/command", json=payload)
            self.assertEqual(res.status_code, 200)
            data = res.get_json()

            self.assertTrue(data["requires_confirmation"])
            self.assertIn("action_id", data)
            self.assertIsNotNone(data["action_id"])
            action_id = data["action_id"]

            # Must be saved in PENDING_ACTIONS global dictionary
            self.assertIn(action_id, PENDING_ACTIONS)

    def test_voice_confirm_success(self):
        from app import PENDING_ACTIONS

        # Manually seed an action in PENDING_ACTIONS
        action_id = "test-action-123"
        PENDING_ACTIONS[action_id] = [
            {"type": "sale", "amount": 1500, "description": "counter sale"}
        ]

        confirm_payload = {
            "action_id": action_id,
            "confirmed": True
        }
        res = self.client.post("/api/voice/confirm", json=confirm_payload)
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertEqual(data, {
            "success": True,
            "transaction_saved": True,
            "message": "Transaction successfully saved."
        })

        # Action must be popped from PENDING_ACTIONS
        self.assertNotIn(action_id, PENDING_ACTIONS)

        # Verify transaction persisted to SQLite and summary updated
        summary = database.get_summary_today(db_path=self.temp_db_path)
        self.assertEqual(summary["sales"], 1500)
        txs = database.get_latest_transactions(limit=1, db_path=self.temp_db_path)
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["type"], "sale")
        self.assertEqual(txs[0]["amount"], 1500)

    def test_voice_confirm_cancelled(self):
        from app import PENDING_ACTIONS

        action_id = "test-cancel-456"
        PENDING_ACTIONS[action_id] = [
            {"type": "expense", "amount": 600, "description": "tea"}
        ]

        confirm_payload = {
            "action_id": action_id,
            "confirmed": False
        }
        res = self.client.post("/api/voice/confirm", json=confirm_payload)
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["transaction_saved"])
        self.assertIn("cancelled", data["message"].lower())

        # Action popped from PENDING_ACTIONS
        self.assertNotIn(action_id, PENDING_ACTIONS)

        # Nothing saved in DB
        summary = database.get_summary_today(db_path=self.temp_db_path)
        self.assertEqual(summary["expenses"], 0)

    def test_voice_confirm_errors(self):
        # Missing action_id
        res_missing = self.client.post("/api/voice/confirm", json={"confirmed": True})
        self.assertEqual(res_missing.status_code, 400)

        # Non-existent action_id
        res_not_found = self.client.post("/api/voice/confirm", json={"action_id": "nonexistent", "confirmed": True})
        self.assertEqual(res_not_found.status_code, 404)

    def test_summary_weekly_empty(self):
        res = self.client.get("/api/summary/weekly")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["dates"]), 7)
        self.assertEqual(data["sales"], [0] * 7)
        self.assertEqual(data["expenses"], [0] * 7)
        self.assertEqual(len(data["days"]), 7)

    def test_summary_weekly_with_transactions(self):
        # Insert transactions for today, 2 days ago, 6 days ago, and 8 days ago (out of range)
        with database.get_db_cursor(self.temp_db_path) as cursor:
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, DATETIME('now'))",
                ("sale", 1000, "Today sale")
            )
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, DATETIME('now'))",
                ("expense", 250, "Today expense")
            )
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, DATETIME('now', '-2 days'))",
                ("sale", 2000, "Two days ago sale")
            )
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, DATETIME('now', '-6 days'))",
                ("expense", 400, "Six days ago expense")
            )
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, DATETIME('now', '-8 days'))",
                ("sale", 9999, "Old sale outside 7-day window")
            )

        res = self.client.get("/api/summary/weekly")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(len(data["labels"]), 7)
        self.assertEqual(len(data["sales"]), 7)
        self.assertEqual(len(data["expenses"]), 7)

        # Index 6 is today, index 4 is 2 days ago, index 0 is 6 days ago
        self.assertEqual(data["sales"][6], 1000)
        self.assertEqual(data["expenses"][6], 250)
        self.assertEqual(data["sales"][4], 2000)
        self.assertEqual(data["expenses"][0], 400)
        # 8-day-old transaction must not be included
        self.assertEqual(sum(data["sales"]), 3000)
        self.assertEqual(sum(data["expenses"]), 650)

    def test_undo_last_transaction_success(self):
        tx1 = database.insert_transaction("sale", 1200, "First sale", db_path=self.temp_db_path)
        tx2 = database.insert_transaction("expense", 300, "Second expense", db_path=self.temp_db_path)

        res = self.client.post("/api/transaction/undo")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertTrue(data["success"])
        self.assertEqual(data["message"], "Last transaction undone.")
        self.assertEqual(data["deleted_transaction"]["id"], tx2["id"])
        self.assertEqual(data["deleted_transaction"]["amount"], 300)
        self.assertEqual(data["updated_summary"], {
            "sales": 1200,
            "expenses": 0,
            "net_balance": 1200
        })

        remaining = database.get_latest_transactions(db_path=self.temp_db_path)
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0]["id"], tx1["id"])

    def test_undo_last_transaction_empty_db(self):
        res = self.client.post("/api/transaction/undo")
        self.assertEqual(res.status_code, 404)
        data = res.get_json()
        self.assertFalse(data["success"])
        self.assertIn("no transaction", data["message"].lower())

    def test_date_filter_transactions_and_summary(self):
        # Insert transactions with different dates
        with database.get_db_cursor(self.temp_db_path) as cursor:
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, ?)",
                ("sale", 5000, "Historical Sale", "2026-10-15 11:30:00")
            )
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, ?)",
                ("expense", 1200, "Historical Expense", "2026-10-15 14:00:00")
            )
            cursor.execute(
                "INSERT INTO transactions (type, amount, description, timestamp) VALUES (?, ?, ?, ?)",
                ("sale", 300, "Today Sale", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )

        # 1. Summary for historical date
        res = self.client.get("/api/summary/today?date=2026-10-15")
        self.assertEqual(res.status_code, 200)
        summary = res.get_json()
        self.assertEqual(summary["sales"], 5000)
        self.assertEqual(summary["expenses"], 1200)
        self.assertEqual(summary["net_balance"], 3800)

        # 2. Transactions for historical date
        res_tx = self.client.get("/api/transactions?date=2026-10-15")
        self.assertEqual(res_tx.status_code, 200)
        tx_data = res_tx.get_json()
        self.assertEqual(tx_data["count"], 2)
        descriptions = [t["description"] for t in tx_data["transactions"]]
        self.assertIn("Historical Sale", descriptions)
        self.assertIn("Historical Expense", descriptions)
        self.assertNotIn("Today Sale", descriptions)

        # 3. Summary without date parameter should only reflect today's transaction
        res_today = self.client.get("/api/summary/today")
        self.assertEqual(res_today.status_code, 200)
        self.assertEqual(res_today.get_json()["sales"], 300)
        self.assertEqual(res_today.get_json()["expenses"], 0)


if __name__ == "__main__":
    unittest.main()


