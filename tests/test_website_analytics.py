import importlib.util
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

    def test_index_has_left_nav_and_renders_website_analytics_page(self):
        html = (ROOT / "index.html").read_text()
        self.assertIn('data-page="websiteAnalytics"', html)
        self.assertIn("Website Analytics", html)
        self.assertIn('id="websiteAnalytics"', html)
        self.assertIn("data.websiteAnalytics", html)


if __name__ == "__main__":
    unittest.main()
