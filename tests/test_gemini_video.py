"""
Tests for GeminiVideoStudio (Veo scene planning, timing synchronization, and compositing).
"""

import unittest
from engine.gemini_video_engine import GeminiVideoStudio, GeminiScene
from engine.whisper_captions import WordTiming


class TestGeminiVideoStudio(unittest.TestCase):
    """Test suite for Gemini Video Generation Studio."""

    def setUp(self):
        self.sample_topic = {
            "id": "mechanical_watch",
            "title": "How a Mechanical Watch Works",
            "script": "Inside a luxury mechanical watch sits a coiled mainspring. As it unwinds, it drives a train of gears. The escape wheel regulates the pulses.",
            "bullets": ["Mainspring barrel", "Involute gear train", "Oscillating escapement"],
        }
        self.sample_words = [
            WordTiming(word="Inside", start=0.0, end=0.3),
            WordTiming(word="a", start=0.3, end=0.4),
            WordTiming(word="watch", start=0.4, end=0.9),
            WordTiming(word="sits", start=0.9, end=1.2),
            WordTiming(word="mainspring", start=1.2, end=1.8),
        ]

    def test_plan_scenes(self):
        """Verify script is cleanly divided into timed visual scenes with 9:16 Veo prompts."""
        scenes = GeminiVideoStudio.plan_scenes(
            topic=self.sample_topic,
            total_duration=12.0,
            words=self.sample_words,
            num_scenes=3,
        )
        self.assertEqual(len(scenes), 3)
        self.assertAlmostEqual(scenes[0].target_duration, 4.0)
        self.assertIn("9:16", scenes[0].video_prompt)
        self.assertIn("cutaway", scenes[0].video_prompt.lower())

    def test_active_caption_window(self):
        """Verify active word window indexing matches audio timestamps."""
        words, active_idx = GeminiVideoStudio._get_active_caption(0.5, self.sample_words, window_size=4)
        self.assertEqual(len(words), 4)
        self.assertEqual(words[active_idx], "watch")


if __name__ == "__main__":
    unittest.main()
