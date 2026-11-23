"""
Narration-Animation Synchronization Engine.

Maps Whisper word-level timestamps to 3D SceneSpec animation keyframes.
When the narrator speaks a key technical trigger (e.g., 'escapement wheel',
'turbines compress', 'systolic beat'), the corresponding 3D object animation,
exploded view translation, or callout highlight begins at that exact frame.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from engine.whisper_captions import WordTiming

logger = logging.getLogger("viral_reels.sync")


@dataclass
class SyncCue:
    """An animation trigger synchronized to spoken narration."""
    phrase: str
    target_object_id: str
    action_type: str  # "explode", "rotate", "highlight", "pulse", "cutaway"
    start_time_seconds: float
    end_time_seconds: float
    start_frame: int
    end_frame: int


class NarrationSyncEngine:
    """Matches spoken transcript words to visual animation cues."""

    # Common technical trigger dictionaries
    TOPIC_KEYWORD_MAP = {
        "watch": {
            "mainspring": ("Mainspring_Barrel", "rotate"),
            "barrel": ("Mainspring_Barrel", "rotate"),
            "gear": ("Center_Wheel", "rotate"),
            "teeth": ("Third_Wheel", "rotate"),
            "escapement": ("Escape_Wheel", "explode"),
            "escape": ("Escape_Wheel", "rotate"),
            "pallet": ("Pallet_Fork", "pulse"),
            "ruby": ("Ruby_Jewel_1", "highlight"),
            "balance": ("Balance_Wheel", "explode"),
            "hairspring": ("Hairspring", "pulse"),
            "vibrate": ("Balance_Wheel", "rotate"),
            "tick": ("Pallet_Fork", "pulse"),
        },
        "jet": {
            "intake": ("Intake_Fan", "rotate"),
            "fan": ("Intake_Fan", "rotate"),
            "compress": ("HPC_Stage_1", "rotate"),
            "compressor": ("HPC_Stage_1", "rotate"),
            "blade": ("LPC_Stage_1", "explode"),
            "combustion": ("Combustion_Chamber", "pulse"),
            "fire": ("Combustion_Chamber", "highlight"),
            "fuel": ("Combustion_Chamber", "pulse"),
            "turbine": ("Turbine_Stage_1", "rotate"),
            "exhaust": ("Exhaust_Nozzle", "highlight"),
            "thrust": ("Exhaust_Nozzle", "explode"),
        },
        "heart": {
            "beat": ("Heart_Ventricles", "pulse"),
            "pump": ("Heart_Ventricles", "pulse"),
            "ventricle": ("Heart_Ventricles", "pulse"),
            "atrium": ("Right_Atrium", "pulse"),
            "atria": ("Left_Atrium", "pulse"),
            "aorta": ("Aortic_Arch", "highlight"),
            "valve": ("Heart_Ventricles", "pulse"),
            "blood": ("Aortic_Arch", "pulse"),
            "oxygen": ("Aortic_Arch", "highlight"),
            "pulmonary": ("Pulmonary_Trunk", "highlight"),
        },
    }

    @classmethod
    def align_narration_to_cues(
        cls,
        words: List[WordTiming],
        topic_id: str,
        fps: int = 30,
    ) -> List[SyncCue]:
        """Scans transcript words and generates exact frame-aligned SyncCues."""
        cues: List[SyncCue] = []
        if not words:
            return cues

        # Find matching topic keyword category
        keyword_dict = {}
        for k in cls.TOPIC_KEYWORD_MAP:
            if k in topic_id.lower():
                keyword_dict = cls.TOPIC_KEYWORD_MAP[k]
                break

        if not keyword_dict:
            keyword_dict = cls.TOPIC_KEYWORD_MAP.get("watch", {})

        for w in words:
            clean_word = re.sub(r'[^a-zA-Z0-9]', '', w.word.lower())
            if clean_word in keyword_dict:
                obj_id, action = keyword_dict[clean_word]
                start_f = int(w.start * fps)
                end_f = int((w.end + 1.2) * fps)  # Hold action through the word + tail
                cue = SyncCue(
                    phrase=w.word,
                    target_object_id=obj_id,
                    action_type=action,
                    start_time_seconds=w.start,
                    end_time_seconds=w.end + 1.2,
                    start_frame=start_f,
                    end_frame=end_f,
                )
                cues.append(cue)

        logger.info("Aligned %d narration sync cues for topic '%s'", len(cues), topic_id)
        return cues

    @classmethod
    def generate_subtitles_srt(cls, words: List[WordTiming], max_words_per_group: int = 3) -> str:
        """Export Whisper transcription to standard SRT format."""
        if not words:
            return ""

        def format_time(sec: float) -> str:
            hrs = int(sec // 3600)
            mins = int((sec % 3600) // 60)
            secs = int(sec % 60)
            mils = int((sec - int(sec)) * 1000)
            return f"{hrs:02d}:{mins:02d}:{secs:02d},{mils:03d}"

        srt_lines = []
        index = 1
        i = 0
        while i < len(words):
            chunk = words[i:i + max_words_per_group]
            start_t = chunk[0].start
            end_t = chunk[-1].end
            text = " ".join(w.word for w in chunk)

            srt_lines.append(str(index))
            srt_lines.append(f"{format_time(start_t)} --> {format_time(end_t)}")
            srt_lines.append(text)
            srt_lines.append("")

            index += 1
            i += len(chunk)

        return "\n".join(srt_lines)
