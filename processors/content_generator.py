"""
内容生成器 - 调用 LLM 生成 Push Title/Description/AIGC Prompt/Hashtags
"""
import json
import urllib.request
from typing import Optional

from config import settings


# ── 场景 → AIGC Prompt 风格映射 ──
SCENARIO_STYLE_MAP = {
    "玩梗群嘲": {
        "genre_primary": "Comedy / Satire",
        "genre_options": ["Bossa Nova", "Country Comedy", "Punk Rock", "Emo Rock"],
        "mood": "sarcastic, playful, mocking",
        "bpm_range": [100, 180],
        "vocal_tone": "mocking, comedic",
        "social_focus": "TikTok meme potential, singable chorus",
    },
    "情怀致敬": {
        "genre_primary": "Epic / Emotional",
        "genre_options": ["Orchestral Pop", "R&B Ballad", "Brazilian Funk-Trap"],
        "mood": "epic, emotional, triumphant",
        "bpm_range": [70, 140],
        "vocal_tone": "soaring, emotional",
        "social_focus": "IG/X tribute content, cinematic feel",
    },
    "社交派对": {
        "genre_primary": "Party / Social",
        "genre_options": ["Irish Pub-Rock", "EDM Festival", "Electronic Rap"],
        "mood": "energetic, competitive, celebratory",
        "bpm_range": [120, 150],
        "vocal_tone": "rowdy, hype",
        "social_focus": "group sing-along, party atmosphere",
    },
    "短视频二创": {
        "genre_primary": "BGM / Edit-friendly",
        "genre_options": ["Phonk", "Glitch-Hop", "Hyperpop", "Cinematic Rock"],
        "mood": "dramatic, mysterious, goofy",
        "bpm_range": [130, 180],
        "vocal_tone": "varies by sub-type",
        "social_focus": "TikTok/Reels BGM, sync-friendly beats",
    },
    "主场狂热": {
        "genre_primary": "Stadium / Aggressive",
        "genre_options": ["Heavy Metal", "Stadium Hip-Hop", "EDM", "Mariachi-Trap"],
        "mood": "furious, euphoric, explosive",
        "bpm_range": [128, 170],
        "vocal_tone": "screaming, chanting, aggressive",
        "social_focus": "stadium chants, bass-heavy drops",
    },
    "遗憾怀念": {
        "genre_primary": "Melancholic / Tribute",
        "genre_options": ["Alt-Rock Ballad", "Synth-Pop", "Blues", "Acoustic R&B"],
        "mood": "melancholic, nostalgic, divine",
        "bpm_range": [60, 100],
        "vocal_tone": "soulful, ethereal",
        "social_focus": "memorial tributes, emotional resonance",
    },
}


