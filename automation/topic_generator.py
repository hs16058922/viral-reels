"""
Autonomous Intelligent Topic Generator for CurioMotion Reels.

Ensures the topic queue is constantly replenished with fresh, viral,
highly descriptive engineering & everyday science mysteries:
1. Strict Deduplication: Cross-checks existing topics and published history
2. Dual-Engine Generation:
   - Primary: LLM Generation (Gemini API / OpenAI) when API key is provided
   - Built-in Fallback: Curated catalog of 25+ high-retention engineering mysteries
3. High-CTR Formatting:
   - Counterintuitive hook
   - 50-70s descriptive breakdown with physics/mechanics
   - Crisp punchline & @CurioMotion call-to-action
   - Dual-tone cover headlines & stickers
   - 3-tier hashtag stack
"""

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("viral_reels.topic_generator")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TOPICS_FILE = PROJECT_ROOT / "automation" / "topics.json"
HISTORY_FILE = PROJECT_ROOT / "automation" / "published_history.json"

# ── Rich Built-in Curated Science & Engineering Mysteries ───────────────
CURATED_VIRAL_LIBRARY: List[Dict[str, Any]] = [
    {
        "id": "airplane_pressurization",
        "title": "How Airplane Cabins Breathe at 35,000 Feet",
        "hook": "At cruising altitude, the air outside your plane is -60 degrees and has almost zero oxygen. So where does the air you breathe come from?",
        "script": """At thirty-five thousand feet, the air outside your airplane is negative sixty degrees and thin enough to make you pass out in seconds. So where does your cabin air actually come from?
It comes straight out of the roaring jet engines.
High-pressure compressor stages squeeze freezing outside air, compressing it until it reaches over four hundred degrees Fahrenheit.
This scorching bleed air is completely sterilized. Air conditioning packs then cool it through heat exchangers down to comfortable room temperature.
An outflow valve at the back of the fuselage constantly cracks open and closed by millimeters, balancing cabin pressure so you breathe like you're standing on an eight-thousand-foot mountain.
You aren't trapped in a sealed can. You are breathing engine-pressurized air that refreshes completely every three minutes.
Tap follow on @CurioMotion for your daily dose of hidden engineering. What aircraft mystery should we tackle next?""",
        "bullets": [
            "Engine compressor stages compress freezing -60°F thin atmospheric air",
            "Compression generates 400°F heat that sterilizes ambient air",
            "Air cycle machines cool bleed air to room temperature",
            "Fuselage outflow valve meters cabin pressure to an equivalent 8,000ft altitude",
            "Full cabin air volume refreshes every 2 to 3 minutes"
        ],
        "niche_tags": ["#AviationEngineering", "#JetEngine", "#Aerodynamics", "#AviationFacts", "#HowPlanesWork"],
        "cover_hook_1": "AIRPLANE CABIN SECRET",
        "cover_hook_2": "HOW YOU BREATHE AT 35,000FT?!",
        "cover_tag": "AVIATION PHYSICS",
        "cover_sticker": "ENGINE BLEED AIR",
    },
    {
        "id": "car_airbag_explosion",
        "title": "Why Car Airbags Don't Use Compressed Air",
        "hook": "Your car's airbag doesn't inflate with compressed gas. It inflates using a literal rocket explosion.",
        "script": """Your car's airbag doesn't inflate using compressed air. It inflates with a controlled rocket chemical explosion.
Compressed air tanks are far too slow to save your life. In a forty-mile-per-hour crash, your skull will strike the steering wheel in under fifty milliseconds.
When crash sensors detect sudden deceleration, an electrical squib ignites a solid chemical propellant called sodium azide or guanidine nitrate.
In less than thirty milliseconds, the solid pellets burn violently, producing a massive cloud of harmless nitrogen gas.
This expands the nylon bag at over two hundred miles per hour—faster than the blink of a human eye—catching your head right before the impact.
Vents behind the bag immediately release the gas so your chest doesn't bounce back.
A literal rocket engine, built into your steering wheel to save your life in a fraction of a second.
Hit follow on @CurioMotion for daily 3D mechanical breakdowns. What automotive secret should we unpack next?""",
        "bullets": [
            "Compressed air is too slow; crash impact requires sub-30ms inflation",
            "MEMS accelerometers trigger an electrical igniter upon deceleration",
            "Solid propellant pellets combust rapidly into non-toxic nitrogen gas",
            "Nylon airbag deploys at over 200 mph to cushion occupant deceleration",
            "Exhaust vents immediately deflate bag to prevent rebound injury"
        ],
        "niche_tags": ["#AutomotiveEngineering", "#CarSafety", "#ChemicalReactions", "#PhysicsInRealLife", "#EverydayScience"],
        "cover_hook_1": "CAR AIRBAG SECRET",
        "cover_hook_2": "IT'S A ROCKET EXPLOSION?!",
        "cover_tag": "AUTOMOTIVE PHYSICS",
        "cover_sticker": "30-MILLISECOND BLAST",
    },
    {
        "id": "microwave_magnetron",
        "title": "Why Microwaves Heat Soup But Never the Bowl",
        "hook": "A microwave oven doesn't heat food from the outside in. It heats it from the molecular inside out.",
        "script": """A microwave oven doesn't heat food from the outside in. It targets water molecules directly using electromagnetic resonance.
Inside the wall sits a vacuum tube called a magnetron, firing waves at 2.45 gigahertz—two point four five billion cycles per second.
Water molecules are electric dipoles: positively charged on the hydrogen side, negatively charged on the oxygen side.
As the microwave's electric field flips back and forth billions of times a second, water molecules desperately try to align with the field, twisting and rotating at astronomical speed.
This violent molecular friction turns kinetic movement directly into boiling heat.
Glass and ceramic bowls have no free dipoles, so the radiation passes straight through without warming them.
The oven doesn't cook your food. It forces the water inside your food to boil itself.
Hit follow on @CurioMotion for daily physics explained simply. What household device should we cut open next?""",
        "bullets": [
            "Magnetron vacuum tube produces 2.45 GHz electromagnetic radiation",
            "Water molecules act as microscopic electrical dipoles",
            "Electric field flips polarity 2.45 billion times per second",
            "Molecular friction converts kinetic oscillation into thermal heat",
            "Dry ceramics and glass lack dipoles, allowing waves to pass through cold"
        ],
        "niche_tags": ["#MicrowaveOven", "#Electromagnetism", "#MolecularPhysics", "#KitchenScience", "#PhysicsExplained"],
        "cover_hook_1": "MICROWAVE SECRET",
        "cover_hook_2": "WHY THE BOWL STAYS COLD?!",
        "cover_tag": "ELECTROMAGNETISM",
        "cover_sticker": "2.45 BILLION CYCLES/SEC",
    },
    {
        "id": "abs_braking_system",
        "title": "Why Stomping Your Brakes Used to Cause Crashes",
        "hook": "Why does stomping on your brakes at full force make a car skidding harder, until ABS intervenes?",
        "script": """When you slam your brakes in an emergency, your tires don't stop you faster by locking up. They completely lose control.
Physics dictates that static friction—where tire rubber grips the pavement—is up to thirty percent stronger than kinetic friction, which occurs when a locked tire skids like a hockey puck.
Once your wheels lock, you lose one hundred percent of your steering.
This is where ABS takes over. Magnetic wheel speed sensors detect a tire locking up in milliseconds.
The ABS hydraulic modulator pulses the brake fluid pressure up to twenty times per second—rapidly releasing and reapplying the brake pad.
This keeps the tire right on the threshold of maximum static friction, letting you steer around obstacles while stopping in the shortest physical distance possible.
The rapid shutter in your pedal isn't a malfunction; it's physics saving your life.
Follow @CurioMotion for daily engineering breakdowns. What should we explore next?""",
        "bullets": [
            "Static friction between rubber and road is ~30% stronger than kinetic sliding friction",
            "Locked wheels lose directional steering control completely",
            "Hall-effect speed sensors detect impending wheel lockup in real-time",
            "Hydraulic actuator pulses brake line pressure up to 20 times per second",
            "Maintains maximum braking grip while allowing full evasive steering"
        ],
        "niche_tags": ["#ABSBrakes", "#AutomotiveTech", "#FrictionPhysics", "#CarSafety", "#EngineeringExplained"],
        "cover_hook_1": "ABS BRAKES SECRET",
        "cover_hook_2": "WHY LOCKED TIRES SKID?!",
        "cover_tag": "MECHANICAL PHYSICS",
        "cover_sticker": "20 PULSES PER SECOND",
    },
    {
        "id": "quartz_clock_crystal",
        "title": "The Vibrating Crystal Inside Every Wristwatch",
        "hook": "Your watch doesn't tick using gears or microchips to keep time. It uses a microscopic tuning fork carved from quartz rock.",
        "script": """Your watch doesn't measure time using tiny gears or a microchip clock. It uses a microscopic tuning fork carved out of pure quartz rock.
Quartz exhibits the piezoelectric effect: apply an electric voltage to it, and it physically bends. Release the voltage, and it produces an electric pulse.
Engineers carve this quartz crystal so precisely that when a watch battery shocks it, it oscillates at exactly thirty-two thousand seven hundred and sixty-eight times every second.
Why this exact number? Because thirty-two thousand seven hundred and sixty-eight is two raised to the power of fifteen.
A simple chain of fifteen micro-electronic flip-flop dividers divides that frequency by two, fifteen times in a row, until it produces exactly one pulse per second.
That single pulse moves the second hand by one tick.
A stone crystal, vibrating thirty-two thousand times a second, measuring human time with near-atomic precision.
Tap follow on @CurioMotion for daily 3D engineering secrets. What should we unpack next?""",
        "bullets": [
            "Piezoelectric quartz crystal converts voltage into mechanical vibration",
            "Precision-cut tuning fork vibrates at precisely 32,768 Hz",
            "32,768 equals 2^15, perfect for binary electronic division",
            "15 flip-flop logic circuits halve the frequency down to exactly 1 Hz",
            "Delivers 1 mechanical or digital tick per second with pinpoint accuracy"
        ],
        "niche_tags": ["#QuartzWatch", "#Piezoelectric", "#Horology", "#PrecisionEngineering", "#ScienceInRealLife"],
        "cover_hook_1": "QUARTZ WATCH SECRET",
        "cover_hook_2": "THE 32,768 Hz CRYSTAL?!",
        "cover_tag": "PRECISION PHYSICS",
        "cover_sticker": "PIEZOELECTRIC EFFECT",
    },
    {
        "id": "maglev_train_levitation",
        "title": "How Maglev Trains Float on Thin Air at 370 MPH",
        "hook": "A bullet train weighing over five hundred tons can float two inches above the tracks with zero wheels. Here's the electromagnetic magic.",
        "script": """A bullet train weighing five hundred tons can float two inches in the air with zero wheels touching the track. How does it defeat gravity?
It doesn't use ordinary magnets. It uses liquid helium-cooled superconducting electromagnets.
When cooled to negative four hundred and fifty degrees Fahrenheit, electrical resistance vanishes completely, allowing massive currents to generate magnetic fields tens of thousands of times stronger than Earth's.
As the train glides forward, these superconducting magnets pass over aluminum coils embedded in the concrete track walls.
This induces a mirror magnetic field in the tracks. By physics, like poles repel and opposite poles attract.
The track coils repel the bottom of the train upward, levitating five hundred tons on a cushion of pure magnetic flux.
With zero rolling friction and zero rail wear, the train hits three hundred and seventy miles per hour in whisper-quiet flight.
Follow @CurioMotion for your daily dose of futuristic engineering. What transportation wonder should we break down next?""",
        "bullets": [
            "Superconducting electromagnets cooled by liquid helium to -450°F",
            "Zero electrical resistance creates massive persistent magnetic fields",
            "Electrodynamic suspension (EDS) induces repulsive magnetic forces in guideway",
            "Levitates 500-ton train chassis 100mm above tracks with zero physical contact",
            "Eliminates rolling friction for speeds exceeding 370 mph"
        ],
        "niche_tags": ["#MaglevTrain", "#Superconductivity", "#Electromagnetism", "#FutureTransport", "#HighSpeedRail"],
        "cover_hook_1": "MAGLEV TRAIN SECRET",
        "cover_hook_2": "HOW 500 TONS FLOATS?!",
        "cover_tag": "SUPERCONDUCTIVITY",
        "cover_sticker": "ZERO WHEELS, 370 MPH",
    },
    {
        "id": "night_vision_optics",
        "title": "How Night Vision Turns Total Darkness Into Bright Green",
        "hook": "Night vision goggles don't shine invisible light into the dark. They multiply single photons of starlight into millions of electrons.",
        "script": """Night vision goggles don't shine light into the dark. They turn single, invisible particles of starlight into millions of bright green pixels.
In deep night, microscopic ambient photons enter the front lens and strike a photocathode disc made of gallium arsenide.
This releases a shower of electrons through the photoelectric effect.
Those electrons fly into a microchannel plate—a glass disc thinner than a coin, honeycombed with millions of microscopic angled tunnels.
As each electron ricochets through a tunnel, it knocks free thousands more secondary electrons.
A single starlight photon becomes an avalanche of over fifty thousand electrons.
This amplified electron beam slams into a phosphor screen, converting electrical energy back into visible green light.
Why green? Because the human eye is biologically tuned to differentiate more shades of green than any other color on Earth.
Hit follow on @CurioMotion for daily technical mysteries. What military technology should we dissect next?""",
        "bullets": [
            "Gallium arsenide photocathode converts photons into photoelectrons",
            "Microchannel plate with millions of microscopic dynode capillaries",
            "Continuous secondary electron emission amplifies signal by over 50,000x",
            "Phosphor screen converts accelerated electrons back into visible photons",
            "Green phosphor chosen because human eye perceives most shades in green spectrum"
        ],
        "niche_tags": ["#NightVision", "#Optics", "#PhotoelectricEffect", "#MilitaryTech", "#PhysicsInAction"],
        "cover_hook_1": "NIGHT VISION SECRET",
        "cover_hook_2": "WHY IS IT ALWAYS GREEN?!",
        "cover_tag": "OPTICAL PHYSICS",
        "cover_sticker": "50,000x ELECTRON POP",
    },
    {
        "id": "fiber_optic_cables",
        "title": "How Light Bends Through Thousands of Miles of Glass",
        "hook": "Every website, video, and message you send travels across oceans as pulses of laser light trapped inside hair-thin glass strands.",
        "script": """Ninety-nine percent of international internet traffic doesn't travel through satellites. It travels through deep-sea glass cables thinner than a human hair.
How does light travel thousands of miles without leaking out when the cable bends around undersea mountains?
The secret is an optical phenomenon called total internal reflection.
Inside each cable is a glass core wrapped in a second layer of glass called cladding.
The cladding is engineered with a slightly lower refractive index than the core.
When laser pulses shoot into the fiber at an angle greater than the critical angle, the light cannot penetrate the cladding.
Instead, it bounces off the boundary with one hundred percent reflection—trapped inside the glass like an infinite tunnel of mirrors.
Lasers pulse hundreds of billions of times a second, carrying petabytes of data across dark ocean trenches at near the speed of light.
Tap follow on @CurioMotion for your daily look inside our modern world. What should we explore next?""",
        "bullets": [
            "Hair-thin core of ultra-pure silica glass surrounded by cladding",
            "Cladding possesses lower refractive index creating boundary barrier",
            "Total internal reflection bounces photons at 100% efficiency without leakage",
            "Infrared laser pulses transmit petabits of global communications per second",
            "Crosses thousands of miles across continental ocean beds"
        ],
        "niche_tags": ["#FiberOptics", "#TotalInternalReflection", "#InternetInfrastructure", "#OpticsPhysics", "#Telecommunications"],
        "cover_hook_1": "FIBER OPTIC SECRET",
        "cover_hook_2": "LIGHT BENDING IN GLASS?!",
        "cover_tag": "OPTICAL PHYSICS",
        "cover_sticker": "100% INTERNAL REFLECTION",
    }
]


