"""
Unit and integration tests for VaaniOS Voice Agent (agent.py) and Voice API endpoints (app.py).
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import agent
import database
from app import app


class AgentTestCase(unittest.TestCase):
    def setUp(self):
        # Create a fresh temporary database for isolated testing
        self.db_fd, self.temp_db_path = tempfile.mkstemp(suffix=".db")
        os.environ["VAANIOS_DB_PATH"] = self.temp_db_path
        database.init_db(self.temp_db_path)

        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.close(self.db_fd)
        if os.path.exists(self.temp_db_path):
            os.remove(self.temp_db_path)

    # -------------------------------------------------------------------------
    # 1. Number to Hinglish Words Conversion
    # -------------------------------------------------------------------------
    def test_number_to_hinglish_words(self):
        self.assertEqual(agent.number_to_hinglish_words(0), "shunya")
        self.assertEqual(agent.number_to_hinglish_words(500), "paanch sau")
        self.assertEqual(agent.number_to_hinglish_words(800), "aath sau")
        self.assertEqual(agent.number_to_hinglish_words(1500), "pandrah sau")
        self.assertEqual(agent.number_to_hinglish_words(2000), "do hazaar")
        self.assertEqual(agent.number_to_hinglish_words(2500), "pachees sau")
        self.assertEqual(agent.number_to_hinglish_words(10000), "das hazaar")
        self.assertEqual(agent.number_to_hinglish_words(2550), "do hazaar paanch sau pachaas")

    # -------------------------------------------------------------------------
    # 2. Happy Path - Single Actions
    # -------------------------------------------------------------------------
    def test_single_sale_numeric(self):
        res = agent.parse_voice_command("Aaj 2500 rupaye ki sale hui")
        self.assertEqual(res["intent"], "add_sale")
        self.assertEqual(res["type"], "sale")
        self.assertEqual(res["amount"], 2500)
        self.assertFalse(res["requires_confirmation"])
        self.assertIn("2500", res["response_text"])

    def test_single_sale_sell_keyword(self):
        for phrase in ["sell 500", "500 sell", "sell 1000 rupaye", "aaj 200 sell kiya"]:
            res = agent.parse_voice_command(phrase)
            self.assertEqual(res["intent"], "add_sale")
            self.assertEqual(res["type"], "sale")
            self.assertGreater(res["amount"], 0)
            self.assertFalse(res["requires_confirmation"])

    def test_all_required_keywords_presence(self):
        required_sales = [
            "sale", "sell", "bikri", "becha", "bechi", "aaye", "aaya", "jama",
            "kamaya", "received", "mile", "credit", "aamdani", "aamdhani", "profit", "bech diya"
        ]
        for kw in required_sales:
            self.assertIn(kw, agent.SALE_KEYWORDS)

        required_expenses = [
            "expense", "kharcha", "kharch", "maal", "kharida", "kharidi", "diye", "diya",
            "bill", "paid", "bought", "chukaya", "bhara", "debit", "gaya", "nuksan", "de diya"
        ]
        for kw in required_expenses:
            self.assertIn(kw, agent.EXPENSE_KEYWORDS)

    def test_expanded_keywords_intent_detection(self):
        # Test individual sale phrases
        sale_samples = [
            ("500 rupaye aaye", 500),
            ("1000 jama kiya", 1000),
            ("2000 kamaya", 2000),
            ("800 received", 800),
            ("300 mile", 300),
            ("5000 credit hua", 5000),
            ("1200 aamdani hui", 1200),
            ("400 profit hua", 400),
            ("1500 me bech diya", 1500)
        ]
        for phrase, expected_amt in sale_samples:
            res = agent.parse_voice_command(phrase)
            self.assertEqual(res["intent"], "add_sale", f"Failed for {phrase}")
            self.assertEqual(res["amount"], expected_amt, f"Failed for {phrase}")

        # Test individual expense phrases
        expense_samples = [
            ("500 kharch kiya", 500),
            ("600 rupaye diye", 600),
            ("700 ka bill bhara", 700),
            ("900 paid kiya", 900),
            ("1100 bought", 1100),
            ("450 chukaya", 450),
            ("350 bhara", 350),
            ("250 debit hua", 250),
            ("150 gaya", 150),
            ("800 ka nuksan hua", 800),
            ("950 de diya", 950)
        ]
        for phrase, expected_amt in expense_samples:
            res = agent.parse_voice_command(phrase)
            self.assertEqual(res["intent"], "add_expense", f"Failed for {phrase}")
            self.assertEqual(res["amount"], expected_amt, f"Failed for {phrase}")

    def test_single_expense_numeric(self):
        res = agent.parse_voice_command("₹800 ka maal kharida")
        self.assertEqual(res["intent"], "add_expense")
        self.assertEqual(res["type"], "expense")
        self.assertEqual(res["amount"], 800)
        self.assertFalse(res["requires_confirmation"])

    def test_get_daily_summary(self):
        phrases = [
            "aaj ka hisab batao",
            "today summary",
            "din ka hisaab kitna hai",
            "aaj ki report do"
        ]
        for p in phrases:
            res = agent.parse_voice_command(p)
            self.assertEqual(res["intent"], "get_daily_summary")
            self.assertFalse(res["requires_confirmation"])

    # -------------------------------------------------------------------------
    # 3. Hinglish Word Numbers (e.g. "pachchis sau", "do hazaar paanch sau")
    # -------------------------------------------------------------------------
    def test_hinglish_spoken_numbers(self):
        # 2500 variations
        res1 = agent.parse_voice_command("pachchis sau rupaye ki bikri hui")
        self.assertEqual(res1["amount"], 2500)
        self.assertEqual(res1["intent"], "add_sale")

        res2 = agent.parse_voice_command("pachees sau ki sale hui")
        self.assertEqual(res2["amount"], 2500)

        res3 = agent.parse_voice_command("do hazaar paanch sau rupaye jama hue")
        self.assertEqual(res3["amount"], 2500)

        # 500 and 800
        res4 = agent.parse_voice_command("paanch sau rupaye ka kharcha hua")
        self.assertEqual(res4["amount"], 500)
        self.assertEqual(res4["intent"], "add_expense")

        res5 = agent.parse_voice_command("aath sau rupaye diye")
        self.assertEqual(res5["amount"], 800)
        self.assertEqual(res5["intent"], "add_expense")

        # Fractions: dedh hazaar (1500) & dhai sau (250)
        res6 = agent.parse_voice_command("dedh hazaar ki sale")
        self.assertEqual(res6["amount"], 1500)

        res7 = agent.parse_voice_command("dhai sau ka kharcha")
        self.assertEqual(res7["amount"], 250)

        # Devanagari script: पच्चीस सौ की सेल
        res8 = agent.parse_voice_command("पच्चीस सौ की सेल हुई")
        self.assertEqual(res8["amount"], 2500)

        # Compound numbers: teen hazaar chaar sau chhiyattar (3476)
        res9 = agent.parse_voice_command("teen hazaar chaar sau chhiyattar rupaye ki sale hui")
        self.assertEqual(res9["amount"], 3476)
        self.assertEqual(res9["intent"], "add_sale")
        self.assertEqual(agent.number_to_hinglish_words(3476), "teen hazaar chaar sau chhiyattar")

        # Specific compound words (ikkis=21, chhiyattar=76, unasi=79, nawasi=89)
        self.assertEqual(agent.parse_voice_command("ikkis rupaye ki sale")["amount"], 21)
        self.assertEqual(agent.parse_voice_command("chhiyattar rupaye ka kharcha")["amount"], 76)
        self.assertEqual(agent.parse_voice_command("unasi rupaye ki sale")["amount"], 79)
        self.assertEqual(agent.parse_voice_command("nawasi rupaye ka kharcha")["amount"], 89)
        self.assertEqual(agent.parse_voice_command("दो हज़ार छिहत्तर रुपये की सेल")["amount"], 2076)

    # -------------------------------------------------------------------------
    # 4. Multi-Action Sentences (Sale and Expense together)
    # -------------------------------------------------------------------------
    def test_multi_action(self):
        transcript = "Aaj 2500 rupaye ki sale hui aur 800 rupaye ka maal kharida"
        res = agent.parse_voice_command(transcript)

        self.assertEqual(res["intent"], "multi_action")
        self.assertFalse(res["requires_confirmation"])
        self.assertIn("actions", res)
        self.assertEqual(len(res["actions"]), 2)

        action1 = res["actions"][0]
        self.assertEqual(action1["type"], "sale")
        self.assertEqual(action1["amount"], 2500)

        action2 = res["actions"][1]
        self.assertEqual(action2["type"], "expense")
        self.assertEqual(action2["amount"], 800)

    # -------------------------------------------------------------------------
    # 5. Safety & Ambiguity Handling
    # -------------------------------------------------------------------------
    def test_ambiguous_maal_requires_clarification(self):
        # "aaj paanch ka maal gaya" is ambiguous (could mean 500 or 5000)
        res = agent.parse_voice_command("aaj paanch ka maal gaya")
        self.assertEqual(res["intent"], "clarification_needed")
        self.assertTrue(res["requires_confirmation"])
        self.assertIsNotNone(res.get("clarification_prompt"))
        self.assertIn("paanch", res["clarification_prompt"])

    def test_missing_amount_requires_clarification(self):
        res = agent.parse_voice_command("sale record karo")
        self.assertEqual(res["intent"], "clarification_needed")
        self.assertTrue(res["requires_confirmation"])

    def test_zero_amount_requires_clarification(self):
        res = agent.parse_voice_command("shunya rupaye ki sale")
        self.assertEqual(res["intent"], "clarification_needed")
        self.assertTrue(res["requires_confirmation"])

    def test_empty_transcript_requires_clarification(self):
        res = agent.parse_voice_command("")
        self.assertEqual(res["intent"], "clarification_needed")
        self.assertTrue(res["requires_confirmation"])

    # -------------------------------------------------------------------------
    # 6. End-to-End API Integration (/api/voice/command)
    # -------------------------------------------------------------------------
    @patch("gnani_client.synthesize_speech")
    def test_api_voice_command_multi_action_execution(self, mock_tts):
        mock_tts.return_value = {
            "success": True,
            "audio_bytes": b"RIFFmockwavcontent",
            "content_type": "audio/wav"
        }

        payload = {
            "transcript": "Aaj 2500 rupaye ki sale hui aur 800 rupaye ka maal kharida",
            "auto_commit": True
        }
        res = self.client.post("/api/voice/command", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["executed"])
        self.assertTrue(data["transaction_saved"])
        self.assertFalse(data["requires_confirmation"])
        self.assertIsNotNone(data["audio_base64"])

        # Check database records
        summary = data["updated_summary"]
        self.assertEqual(summary["sales"], 2500)
        self.assertEqual(summary["expenses"], 800)
        self.assertEqual(summary["net_balance"], 1700)

    @patch("gnani_client.synthesize_speech")
    def test_api_voice_command_clarification(self, mock_tts):
        mock_tts.return_value = {
            "success": True,
            "audio_bytes": b"RIFFmockwavcontent",
            "content_type": "audio/wav"
        }

        payload = {"transcript": "aaj paanch ka maal gaya"}
        res = self.client.post("/api/voice/command", json=payload)
        self.assertEqual(res.status_code, 200)

        data = res.get_json()
        self.assertTrue(data["requires_confirmation"])
        self.assertFalse(data["executed"])
        self.assertEqual(data["parsed"]["intent"], "clarification_needed")
        self.assertIn("action_id", data)
        self.assertIsNotNone(data["action_id"])

    def test_voice_confirm_flow(self):
        from app import PENDING_ACTIONS
        action_id = "agent-confirm-test-id"
        PENDING_ACTIONS[action_id] = [
            {"type": "sale", "amount": 2500, "description": "counter sale"}
        ]

        res = self.client.post("/api/voice/confirm", json={"action_id": action_id, "confirmed": True})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data, {
            "success": True,
            "transaction_saved": True,
            "message": "Transaction successfully saved."
        })
        self.assertNotIn(action_id, PENDING_ACTIONS)
        self.assertEqual(database.get_summary_today(db_path=self.temp_db_path)["sales"], 2500)

    @patch("gnani_client.synthesize_speech")
    def test_api_speech_endpoint(self, mock_tts):
        mock_tts.return_value = {
            "success": True,
            "audio_bytes": b"RIFFsyntheticwavbytes",
            "content_type": "audio/wav"
        }

        # Test WAV binary return
        res = self.client.post("/api/speech", json={"text": "Namaste VaaniOS"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.mimetype, "audio/wav")
        self.assertEqual(res.data, b"RIFFsyntheticwavbytes")

        # Test Base64 format return
        res_b64 = self.client.post("/api/speech", json={"text": "Namaste VaaniOS", "format": "base64"})
        self.assertEqual(res_b64.status_code, 200)
        b64_data = res_b64.get_json()
        self.assertTrue(b64_data["success"])
        self.assertIn("audio_base64", b64_data)


if __name__ == "__main__":
    unittest.main()