class ContentGenerator:
    """LLM 内容生成器"""

    def __init__(self):
        self.base_url = settings.LLM_BASE_URL.rstrip("/")
        self.api_key = settings.LLM_API_KEY
        self.model = settings.LLM_MODEL

    def generate(self, event_context: dict, scenario: str, x_sentiment: str = "") -> dict:
        """
        生成英文基准版的 Push 内容

        返回:
        {
            "push_title": str,
            "push_description": str,
            "aigc_prompt": dict (structured JSON),
            "hashtags": str,
            "applicable_object": str,
        }
        """
        style = SCENARIO_STYLE_MAP.get(scenario, SCENARIO_STYLE_MAP["玩梗群嘲"])
        match_info = event_context.get("match", {})
        event_info = event_context.get("event", {})

        prompt = self._build_generation_prompt(
            match_info=match_info,
            event_info=event_info,
            scenario=scenario,
            style=style,
            x_sentiment=x_sentiment,
        )

        response = self._call_llm(prompt, system_role="content_generator")

        # 解析 LLM 返回的 JSON
        try:
            content = json.loads(response)
        except json.JSONDecodeError:
            # 尝试从 markdown code block 中提取
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
                content = json.loads(json_str)
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
                content = json.loads(json_str)
            else:
                raise ValueError(f"无法解析 LLM 输出: {response[:200]}")

        return content

    def _build_generation_prompt(self, match_info, event_info, scenario, style, x_sentiment) -> str:
        """构建内容生成的 prompt"""
        return f"""You are the Vanso World Cup Push Content Generator.
Generate viral push notification content for an AI music generation app during the 2026 FIFA World Cup.

## Current Event
- Match: {match_info.get('match_display', 'Unknown')}
- Stage: {match_info.get('stage', 'Group Stage')}
- Venue: {match_info.get('venue', 'Unknown')}
- Score: {match_info.get('score', 'Unknown')}
- Event: {event_info.get('description', 'Unknown')}
- Player: {event_info.get('player', 'Unknown')}
- Minute: {event_info.get('minute', 'Unknown')}'

## Target Scenario: {scenario}
Style Guidelines:
- Genre: {style['genre_primary']} (options: {', '.join(style['genre_options'])})
- Mood: {style['mood']}
- BPM Range: {style['bpm_range'][0]}-{style['bpm_range'][1]}
- Vocal Tone: {style['vocal_tone']}
- Social Focus: {style['social_focus']}

{f"## X (Twitter) Sentiment Context\n{x_sentiment}\n" if x_sentiment else ""}

## Output Requirements
Return a JSON object with exactly these fields:

```json
{{
    "push_title": "15-30 chars, starts with emoji, short/punchy/provocative, action-oriented",
    "push_description": "40-80 chars, emotional trigger + call-to-action to generate a song",
    "aigc_prompt": {{
        "title_hint": "suggested song title",
        "genre": {{
            "primary": "main genre",
            "secondary": "sub-genre or fusion",
            "fusion": null
        }},
        "mood": {{
            "primary": "primary mood",
            "secondary": "secondary mood",
            "intensity": "low/medium/high"
        }},
        "tempo": {{
            "bpm_range": [{style['bpm_range'][0]}, {style['bpm_range'][1]}],
            "feel": "rhythmic feel description",
            "rhythm_pattern": "specific rhythm pattern"
        }},
        "instrumentation": {{
            "core": ["core instrument 1", "core instrument 2"],
            "accent": ["accent instrument"],
            "exclude": ["instruments to avoid"]
        }},
        "vocal": {{
            "style": "vocal style",
            "gender": "male/female/any",
            "language": "en",
            "tone": "vocal tone",
            "reference": "artist reference for style"
        }},
        "lyrics": {{
            "theme": "lyrical theme in one sentence",
            "key_imagery": ["imagery 1", "imagery 2", "imagery 3"],
            "tone": "lyrical tone",
            "structure": "song structure",
            "must_include": ["element 1", "element 2"],
            "must_avoid": ["profanity", "personal attacks"]
        }},
        "production": {{
            "length_seconds": [60, 90],
            "energy_curve": "how energy builds through the song",
            "mix_style": "production aesthetic",
            "hook_strength": "high/medium - how catchy the hook should be"
        }},
        "social_optimization": {{
            "tiktok_friendly": true,
            "meme_potential": "high/medium/low",
            "duet_friendly": true,
            "trending_audio_style": true
        }}
    }},
    "hashtags": "#VansoWorldCup26 #MyAnthem2026 + 3-5 scenario/player/country specific hashtags",
    "applicable_object": "who this targets, e.g. '姆巴佩(隐身/姆总监)'"
}}
```

## Style Rules
- Push Title: NO marketing speak. Sound like a fired-up fan, not a brand.
- Push Description: Must create urgency to click and generate a song NOW.
- AIGC Prompt: Must have vivid, specific imagery that produces viral-worthy lyrics.
- Hashtags: Layer 1 (brand) + Layer 2 (event) + Layer 3 (country) + Layer 4 (player meme) + Layer 5 (scenario)

Return ONLY the JSON object, no extra text."""

    def _call_llm(self, prompt: str, system_role: str = "content_generator") -> str:
        """调用 LLM API"""
        system_prompts = {
            "content_generator": "You are a world-class social media content strategist and AI music prompt engineer specializing in football/soccer culture. You output only valid JSON.",
            "translator": "You are a football culture localization expert. You adapt content culturally, not translate literally. You output only valid JSON.",
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompts.get(system_role, system_prompts["content_generator"])},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.8,
            "response_format": {"type": "json_object"},
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())

        return result["choices"][0]["message"]["content"]
