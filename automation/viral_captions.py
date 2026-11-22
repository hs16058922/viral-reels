"""
Viral Caption & Hashtag Generator for Instagram Reels.

Generates high-retention, high-CTR captions designed specifically for
the Instagram Reels algorithm:
- First 125 chars: Click-worthy hook that prevents scrolling before "...more"
- Core value: 3 bullet points with emojis
- Engagement loop: Question + Call-to-Action to save & share
- 3-Tier Hashtag strategy (Niche + Authority + Discovery)
"""

from typing import Dict, List, Optional


class ViralCaptionGenerator:
    """Generates structured viral captions and tiered hashtags for Instagram Reels."""

    # 3-Tier Hashtag Taxonomy for Science & Engineering Reels
    AUTHORITY_TAGS = [
        "#HowItWorks",
        "#EngineeringExplained",
        "#ScienceFacts",
        "#PhysicsFacts",
        "#MechanicalEngineering",
        "#ScienceCommunication",
        "#DidYouKnow",
    ]

    DISCOVERY_TAGS = [
        "#ReelsViral",
        "#ExplorePage",
        "#MindBlowing",
        "#ViralReels",
        "#LearnOnReels",
        "#ReelsInstagram",
        "#TrendingReels",
    ]

    @classmethod
    def generate(
        cls,
        topic_title: str,
        hook: str,
        bullet_points: List[str],
        niche_tags: Optional[List[str]] = None,
        call_to_action: str = "Save this reel and share with someone who loves how things work! 🚀",
        question: str = "Did you already know this secret, or did this surprise you? Drop it in the comments! 👇",
    ) -> str:
        """Construct the complete viral caption string."""
        niche = niche_tags or ["#ThermalBottle", "#VacuumInsulation", "#Thermodynamics", "#EverydayScience"]
        
        # Combine max 15-20 highly targeted tags (Instagram algorithm sweet spot)
        combined_tags = niche + cls.AUTHORITY_TAGS[:5] + cls.DISCOVERY_TAGS[:5]
        hashtags_str = " ".join(combined_tags)

        bullets_str = "\n".join(f"🔹 {bp}" for bp in bullet_points)

        caption = f"""{hook} 🤯

Ever wondered what's REALLY happening inside? Here is the exact physics breakdown:

{bullets_str}

{question}

{call_to_action}

Follow @daily_howitworks for your daily dose of visual engineering! 🔔

.
.
.
{hashtags_str}
"""
        return caption.strip()


# Pre-defined viral caption templates for the Thermal Bottle reel
THERMAL_BOTTLE_CAPTION = ViralCaptionGenerator.generate(
    topic_title="How Does a Thermal Water Bottle Work?",
    hook="Your thermal bottle doesn't keep drinks hot by heating them. It does it by using OUTER SPACE.",
    bullet_points=[
        "DOUBLE-WALL DESIGN: Two stainless steel flasks welded together with zero contact points except the rim.",
        "THE VACUUM SHIELD: All air is sucked out between the walls. Without air molecules, heat CONDUCTION and CONVECTION are physically impossible.",
        "INFRARED MIRROR: The inner chamber is electro-polished like a mirror so thermal radiation bounces straight back into your liquid.",
        "AIRTIGHT STOPPER: The insulated lid prevents the only remaining heat loss channel—vapor escape.",
    ],
    niche_tags=[
        "#ThermalFlask",
        "#HydroFlask",
        "#Thermodynamics",
        "#VacuumInsulation",
        "#StainlessSteel",
        "#KitchenScience",
    ],
    question="Be honest: did you think there was a battery or heating element inside? Tell us below! 👇",
    call_to_action="📌 Save this for school or science trivia, and share with a friend who always carries a flask! ☕❄️",
)