class ViralTopicGenerator:
    """Manages queue replenishment and ensures strict non-duplication."""

    @staticmethod
    def get_existing_ids_and_titles() -> Tuple[Set[str], Set[str]]:
        """Collect all existing IDs and normalized titles to avoid repetition."""
        existing_ids = set()
        existing_titles = set()

        # From topics.json
        if TOPICS_FILE.exists():
            try:
                with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                    topics = json.load(f)
                    for t in topics:
                        if "id" in t:
                            existing_ids.add(t["id"].lower())
                        if "title" in t:
                            norm = re.sub(r'[^a-z0-9]', '', t["title"].lower())
                            existing_titles.add(norm)
            except Exception as e:
                logger.warning("Could not read topics.json for deduplication: %s", e)

        # From published_history.json
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                    for h in history:
                        if "id" in h:
                            existing_ids.add(h["id"].lower())
                        if "title" in h:
                            norm = re.sub(r'[^a-z0-9]', '', h["title"].lower())
                            existing_titles.add(norm)
            except Exception as e:
                logger.warning("Could not read published_history.json: %s", e)

        return existing_ids, existing_titles

    @staticmethod
    def is_duplicate(candidate: Dict[str, Any], existing_ids: Set[str], existing_titles: Set[str]) -> bool:
        """Verify candidate topic has never been added or posted."""
        c_id = candidate.get("id", "").lower()
        if c_id in existing_ids:
            return True
        norm_title = re.sub(r'[^a-z0-9]', '', candidate.get("title", "").lower())
        if norm_title in existing_titles:
            return True
        return False

    @classmethod
    def generate_with_gemini(cls, count: int = 3) -> List[Dict[str, Any]]:
        """Optionally generate brand-new trending engineering mysteries via Gemini API."""
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return []

        logger.info("Generating %d new viral topics via Gemini API...", count)
        from engine.studio import shots
        shot_list = "\n".join(f"   - {n}: {v['desc']}" for n, v in shots.SHOTS.items())
        prompt = f"""You are the head science writer for @CurioMotion, a viral 3D animation Instagram page explaining everyday engineering and physics mysteries.
Generate {count} unique, high-retention topics.
Requirements:
1. Subject must be an everyday device whose INSIDE is a rigid mechanism that a 3D cutaway can show clearly:
   gears, rotors, fans, pistons, valves, pumps, springs, coils, magnets, bearings, lenses, chambers, pipes
   (e.g. a lock cylinder, a car differential, a toilet flush valve, a hard drive, a bicycle hub).
   Avoid subjects that are mostly fabric, chemistry, software, electronics on circuit boards, or people.
   It MUST be explainable with the existing 3D shots below (most of its 5-7 scenes need a matching shot):
{shot_list}
2. Hook (max 2 short sentences, first under 10 words) opens a curiosity gap WITHOUT giving the answer: a
   shocking claim, a danger, an impossible number, or a "why" about something people use daily, e.g. "Your car
   brakes are lying to you." / "This tiny crystal vibrates 32,768 times a second. Why?" Never "Did you know".
3. Script must be 120-150 words, descriptive with real physics/engineering terms, and end with: "Tap follow on @CurioMotion for daily 3D mechanical breakdowns. What should we cut open next?"
4. Provide 4 technical bullet points.
5. Provide 5 niche hashtags.
6. Provide high-CTR cover hooks (dual-tone title): line 1 names the object, line 2 is the unanswered question
   or the shocking number (e.g. "QUARTZ WATCH" / "32,768 VIBRATIONS A SECOND?!"). Never the word "SECRET".

Return strictly JSON array:
[
  {{
    "id": "slug_id",
    "title": "Title",
    "hook": "Hook",
    "script": "Script",
    "bullets": ["Bullet 1", "Bullet 2", "Bullet 3", "Bullet 4"],
    "niche_tags": ["#Tag1", "#Tag2", "#Tag3", "#Tag4", "#Tag5"],
    "cover_hook_1": "LINE 1",
    "cover_hook_2": "LINE 2?!",
    "cover_tag": "CATEGORY",
    "cover_sticker": "HIGHLIGHT STICKER"
  }}
]
"""
        from engine.studio.director import MODELS, _call_gemini
        for model in MODELS:
            try:
                return json.loads(_call_gemini(prompt, model, api_key))
            except Exception as e:  # noqa: BLE001 — fall back to the next model, then the curated library
                logger.warning("Gemini topic generation with %s failed: %s", model, e)
        return []

    @classmethod
    def replenish_queue(cls, min_pending: int = 5) -> int:
        """Check the queue and automatically add fresh, non-duplicate topics."""
        existing_ids, existing_titles = cls.get_existing_ids_and_titles()

        # Load current topics
        topics = []
        if TOPICS_FILE.exists():
            with open(TOPICS_FILE, "r", encoding="utf-8") as f:
                topics = json.load(f)

        # Count pending/ready topics
        pending_count = sum(1 for t in topics if t.get("status") in ("pending", "ready"))
        logger.info("Current queue status: %d pending/ready topics (target threshold: %d)", pending_count, min_pending)

        if pending_count >= min_pending:
            logger.info("Queue is healthy. No replenishment needed.")
            return 0

        needed = min_pending - pending_count
        logger.info("Replenishing queue with %d new topics...", needed)

        added = 0
        new_candidates = []

        # 1. Try Gemini API if key available
        if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
            ai_topics = cls.generate_with_gemini(count=needed)
            for t in ai_topics:
                if not cls.is_duplicate(t, existing_ids, existing_titles):
                    t["status"] = "pending"
                    t["video_path"] = None
                    new_candidates.append(t)
                    existing_ids.add(t["id"].lower())
                    existing_titles.add(re.sub(r'[^a-z0-9]', '', t["title"].lower()))
                    added += 1
                    if added >= needed:
                        break

        # 2. Fill remaining from curated viral library
        if added < needed:
            for item in CURATED_VIRAL_LIBRARY:
                if not cls.is_duplicate(item, existing_ids, existing_titles):
                    entry = dict(item)
                    entry["status"] = "pending"
                    entry["video_path"] = None
                    new_candidates.append(entry)
                    existing_ids.add(entry["id"].lower())
                    existing_titles.add(re.sub(r'[^a-z0-9]', '', entry["title"].lower()))
                    added += 1
                    if added >= needed:
                        break

        if new_candidates:
            topics.extend(new_candidates)
            with open(TOPICS_FILE, "w", encoding="utf-8") as f:
                json.dump(topics, f, indent=2)
            logger.info("🎉 Successfully added %d new unique topics to topics.json!", len(new_candidates))

        return len(new_candidates)


if __name__ == "__main__":
    count = ViralTopicGenerator.replenish_queue(min_pending=5)
    print(f"Replenished queue with {count} new topics.")
