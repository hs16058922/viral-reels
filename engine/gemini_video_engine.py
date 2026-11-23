"""
Gemini / Google Veo Video Generation Studio.

Autonomous pipeline to:
1. Divide narration script into coherent visual scenes.
2. Generate photorealistic vertical 9:16 video clips per scene via Gemini Veo API (veo-2.0-generate-001).
3. Synchronize scene timing with Whisper word-level audio alignment.
4. Composite synchronized word-level captions, SFX audio mastering, and sleek HUD graphics.
5. Export 1080x1920 30fps Meta-compliant reels for Instagram, Shorts, and TikTok.
"""

from __future__ import annotations

import json
import logging
import math
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from config.settings import settings
from engine.caption_styles import CaptionStyleRotator, CaptionTheme
from engine.cover_generator import ReelCoverGenerator
from engine.edge_voice import VoiceEngine
from engine.hud_graphics import HUDGraphicsEngine
from engine.sfx_manager import SFXManager
from engine.video_formats import FormatCompositor, ReelVideoFormat
from engine.whisper_captions import CaptionGenerator, WordTiming

logger = logging.getLogger("viral_reels.gemini_video")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = PROJECT_ROOT / "tmp"
EXPORT_DIR = PROJECT_ROOT / "export"


@dataclass
class GeminiScene:
    """Represents a planned visual scene for video generation."""
    scene_index: int
    narration_chunk: str
    video_prompt: str
    target_duration: float
    start_time: float = 0.0
    end_time: float = 0.0
    clip_path: Optional[Path] = None


