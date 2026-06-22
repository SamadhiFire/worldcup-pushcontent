import unittest

from processors.music_prompt_generator import MusicPromptGenerator


class MusicPromptGeneratorDurationTests(unittest.TestCase):
    def setUp(self):
        self.generator = MusicPromptGenerator(mock=True)

    def test_style_reference_drops_legacy_length_seconds(self):
        style_reference = self.generator._style_reference(
            {
                "production": {
                    "length_seconds": [60, 90],
                    "energy_curve": "start hot, lift at the chorus by 15 seconds",
                    "mix_style": "clean, loud",
                }
            }
        )

        self.assertNotIn("length_seconds", style_reference)
        self.assertNotIn("60, 90", style_reference)
        self.assertIn("no fixed total duration", style_reference)
        self.assertIn("chorus by 15 seconds", style_reference)

    def test_validate_rejects_total_duration_range(self):
        issues = self.generator._validate(
            {
                "music_prompt": (
                    "Create a 60-90 second epic emotional orchestral pop anthem "
                    "for Spain vs Saudi Arabia."
                ),
                "negative_prompt": "Avoid profanity.",
            }
        )

        self.assertIn("music_prompt specifies a fixed total duration", issues)

    def test_validate_allows_section_timing(self):
        issues = self.generator._validate(
            {
                "music_prompt": (
                    "Create an epic emotional orchestral pop anthem for Spain vs "
                    "Saudi Arabia. Hit the chorus by 15 seconds with crowd response."
                ),
                "negative_prompt": "Avoid profanity.",
            }
        )

        self.assertEqual([], issues)


if __name__ == "__main__":
    unittest.main()
