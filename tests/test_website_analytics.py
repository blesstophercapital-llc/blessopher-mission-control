import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_mission_control", ROOT / "scripts" / "generate-mission-control.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WebsiteAnalyticsTests(unittest.TestCase):
    def test_generated_data_contains_actionable_website_analytics_section(self):
        generator = load_generator()
        data = generator.build_data(Path("/Users/christopherbless/TomMemory"), ROOT / "mission-control.json")

        analytics = data["websiteAnalytics"]
        self.assertEqual(analytics["ga4"]["propertyId"], "532192988")
        self.assertEqual(analytics["searchConsole"]["siteUrl"], "sc-domain:getmaintane.com")
        self.assertGreaterEqual(len(analytics["scorecards"]), 4)
        self.assertGreaterEqual(len(analytics["actions"]), 3)
        self.assertTrue(any("SEO" in item[0] or "Search" in item[0] for item in analytics["diagnostics"]))

    def test_generated_data_contains_v1_operating_sections(self):
        generator = load_generator()
        data = generator.build_data(Path("/Users/christopherbless/TomMemory"), ROOT / "mission-control.json")

        for key in [
            "commandCenter",
            "revenueFunnel",
            "websiteAnalytics",
            "seoOpportunities",
            "channelOps",
            "unitEconomics",
            "actionQueue",
        ]:
            self.assertIn(key, data)

        self.assertGreaterEqual(len(data["commandCenter"]["scorecards"]), 4)
        self.assertGreaterEqual(len(data["revenueFunnel"]["stages"]), 5)
        self.assertGreaterEqual(len(data["seoOpportunities"]["opportunities"]), 3)
        self.assertGreaterEqual(len(data["actionQueue"]["now"]), 3)

    def test_v1_sections_have_required_fields_and_honest_pending_placeholders(self):
        generator = load_generator()
        data = generator.build_data(Path("/Users/christopherbless/TomMemory"), ROOT / "mission-control.json")

        command_center = data["commandCenter"]
        self.assertTrue({"diagnosis", "scorecards", "primaryBottleneck", "nextActions"}.issubset(command_center))
        for card in command_center["scorecards"]:
            self.assertTrue({"label", "value", "tone", "source"}.issubset(card))
        future_cards = [card for card in command_center["scorecards"] if "Revenue" in card["label"] or "Orders" in card["label"] or "Contribution Profit" in card["label"]]
        self.assertTrue(future_cards)
        for card in future_cards:
            self.assertIn("Pending", card["value"])
            self.assertTrue(card["source"].startswith("future:"))

        revenue_funnel = data["revenueFunnel"]
        self.assertTrue({"diagnosis", "stages", "missingInstrumentation"}.issubset(revenue_funnel))
        for stage in revenue_funnel["stages"]:
            self.assertTrue({"label", "value", "status", "source", "tone"}.issubset(stage))
        pending_stages = [stage for stage in revenue_funnel["stages"] if stage["status"] == "pending"]
        self.assertTrue(pending_stages)
        for stage in pending_stages:
            self.assertIn("Pending", stage["value"])
            self.assertTrue(stage["source"].startswith("future:"))

        expected_action_columns = {"now", "next", "waiting", "done"}
        self.assertEqual(set(data["actionQueue"]), expected_action_columns)
        for column in expected_action_columns:
            for action in data["actionQueue"][column]:
                self.assertTrue({"title", "kpi", "impact", "owner", "status"}.issubset(action))

    def test_fresh_output_path_builds_complete_data_model(self):
        generator = load_generator()
        with tempfile.TemporaryDirectory() as tmpdir:
            fresh_output = Path(tmpdir) / "mission-control-fresh.json"
            data = generator.build_data(Path("/Users/christopherbless/TomMemory"), fresh_output)

        for key in ["blockers", "influencers", "content", "finance", "tom", "commandCenter", "revenueFunnel", "seoOpportunities", "actionQueue"]:
            self.assertIn(key, data)
        self.assertGreaterEqual(len(data["blockers"]["columns"]), 3)
        self.assertGreaterEqual(len(data["blockers"]["metrics"]), 4)
        self.assertGreaterEqual(len(data["content"]["pillars"]), 5)
        self.assertGreaterEqual(len(data["finance"]["priceLadder"]), 4)

    def test_seo_bucket_boundaries_and_counts_are_consistent(self):
        generator = load_generator()
        self.assertEqual(generator._seo_bucket("maintane", 80.0, 1), "Brand Defense")
        self.assertEqual(generator._seo_bucket("septic treatment", 4.0, 1), "Quick Win")
        self.assertEqual(generator._seo_bucket("septic treatment", 49.9, 1), "Build Authority")
        self.assertEqual(generator._seo_bucket("septic treatment", 50.0, 1), "Long Shot")

        seo = generator.build_seo_opportunities({"websiteAnalytics": generator._default_website_analytics()})
        tracked = next(card for card in seo["scorecards"] if card["label"] == "Tracked opportunities")
        self.assertEqual(int(tracked["value"]), len(seo["opportunities"]))
        bucket_counts = {item["bucket"]: item["count"] for item in seo["queryBuckets"]}
        self.assertEqual(bucket_counts["Build Authority"], 2)
        self.assertEqual(bucket_counts["Brand Defense"], 1)

    def test_index_has_optimized_business_navigation(self):
        html = (ROOT / "index.html").read_text()
        for page_id in [
            "commandCenter",
            "revenue",
            "channels",
            "marketing",
            "productInventory",
            "customers",
            "finance",
            "tasks",
            "dataHealth",
            "tom",
        ]:
            self.assertIn(page_id, html)
            self.assertIn(f'id="{page_id}"', html)

        for label in [
            "Command Center",
            "Revenue",
            "Channels",
            "Marketing",
            "Product & Inventory",
            "Customers",
            "Finance",
            "Tasks",
            "Data Health",
            "Tom",
        ]:
            self.assertIn(label, html)

        self.assertNotIn("'launch'", html.lower())
        self.assertIn("Marketing includes creators", html)
        self.assertIn("Product & Inventory combined", html)
        self.assertIn("No Launch page", html)
        self.assertIn("data.websiteAnalytics", html)

    def test_index_has_hermes_operator_chat_bridge(self):
        html = (ROOT / "index.html").read_text()
        function_path = ROOT / "functions" / "api" / "tom-chat.js"
        worker = function_path.read_text()

        self.assertIn("Tom Operator Console", html)
        self.assertIn("/api/tom-chat", html)
        self.assertIn("No browser access key required", html)
        self.assertNotIn("X-Mission-Control-Key", html)
        self.assertNotIn("missionControlTomKey", html)
        self.assertIn("HERMES_API_BASE", worker)
        self.assertIn("HERMES_API_KEY", worker)
        self.assertNotIn("MISSION_CONTROL_TOM_KEY", worker)
        self.assertIn("/v1/chat/completions", worker)
        self.assertIn("X-Hermes-Session-Key", worker)
        self.assertIn("do not send emails", worker)

    def test_index_uses_mobile_hamburger_off_canvas_navigation(self):
        html = (ROOT / "index.html").read_text()
        self.assertIn("@media(max-width:860px)", html)
        self.assertIn('class="btn menu-toggle"', html)
        self.assertIn('id="mobileMenu"', html)
        self.assertIn('id="menuBackdrop"', html)
        self.assertIn("function toggleMenu()", html)
        self.assertIn("function closeMenu()", html)
        self.assertIn("transform:translateX(-105%)", html)
        self.assertIn(".side.open{transform:translateX(0)}", html)
        self.assertNotIn(".side{display:none}", html)
        self.assertNotIn("overflow-x:auto", html)


if __name__ == "__main__":
    unittest.main()