class GeminiVideoStudio:
    """Orchestrates scene-wise video generation with Gemini Veo and multi-layer compositing."""

    @classmethod
    def get_api_key(cls) -> Optional[str]:
        """Fetch Gemini API key from environment or settings."""
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or settings.GEMINI_API_KEY

    @classmethod
    def is_available(cls) -> bool:
        """Check if google-genai is installed and API key is present."""
        try:
            from google import genai
            return bool(cls.get_api_key())
        except ImportError:
            return False

    @classmethod
    def plan_scenes(
        cls,
        topic: Dict[str, Any],
        total_duration: float,
        words: List[WordTiming],
        num_scenes: int = 4,
    ) -> List[GeminiScene]:
        """
        Break the topic script and Whisper words into timed scenes with cinematic Veo prompts.
        """
        script = topic.get("script", "")
        title = topic.get("title", "")
        topic_id = topic.get("id", "scene")
        bullets = topic.get("bullets", [])

        # Split sentences/clauses
        sentences = [s.strip() for s in script.replace("\n", " ").split(".") if s.strip()]
        if not sentences:
            sentences = [title]

        actual_num_scenes = max(2, min(num_scenes, len(sentences)))
        scene_duration = total_duration / actual_num_scenes

        # Distribute sentences across scenes
        chunk_size = math.ceil(len(sentences) / actual_num_scenes)
        scenes: List[GeminiScene] = []

        # Technical/visual prompt styling cues
        styles = [
            "Vertical 9:16 macro shot, photorealistic 3D cutaway showing internal mechanism, intricate gears and precision engineered components moving smoothly, volumetric studio lighting, 8k resolution, raytraced reflections",
            "Vertical 9:16 exploded view, technical mechanical assembly disassembling in mid-air, floating components with glowing technical conduits, shallow depth of field, cinematic slow motion",
            "Vertical 9:16 high-speed macro push-in camera movement, fluid dynamics and kinetic energy flowing through high-tech chamber, glowing accents, hyper-detailed mechanical textures",
            "Vertical 9:16 cinematic pull-out reveal, fully assembled engineered device operating with flawless mechanical rhythm, elegant matte dark metal and brushed titanium finishes, moody ambient lighting",
        ]

        for i in range(actual_num_scenes):
            start_idx = i * chunk_size
            end_idx = min((i + 1) * chunk_size, len(sentences))
            chunk_sentences = sentences[start_idx:end_idx]
            narration_chunk = ". ".join(chunk_sentences) + "."

            # Enhance prompt with topic specifics
            bullet_hint = bullets[i % len(bullets)] if bullets else title
            base_style = styles[i % len(styles)]
            prompt = (
                f"{base_style}. Subject: {title}. Visual focal point: {bullet_hint}. "
                f"Action: {narration_chunk[:140]}. Highly detailed, photorealistic, cinematic lighting, no text, no captions."
            )

            s_start = i * scene_duration
            s_end = (i + 1) * scene_duration if i < actual_num_scenes - 1 else total_duration

            scenes.append(
                GeminiScene(
                    scene_index=i,
                    narration_chunk=narration_chunk,
                    video_prompt=prompt,
                    target_duration=s_end - s_start,
                    start_time=s_start,
                    end_time=s_end,
                )
            )

        # Try to refine prompts using Gemini text model if API key is active
        api_key = cls.get_api_key()
        if api_key:
            try:
                from google import genai
                client = genai.Client(api_key=api_key)
                prompt_req = (
                    f"Create {actual_num_scenes} visual prompts for Google Veo (vertical 9:16 video generation) "
                    f"to visually explain '{title}'.\n"
                    f"Script: {script}\n"
                    f"Return a JSON array of strings, where each string is a 40-word photorealistic 3D cutaway prompt."
                )
                resp = client.models.generate_content(
                    model="gemini-3-flash-preview",
                    contents=prompt_req,
                    config={"response_mime_type": "application/json"},
                )
                if resp.text:
                    refined = json.loads(resp.text)
                    if isinstance(refined, list) and len(refined) == len(scenes):
                        for idx, p_text in enumerate(refined):
                            scenes[idx].video_prompt = f"Vertical 9:16 aspect ratio. {p_text} Highly cinematic, photorealistic, no watermarks, no subtitles."
                        logger.info("Successfully refined %d scene prompts with Gemini LLM.", len(scenes))
            except Exception as e:
                logger.warning("Gemini prompt refinement skipped: %s. Using high-fidelity template prompts.", e)

        return scenes

    @classmethod
    def generate_scene_clip(
        cls,
        scene: GeminiScene,
        topic_id: str,
        output_dir: Path,
        model_name: str = "veo-2.0-generate-001",
    ) -> Path:
        """
        Calls Gemini Veo generate_videos API to produce a 9:16 scene video clip.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        clip_path = output_dir / f"{topic_id}_scene_{scene.scene_index + 1}.mp4"

        # Check if already generated
        if clip_path.exists() and clip_path.stat().st_size > 100 * 1024:
            logger.info("Using cached Gemini video clip: %s", clip_path.name)
            scene.clip_path = clip_path
            return clip_path

        api_key = cls.get_api_key()
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set GEMINI_API_KEY in your .env file "
                "or environment variables to generate video clips via Google Veo."
            )

        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        logger.info(
            "🎬 [Scene %d/%s] Generating 9:16 video clip via Veo (%s)... Prompt: %s",
            scene.scene_index + 1,
            model_name,
            scene.video_prompt[:80],
        )

        try:
            # Duration in seconds (Veo typically supports 5-8 seconds per generation)
            desired_duration = max(5, min(8, int(round(scene.target_duration))))

            operation = client.models.generate_videos(
                model=model_name,
                prompt=scene.video_prompt,
                config=types.GenerateVideosConfig(
                    aspect_ratio="9:16",
                    duration_seconds=desired_duration,
                    person_generation="dont_allow",
                    enhance_prompt=True,
                ),
            )

            # Poll operation until completion
            logger.info("Waiting for Veo video generation to complete...")
            poll_interval = 10
            max_wait_seconds = 300
            elapsed = 0

            while not operation.done:
                time.sleep(poll_interval)
                elapsed += poll_interval
                operation = client.operations.get(operation)
                logger.info("... Veo generation in progress (%ds elapsed)", elapsed)
                if elapsed >= max_wait_seconds:
                    raise TimeoutError(f"Veo video generation timed out after {max_wait_seconds}s.")

            response = operation.response
            if not response or not response.generated_videos:
                raise RuntimeError(f"Veo operation completed but returned no video: {operation}")

            generated_video = response.generated_videos[0]
            client.files.download(file=generated_video.video)
            generated_video.video.save(str(clip_path))

            logger.info("✅ Scene %d clip saved: %s (%.1f MB)",
                        scene.scene_index + 1, clip_path.name, clip_path.stat().st_size / (1024 * 1024))
            scene.clip_path = clip_path
            return clip_path

        except Exception as e:
            logger.error("Veo video generation error for scene %d: %s", scene.scene_index + 1, e)
            raise

    @classmethod
    def assemble_scene_track(
        cls,
        scenes: List[GeminiScene],
        total_duration: float,
        output_track_mp4: Path,
    ) -> Path:
        """
        Stitches scene clips together with timing adjustments and smooth crossfades to match total_duration.
        """
        output_track_mp4.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"

        # Prepare normalized clips adjusted to each scene's target duration
        norm_clips = []
        for scene in scenes:
            if not scene.clip_path or not scene.clip_path.exists():
                raise FileNotFoundError(f"Missing clip for scene {scene.scene_index}")

            norm_clip = TMP_DIR / f"norm_scene_{scene.scene_index}.mp4"
            # Get input clip duration
            probe_cmd = [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(scene.clip_path),
            ]
            try:
                res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
                in_dur = float(res.stdout.strip())
            except Exception:
                in_dur = 5.0

            speed_factor = in_dur / scene.target_duration
            # Scale video to 1080x1920 30fps and adjust duration
            cmd_norm = [
                ffmpeg_bin, "-y",
                "-i", str(scene.clip_path),
                "-filter_complex",
                f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                f"setpts={1.0 / speed_factor:.4f}*PTS,fps=30[v]",
                "-map", "[v]",
                "-t", f"{scene.target_duration:.3f}",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-an",
                str(norm_clip),
            ]
            subprocess.run(cmd_norm, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            norm_clips.append(norm_clip)

        # Concatenate normalized clips
        concat_list = TMP_DIR / "gemini_concat_list.txt"
        with open(concat_list, "w") as f:
            for p in norm_clips:
                f.write(f"file '{p.resolve()}'\n")

        concat_cmd = [
            ffmpeg_bin, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c:v", "copy",
            str(output_track_mp4),
        ]
        subprocess.run(concat_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("Assembled concatenated visual track: %s", output_track_mp4.name)
        return output_track_mp4

    @classmethod
    def build_gemini_reel(
        cls,
        topic: Dict[str, Any],
        output_mp4: Optional[Path] = None,
        mock_if_no_key: bool = False,
    ) -> Path:
        """
        Complete end-to-end autonomous reel generation using Gemini Veo video base:
        1. Voiceover (EdgeTTS)
        2. Word timestamps (Whisper)
        3. Scene division & Gemini Veo 9:16 clip generation
        4. Audio mastering with SFX
        5. Frame-by-frame synchronized captions, HUD, and Cover hook overlay
        6. Final 1080x1920 MP4 export
        """
        topic_id = topic["id"]
        output_mp4 = output_mp4 or (EXPORT_DIR / f"{topic_id}_gemini_reel.mp4")
        output_mp4.parent.mkdir(parents=True, exist_ok=True)
        TMP_DIR.mkdir(parents=True, exist_ok=True)

        logger.info("🚀 Initiating Gemini Veo Studio for topic: '%s' (ID: %s)", topic["title"], topic_id)

        # 1. Voiceover
        audio_path = TMP_DIR / f"{topic_id}_voice.mp3"
        ve = VoiceEngine()
        ve.synthesize(text=topic["script"], output_path=audio_path)

        # 2. Whisper Word-level Transcription
        logger.info("Transcribing speech with Whisper for microsecond-accurate word alignment...")
        caption_gen = CaptionGenerator(model_size="base")
        txn = caption_gen.transcribe(audio_path)
        words = txn.words
        total_duration = 10.0
        if words:
            total_duration = words[-1].end + 0.8
        try:
            ffprobe_bin = shutil.which("ffprobe") or "ffprobe"
            cmd = [ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)]
            out = subprocess.check_output(cmd, text=True).strip()
            total_duration = float(out)
        except Exception:
            pass
        logger.info("Narration audio: %.2fs (%d words aligned)", total_duration, len(words))

        # 3. Plan Scenes & Generate Clips via Gemini Veo
        scenes = cls.plan_scenes(topic, total_duration, words, num_scenes=4)
        clips_dir = TMP_DIR / "gemini_scenes" / topic_id
        clips_dir.mkdir(parents=True, exist_ok=True)

        model_name = settings.GEMINI_VIDEO_MODEL
        for scene in scenes:
            try:
                cls.generate_scene_clip(scene, topic_id, clips_dir, model_name=model_name)
            except Exception as e:
                logger.warning("Could not generate Veo clip for scene %d: %s", scene.scene_index, e)
                if mock_if_no_key or not cls.get_api_key():
                    logger.info("Creating fallback visual canvas for scene %d...", scene.scene_index)
                    cls._create_fallback_scene_clip(scene, topic_id, clips_dir)
                else:
                    raise

        # 4. Assemble Visual Track
        base_video = TMP_DIR / f"{topic_id}_gemini_base.mp4"
        cls.assemble_scene_track(scenes, total_duration, base_video)

        # 5. Master Multi-Track Soundtrack with SFX
        master_audio_path = TMP_DIR / f"{topic_id}_master_soundtrack.aac"
        scene_cut_times = [s.start_time for s in scenes[1:]]
        callout_times = [s.start_time + 0.3 for s in scenes]

        logger.info("Mastering multi-track audio soundtrack with SFX...")
        SFXManager.build_mixed_soundtrack(
            voice_path=audio_path,
            scene_cut_times=scene_cut_times,
            callout_times=callout_times,
            total_duration=total_duration,
            output_path=master_audio_path,
        )

        # 6. Generate High-CTR Cover Card
        cover_path = TMP_DIR / f"{topic_id}_cover.jpg"
        cover_img = ReelCoverGenerator.generate_cover(
            base_image_path=None,
            hook_line_1=topic.get("cover_hook_1") or topic["title"],
            hook_line_2=topic.get("cover_hook_2") or "SECRET REVEALED",
            category_tag=topic.get("cover_tag") or "HOW IT WORKS",
            curiosity_sticker=topic.get("cover_sticker") or "EXPLAINED",
            accent_color=(0, 229, 255),
            output_path=cover_path,
        )

        # 6b. Pre-render true 3D Blender mechanism sequence
        blender_frames = []
        try:
            from engine.blender_runner import BlenderMechanismRunner
            if BlenderMechanismRunner.is_available():
                logger.info("🎬 Pre-rendering true 3D Blender mechanism for '%s'...", topic_id)
                blender_frames = BlenderMechanismRunner.render_mechanism_sequence(
                    topic_id=topic_id,
                    frames=75,
                    width=720,
                    height=1280,
                )
        except Exception as e:
            logger.warning("Could not pre-render Blender mechanism: %s", e)

        # 7. Final Composite (Base Video + 3D Blender Mechanism + Synchronized Captions + Audio)
        logger.info("Compositing final reel with 3D mechanisms, synchronized captions, and mastered audio...")
        cls._composite_final_reel(
            topic=topic,
            base_video=base_video,
            master_audio=master_audio_path,
            cover_img=cover_img,
            words=words,
            total_duration=total_duration,
            output_mp4=output_mp4,
            blender_frames=blender_frames,
        )

        logger.info("✨ Successfully built Gemini AI Reel: %s (%.1f MB)",
                    output_mp4.name, output_mp4.stat().st_size / (1024 * 1024))
        return output_mp4

    @classmethod
    def _create_fallback_scene_clip(cls, scene: GeminiScene, topic_id: str, clips_dir: Path):
        """Creates a high-contrast animated gradient clip if Gemini API key is missing or quota limited."""
        clip_path = clips_dir / f"{topic_id}_scene_{scene.scene_index + 1}.mp4"
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        color = "0x0a101d" if scene.scene_index % 2 == 0 else "0x0f172a"
        dur = max(1.0, float(scene.target_duration))
        cmd = [
            ffmpeg_bin, "-y",
            "-f", "lavfi",
            "-i", f"color=c={color}:s=1080x1920:r=30:d={dur:.2f}",
            "-c:v", "libx264",
            "-r", "30",
            "-pix_fmt", "yuv420p",
            str(clip_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        scene.clip_path = clip_path

    @classmethod
    def _composite_final_reel(
        cls,
        topic: Dict[str, Any],
        base_video: Path,
        master_audio: Path,
        cover_img: Image.Image,
        words: List[WordTiming],
        total_duration: float,
        output_mp4: Path,
        blender_frames: Optional[List[Image.Image]] = None,
    ):
        """Pipes base video frames through PIL for dynamic captions and writes final audio."""
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        width, height = 1080, 1920
        fps = 30
        total_frames = int(total_duration * fps)

        theme = CaptionStyleRotator.get_theme_for_topic(topic)

        # Open base video reader pipe
        read_cmd = [
            ffmpeg_bin,
            "-i", str(base_video),
            "-f", "image2pipe",
            "-pix_fmt", "rgb24",
            "-vcodec", "rawvideo",
            "-r", str(fps),
            "-",
        ]
        read_proc = subprocess.Popen(read_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        # Open writer pipe
        write_cmd = [
            ffmpeg_bin, "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-s", f"{width}x{height}",
            "-pix_fmt", "rgb24",
            "-r", str(fps),
            "-i", "-",
            "-i", str(master_audio),
            "-c:v", "libx264",
            "-profile:v", "main",
            "-level", "3.1",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-g", "60",
            "-keyint_min", "60",
            "-sc_threshold", "0",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            "-ac", "2",
            "-movflags", "+faststart",
            "-t", f"{total_duration:.3f}",
            str(output_mp4),
        ]
        write_proc = subprocess.Popen(write_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        frame_bytes_size = width * height * 3

        try:
            for frame_idx in range(total_frames):
                t = frame_idx / fps

                # Cover hook for first 12 frames (0.4s)
                if frame_idx < 12:
                    write_proc.stdin.write(cover_img.convert("RGB").tobytes())
                    # Discard from read pipe
                    read_proc.stdout.read(frame_bytes_size)
                    continue

                raw_bytes = read_proc.stdout.read(frame_bytes_size)
                if not raw_bytes or len(raw_bytes) < frame_bytes_size:
                    frame_img = Image.new("RGB", (width, height), (10, 16, 26))
                else:
                    frame_img = Image.frombytes("RGB", (width, height), raw_bytes)

                # Hero 3D Moving Mechanism Overlay (Rotating assembly, gears, turbines)
                if blender_frames:
                    b_idx = int((t * 25.0) % len(blender_frames))
                    b_frame = blender_frames[b_idx]
                    target_w = int(width * 0.98)
                    target_h = int(target_w * (b_frame.height / b_frame.width))
                    scaled_b = b_frame.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    bx = (width - target_w) // 2
                    by = (height - target_h) // 2 + int(math.sin(t * 2.2) * 12.0)
                    frame_img.paste(scaled_b, (bx, by), scaled_b)

                # Overlay Sleek Progress Reticle
                HUDGraphicsEngine.draw_hud_overlay(
                    img=frame_img,
                    t=t,
                    total_duration=total_duration,
                    scene_idx=int((t / max(0.1, total_duration)) * 4),
                    accent_color=(0, 229, 255),
                )

                # Find active caption words
                c_words, active_idx = cls._get_active_caption(t, words)
                if c_words:
                    CaptionStyleRotator.render_caption_to_frame(
                        img=frame_img,
                        words=c_words,
                        active_idx=active_idx,
                        theme=theme,
                        center_y=int(height * 0.74),
                    )

                write_proc.stdin.write(frame_img.convert("RGB").tobytes())

        finally:
            read_proc.stdout.close()
            read_proc.wait()
            write_proc.stdin.close()
            write_proc.wait()

    @classmethod
    def _get_active_caption(
        cls,
        t: float,
        words: List[WordTiming],
        window_size: int = 4,
    ) -> Tuple[List[str], int]:
        """Returns 3-5 word sliding window centered on spoken word at timestamp t."""
        if not words:
            return [], -1

        active_word_idx = -1
        # 1. Exact match within word spoken boundaries
        for idx, w in enumerate(words):
            if w.start <= t <= w.end:
                active_word_idx = idx
                break

        # 2. Inter-word pause tolerance
        if active_word_idx == -1:
            for idx, w in enumerate(words):
                if w.start <= t <= (w.end + 0.15):
                    active_word_idx = idx
                    break

        if active_word_idx == -1:
            for idx in range(len(words) - 1):
                if words[idx].end <= t <= words[idx + 1].start:
                    active_word_idx = idx
                    break

        if active_word_idx == -1:
            if words and t <= words[-1].end + 0.5:
                active_word_idx = len(words) - 1
            else:
                return [], -1

        start_idx = (active_word_idx // window_size) * window_size
        end_idx = min(start_idx + window_size, len(words))
        chunk_words = [words[i].word for i in range(start_idx, end_idx)]
        relative_active = active_word_idx - start_idx
        return chunk_words, relative_active
