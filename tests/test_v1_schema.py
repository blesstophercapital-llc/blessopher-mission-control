import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VAULT = Path("/Users/christopherbless/Documents/TomMemory-2.0")


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_mission_control", ROOT / "scripts" / "generate-mission-control.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class V1SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.generator = load_generator()
        cls.data = cls.generator.build_data(VAULT, ROOT / "mission-control.json")

    def test_command_center_schema(self):
        section = self.data["commandCenter"]
        for key in ["diagnosis", "scorecards", "primaryBottleneck", "nextActions"]:
            self.assertIn(key, section)
        for card in section["scorecards"]:
            for key in ["label", "value", "note", "tone", "source"]:
                self.assertIn(key, card)

    def test_revenue_funnel_schema(self):
        section = self.data["revenueFunnel"]
        for key in ["stages", "diagnosis", "missingInstrumentation"]:
            self.assertIn(key, section)
        for stage in section["stages"]:
            for key in ["label", "value", "status", "source", "tone"]:
                self.assertIn(key, stage)

    def test_seo_opportunities_schema(self):
        section = self.data["seoOpportunities"]
        for key in ["scorecards", "opportunities", "queryBuckets", "actions"]:
            self.assertIn(key, section)
        for opportunity in section["opportunities"]:
            for key in ["query", "clicks", "impressions", "ctr", "position", "bucket", "recommendedAction"]:
                self.assertIn(key, opportunity)

    def test_channel_ops_schema(self):
        section = self.data["channelOps"]
        self.assertIn("channels", section)
        rows = section["channels"]
        self.assertGreaterEqual(len(rows), 5)
        for row in rows:
            for key in ["channel", "status", "blocker", "nextAction", "tone"]:
                self.assertIn(key, row)

    def test_unit_economics_schema(self):
        section = self.data["unitEconomics"]
        for key in ["price", "cogs", "channels", "breakEvenCac", "targetCac", "notes"]:
            self.assertIn(key, section)
        self.assertIn("$39.99", section["price"])
        self.assertIn("$6.49", section["cogs"])

    def test_generator_uses_current_tommemory_vault(self):
        self.assertEqual(self.generator.DEFAULT_VAULT, VAULT)
        self.assertEqual(self.data["meta"]["source"], str(VAULT))
        self.assertIn("Projects/Maintane/Maintane Overview.md", self.data["meta"]["sourceNotes"])
        self.assertIn("Projects/Maintane/Maintane Current Status.md", self.data["meta"]["sourceNotes"])
        self.assertIn("Tasks/Active Tasks.md", self.data["meta"]["sourceNotes"])

    def test_action_queue_schema(self):
        section = self.data["actionQueue"]
        for key in ["now", "next", "waiting", "done"]:
            self.assertIn(key, section)
        for column in ["now", "next", "waiting", "done"]:
            for action in section[column]:
                for key in ["title", "kpi", "impact", "owner", "status"]:
                    self.assertIn(key, action)

    def test_zoho_inventory_schema(self):
        section = self.data["zohoInventory"]
        for key in ["updatedLabel", "status", "message", "scorecards", "inventoryItems", "inventoryTypeSummary", "lowStockItems", "recentSalesOrders", "recentInvoices"]:
            self.assertIn(key, section)
        labels = {card["label"] for card in section["scorecards"]}
        self.assertIn("Zoho stock on hand", labels)
        self.assertIn("Zoho sales orders", labels)
        self.assertIn("Zoho invoices", labels)


if __name__ == "__main__":
    unittest.main()
