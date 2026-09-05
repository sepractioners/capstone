"""End-to-end pipeline test for the JSON/CSV structured path.

Deliberately avoids any LLM call (JSON/CSV records are already
structured) so it exercises the real graph wiring, the real MCP server
spawned as a subprocess over stdio, and the real ingest_contract_handler
fast-forward - without needing an API key.
"""
import asyncio
import base64
import json
import os
import tempfile
import unittest

from extraction_agent.mcp_client import get_source_document_via_mcp
from extraction_agent.pipeline import run


class StructuredPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)

    def tearDown(self) -> None:
        os.remove(self.db_path)

    def test_json_record_ingests_via_real_mcp_server(self) -> None:
        fd, json_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(
                    {
                        "title": "Test Affiliate Agreement",
                        "contract_type": "affiliate-agreement",
                        "parties": [
                            {"legal_name": "Acme Corp", "roles": ["customer"]},
                            {"legal_name": "Widgets Inc", "roles": ["affiliate"]},
                        ],
                        "effective_date": "2020-01-01",
                    },
                    f,
                )

            results = run(json_path, database_path=self.db_path)

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["lifecycle_status"], "approved")
            self.assertFalse(results[0]["already_ingested"])

            source = asyncio.run(
                get_source_document_via_mcp(results[0]["contract_id"], database_path=self.db_path)
            )
            self.assertEqual(source["media_type"], "application/json")
            recovered_record = json.loads(base64.b64decode(source["content_base64"]))
            self.assertEqual(recovered_record["title"], "Test Affiliate Agreement")
        finally:
            os.remove(json_path)

    def test_csv_rows_each_ingest_as_separate_contracts(self) -> None:
        fd, csv_path = tempfile.mkstemp(suffix=".csv")
        try:
            with os.fdopen(fd, "w", newline="") as f:
                f.write(
                    "title,contract_type,party_1_name,party_1_role,party_2_name,party_2_role,effective_date\n"
                    "Row One Agreement,vendor-agreement,Acme Corp,customer,Widgets Inc,vendor,2020-01-01\n"
                    "Row Two Agreement,vendor-agreement,Beta LLC,customer,Gamma Co,vendor,2021-01-01\n"
                )

            results = run(csv_path, database_path=self.db_path)

            self.assertEqual(len(results), 2)
            for r in results:
                self.assertEqual(r["lifecycle_status"], "approved")
        finally:
            os.remove(csv_path)

    def test_rerunning_same_json_file_is_idempotent(self) -> None:
        fd, json_path = tempfile.mkstemp(suffix=".json")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(
                    {
                        "title": "Repeat Agreement",
                        "contract_type": "vendor-agreement",
                        "parties": [
                            {"legal_name": "Acme Corp", "roles": ["customer"]},
                            {"legal_name": "Widgets Inc", "roles": ["vendor"]},
                        ],
                    },
                    f,
                )

            first = run(json_path, database_path=self.db_path)
            second = run(json_path, database_path=self.db_path)

            self.assertFalse(first[0]["already_ingested"])
            self.assertTrue(second[0]["already_ingested"])
            self.assertEqual(first[0]["contract_id"], second[0]["contract_id"])
        finally:
            os.remove(json_path)


if __name__ == "__main__":
    unittest.main()
