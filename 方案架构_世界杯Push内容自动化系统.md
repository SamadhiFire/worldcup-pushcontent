## Vanso 2026 世界杯 Push 内容自动化系统 — 技术方案

### 一、系统全景架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                         数据感知层 (Data Layer)                       │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌────────────┐ │
│  │ 赛事API      │  │ 赛程/阵容DB  │  │ 社媒热点爬取 │  │ 球员百科DB  │ │
│  │ (API-Football)│  │ (预置)      │  │ (X/TikTok)  │  │ (预置)     │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬──────┘ │
│         └────────────────┬┴────────────────┴───────────────┘         │
│                          ▼                                           │
│              事件归一化 (Event Normalizer)                              │
└──────────────────────────┬───────────────────────────────────────────┘
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      内容生成层 (Generation Layer)                    │
│                                                                      │
│  ┌────────────────┐    ┌────────────────┐    ┌────────────────────┐ │
│  │ 场景分类器      │───▶│ Prompt 模板库   │───▶│  LLM 内容生成引擎   │ │
│  │ (Scenario       │    │ (6 场景 ×      │    │                    │ │
│  │  Classifier)    │    │  结构化模板)    │    │  · Push Title      │ │
│  └────────────────┘    └────────────────┘    │  · Push Desc       │ │
│                                              │  · AIGC Prompt     │ │
│                                              │  · Hashtags        │ │
│                                              └────────┬───────────┘ │
│                                                       ▼             │
│                                    ┌──────────────────────────────┐ │
│                                    │  多语言适配引擎               │ │
│                                    │  EN → ZH/ES/MS/FIL/PT-PT/   │ │
│                                    │        PT-BR                │ │
│                                    │  (文化适配，非机械翻译)        │ │
│                                    └──────────────┬───────────────┘ │
└───────────────────────────────────────────────────┬──────────────────┘
                                                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      输出与审核层 (Output Layer)                      │
│                                                                      │
│  ┌──────────────────┐   ┌─────────────────┐   ┌──────────────────┐ │
│  │ 飞书多维表格       │   │  审核工作流       │   │  Vanso 后端 API  │ │
│  │ (Bitable)         │◀──│  (飞书审批/       │──▶│  (拉取已审核内容 │ │
│  │  主表 + 语言子表   │   │   Bitable 状态)  │   │   执行 Push)    │ │
│  └──────────────────┘   └─────────────────┘   └──────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

---

### 二、数据感知层：赛事数据源选型

**主数据源：API-Football (api-football.com)**

选择理由：覆盖 2026 世界杯全部赛事，提供实时比分、事件时间线（进球/红牌/黄牌/VAR/换人/点球）、球员统计、阵容数据。免费 tier 100 次请求/天，付费 tier 起步 $9.99/月。

需要预置的基础数据（赛前一次性拉取缓存）：

- 完整赛程表（64 场比赛的日期、场馆、对阵）
- 32 支参赛队伍阵容名单（球员姓名、号码、位置、国籍）
- 关键球员画像表（姆巴佩、梅西、C罗、维尼修斯、凯恩、内马尔等 50+ 球星的"梗标签"——如姆巴佩=姆总监/神龟，凯恩=无冠魔咒，维尼修斯=爱哭鬼）
- 历史交锋数据和经典叙事（如英格兰"足球回家"、阿根廷巴西世仇）

**辅助数据源（可选增强）**

社媒热点方面，可以用 X (Twitter) 的 Trending API 获取比赛期间的热门话题和梗，作为内容生成的"情绪校准器"——不是直接搬运，而是让 LLM 知道当前球迷的情绪风向。TikTok Trending 可以作为 hashtag 推荐的参考。这两个在 MVP 阶段可以不做，先靠预设的梗标签库。

---

### 三、事件归一化与场景分类

**事件归一化输出格式：**

```json
{
  "event_id": "WC2026_GM_A3_78",
  "match": {
    "id": "WC2026_GM_A3",
    "stage": "group_stage",
    "team_a": { "name": "France", "code": "FRA", "score": 1 },
    "team_b": { "name": "Brazil", "code": "BRA", "score": 2 },
    "venue": "MetLife Stadium, New Jersey",
    "date": "2026-06-20T20:00:00-04:00",
    "minute": 78
  },
  "event_type": "goal",
  "event_detail": {
    "scorer": { "name": "Vinícius Júnior", "number": 7, "team": "BRA" },
    "assist": { "name": "Rodrygo", "number": 11, "team": "BRA" },
    "goal_type": "open_play"
  },
  "match_context": {
    "is_upset": true,
    "score_before": { "FRA": 1, "BRA": 1 },
    "is_home_team": false,
    "key_players_involved": ["Vinícius Júnior"],
    "narrative_tags": ["进球打脸", "舞蹈庆祝", "巴西funk"]
  }
}
```

**场景分类器逻辑：**

场景分类不是简单的 if-else，而是基于事件类型 + 球员画像 + 比赛上下文的综合判断。一场赛事可能同时命中多个场景。

```
分类规则矩阵：

场景一（玩梗群嘲）触发条件：
  - 知名球员表现不佳（隐身/失误/踢飞点球）
  - 争议判罚（VAR 误判/黑哨）
  - 热门球队惨败/出局
  - 球员负面梗标签命中（姆总监/爱哭鬼/无冠魔咒）

场景二（情怀致敬）触发条件：
  - 传奇球员里程碑/疑似告别战
  - 球员进球后致敬动作
  - 逆转/绝杀展现意志力
  - 传奇球员相关叙事标签命中（GOAT/最后一舞）

场景三（社交派对）触发条件：
  - 赛前阶段（开球前 2-4 小时，预热窗口）
  - 东道主比赛日
  - 周末/节假日的焦点战
  - 小组赛阶段（氛围轻松，适合玩梗）

场景四（短视频二创）触发条件：
  - 出现视觉冲击力强的瞬间（世界波/倒钩/离谱失误）
  - 球员夸张庆祝/反应
  - 适合卡点/鬼畜的重复性动作
  - 赛前预测窗口

场景五（主场狂热）触发条件：
  - 美/加/墨东道主比赛
  - VAR 争议判罚
  - 爆冷/黑马
  - 赛场突发事件（球迷闯入/天气中断）
  - 新规争议

场景六（遗憾怀念）触发条件：
  - 知名球员伤退/落选
  - 球队出局后的告别画面
  - 已故传奇相关纪念日
  - 未能晋级的重要球队
```

分类器输出示例（一次事件可能触发多个场景）：

```json
{
  "triggered_scenarios": [
    {
      "scenario_id": 2,
      "scenario_name": "情怀与致敬",
      "confidence": 0.92,
      "reason": "Vinícius Júnior 进球打脸批评者 + 舞蹈庆祝 → 匹配'进球打脸/舞蹈庆祝'模板",
      "matched_template": "vini_goal_celebration",
      "applicable_objects": ["维尼修斯", "巴西国家队"]
    },
    {
      "scenario_id": 1,
      "scenario_name": "玩梗群嘲",
      "confidence": 0.65,
      "reason": "法国队落后 → 可触发对法国/姆巴佩的嘲讽",
      "matched_template": "mbappe_ghost",
      "applicable_objects": ["姆巴佩", "法国国家队"]
    }
  ]
}
```

---

### 四、AIGC Prompt 结构化 JSON 规范

这是给 Vanso 生成引擎的结构化输入，不是自然语言。每条 Push 内容对应一个结构化的 AIGC Prompt JSON：

```json
{
  "aigc_prompt": {
    "title_hint": "The Turtle Retreats",
    "genre": {
      "primary": "Bossa Nova",
      "secondary": "Comedy",
      "fusion": null
    },
    "mood": {
      "primary": "sarcastic",
      "secondary": "playful",
      "intensity": "medium"
    },
    "tempo": {
      "bpm_range": [100, 120],
      "feel": "laid-back",
      "rhythm_pattern": "bossa nova clave"
    },
    "instrumentation": {
      "core": ["nylon guitar", "light percussion", "upright bass"],
      "accent": ["whistle", "finger snaps"],
      "exclude": ["heavy distortion", "synthesizer"]
    },
    "vocal": {
      "style": "spoken-word singing",
      "gender": "male",
      "language": "en",
      "tone": "mocking but playful",
      "reference": "They Might Be Giants comedic style"
    },
    "lyrics": {
      "theme": "A famous football player who acts like a boss but disappears when it matters most",
      "key_imagery": [
        "a turtle slowly retreating into its shell",
        "a director giving orders from the sideline but never playing",
        "the biggest stage, the brightest lights, and nobody's home"
      ],
      "tone": "sarcastic, humorous, TikTok-meme-worthy",
      "structure": "verse-chorus-verse-chorus-bridge-chorus",
      "must_include": ["turtle metaphor", "vanishing act"],
      "must_avoid": ["explicit profanity", "personal attacks beyond public persona"]
    },
    "production": {
      "duration_policy": "no fixed duration; let the music model decide the full song length",
      "energy_curve": "starts chill, builds slightly in chorus, drops back",
      "mix_style": "lo-fi warmth, slightly vintage",
      "hook_strength": "high - chorus should be instantly singable"
    },
    "social_optimization": {
      "tiktok_friendly": true,
      "meme_potential": "high",
      "duet_friendly": true,
      "trending_audio_style": true
    }
  }
}
```

**六个场景的 AIGC Prompt 风格速查：**

| 场景 | 主流派倾向 | 情绪基调 | BPM 范围 | 核心特征 |
|------|-----------|---------|---------|---------|
| 一·玩梗群嘲 | Bossa Nova / Punk / Country Comedy | 嘲讽、搞笑、挑衅 | 100-180 | 高 meme 潜力，副歌要朗朗上口 |
| 二·情怀致敬 | Orchestral Pop / R&B Ballad / Funk-Trap | 史诗、感动、自信 | 70-140 | 电影感制作，情感浓烈 |
| 三·社交派对 | Irish Pub-Rock / EDM Festival / Rap Battle | 狂欢、对抗、认输 | 120-150 | 适合群体合唱，互动性强 |
| 四·短视频二创 | Phonk / Glitch-Hop / Cinematic Rock | 神秘、抓马、魔性 | 130-180 | 卡点友好，BGM 属性强 |
| 五·主场狂热 | Heavy Metal / Stadium Hip-Hop / EDM | 愤怒、狂热、震撼 | 128-170 | 重低音，人群chant，体育场氛围 |
| 六·遗憾怀念 | Alt-Rock / Synth-Pop Ballad / Blues | 忧伤、怀念、神圣 | 60-100 | 空灵感，致敬氛围，80s怀旧 |

---

### 五、飞书多维表格 Schema 设计

采用主表 + 语言子表的双表结构，通过关联字段连接。

**表 1：Push Content Master（推送内容主表）**

| 字段名 | 字段类型 | 说明 |
|--------|---------|------|
| Record ID | 自动编号 | 主键 |
| Match ID | 文本 | 比赛唯一标识，如 WC2026_GM_A3 |
| 比赛日期 | 日期 | 比赛日期时间 |
| 对阵 | 文本 | 如 "FRA 🇫🇷 vs BRA 🇧🇷" |
| 赛事阶段 | 单选 | 小组赛/16强/8强/4强/半决赛/决赛 |
| 比赛场馆 | 文本 | 场馆名 + 城市 |
| 触发事件 | 文本 | 事件描述，如"78' Vinícius Júnior 进球（Rodrygo 助攻）" |
| 事件类型 | 多选 | 进球/红牌/点球/VAR争议/爆冷/伤退/帽子戏法/乌龙… |
| 关联球员 | 文本 | 球员姓名，如 "Vinícius Júnior" |
| 关联国家 | 多选 | 涉及的国家，如 "巴西" |
| 场景类型 | 单选 | 六大场景之一 |
| 情绪标签 | 多选 | 愤怒/嘲讽/狂欢/怀旧/感动/挑衅/搞笑/神圣 |
| AIGC Prompt (EN) | 文本(长) | 结构化 JSON，英文基准版 |
| Hashtag 建议 | 文本 | 通用+国家+球员+场景 组合 |
| 适用对象/热点 | 文本 | 如 "维尼修斯(进球打脸/舞蹈庆祝)" |
| 审核状态 | 单选 | 🟡待审核 / 🟢已通过 / 🔴已废弃 / 🔵已发布 |
| 审核备注 | 文本 | 审核人员的修改意见或通过说明 |
| 创建时间 | 创建时间 | 自动记录 |
| 发布时间 | 日期 | 实际推送时间 |
| 语言版本 | 关联字段 | 关联到「语言版本子表」 |
| 优先级 | 单选 | 🔥紧急 / ⭐高 / 📌普通 |

**表 2：Language Variants（语言版本子表）**

| 字段名 | 字段类型 | 说明 |
|--------|---------|------|
| Record ID | 自动编号 | 主键 |
| 关联主表 | 关联字段 | 关联到「推送内容主表」 |
| 语言 | 单选 | EN / ZH / ES / MS / FIL / PT-PT / PT-BR |
| Push Title | 文本 | 推送标题（本地化版本） |
| Push Description | 文本 | 推送描述（本地化版本） |
| AIGC Prompt | 文本(长) | 结构化 JSON（含本地化歌词意象） |
| Hashtag 本地化 | 文本 | 本地化 hashtag（如西班牙语球迷圈的流行标签） |
| 文化适配备注 | 文本 | 翻译者/审核者的适配说明 |

**Bitable 视图规划：**

- 看板视图（按审核状态分列）：运营日常审核用
- 日历视图（按比赛日期）：预览赛事内容排期
- 画册视图（按场景类型分组）：场景维度浏览
- 筛选视图（"待发布+已通过"）：后端拉取数据用

---

### 六、内容生成 Pipeline 详细设计

Pipeline 分为两条线路并行运作：

**线路 A：赛前预生成（Pre-match Generation）**

```
赛程表 → 遍历未来 48h 比赛
       → 对每场比赛 × 可能场景组合 预生成内容
       → 写入 Bitable（状态：🟡待审核）
       → 运营提前审核储备
```

触发时机：每天 UTC 06:00 跑一次，扫描未来 48 小时的比赛。

生成逻辑：根据对阵双方 + 球员阵容 + 历史叙事，预判最可能命中的场景。比如法国 vs 巴西，预生成内容覆盖：姆巴佩隐身(场景一)、维尼修斯进球打脸(场景二)、派对预热(场景三)、主场氛围(场景五)等多个场景。

预估量：64 场比赛 × 平均每场 3-4 个预生成场景 × 7 语言 = 约 1500-1800 条内容。

**线路 B：赛中实时生成（In-match Real-time Generation）**

```
每 5 分钟轮询比赛事件 API
→ 检测到新关键事件
→ 事件归一化 + 场景分类
→ 对命中的每个场景：
    → 加载对应 Prompt 模板
    → 注入比赛实时上下文
    → LLM 生成 EN 基准内容（Push Title + Desc + AIGC JSON + Hashtags）
    → 多语言文化适配（7 语言并行）
→ 写入 Bitable（状态：🟡待审核，优先级：🔥紧急）
→ 飞书群通知运营人员
```

**内容生成的 LLM Prompt 工程：**

系统级 prompt 模板示例（以场景一为例）：

```
你是 Vanso 的世界杯 Push 内容生成引擎。你的任务是基于真实赛况，生成极具煽动性的 Push 文案和 AI 音乐生成 Prompt。

当前赛事上下文：
- 比赛：{team_a} vs {team_b}
- 事件：{event_description}
- 分钟：{minute}'
- 比分：{score}
- 关联球员：{player_name}（梗标签：{player_meme_tags}）

目标场景：场景一 · 玩梗群嘲

生成要求：
1. Push Title：15-30字符，短促、指令型、煽动性，带一个相关 emoji 开头
2. Push Description：40-80字符，情绪点燃+行动号召，引导用户点击生成歌曲
3. AIGC Prompt：输出为结构化 JSON，包含以下字段：
   - genre (primary/secondary/fusion)
   - mood (primary/secondary/intensity)
   - tempo (bpm_range/feel/rhythm_pattern)
   - instrumentation (core/accent/exclude)
   - vocal (style/gender/language/tone/reference)
   - lyrics (theme/key_imagery/tone/structure/must_include/must_avoid)
   - production (duration_policy/energy_curve/mix_style/hook_strength)
   - social_optimization (tiktok_friendly/meme_potential/duet_friendly)
4. Hashtags：5-8个，包含 #VansoWorldCup26 + 国家标签 + 球员梗标签 + 场景标签

风格基准：抛弃营销腔调，采用球迷视角的"发疯文学"。要像一个刚看完比赛的球迷在跟朋友吐槽，而不是一个品牌在发公告。
```

**多语言适配策略：**

不是直译，而是"文化适配重写"。对每种语言有专门的适配指令：

| 语言 | 适配策略 |
|------|---------|
| EN (基准) | 先生成完整英文版，作为其他语言的参考基准 |
| ZH (中文) | 融入中文球迷圈梗（如"姆总监""凯恩无冠""退钱哥"），语气偏微博/虎扑风 |
| ES (西班牙语) | 拉美足球文化用语，热情奔放，可用当地俚语（如 "boludo" "ché" 等） |
| MS (马来语) | 口语化，融入东南亚球迷文化，适度混入英语借词（Manglish 风格） |
| FIL (菲律宾语) | Taglish 风格（菲律宾语+英语混搭），年轻 TikTok 用户调性 |
| PT-PT (葡萄牙-欧洲) | 偏正式足球用语，C罗/葡萄牙国家队情怀导向 |
| PT-BR (葡萄牙-巴西) | 巴西足球文化用语，可融入 funk/samba 文化元素，极度热情 |

**翻译 LLM Prompt 模板：**

```
你是一位精通{target_language}的足球文化本地化专家，同时也是社交媒体文案高手。

以下是英文基准版本的 World Cup Push 内容：
- Title: {en_title}
- Description: {en_description}
- AIGC Prompt: {en_aigc_prompt_json}

请将其适配为{target_language}版本，要求：
1. 不是逐字翻译，而是文化适配重写
2. 融入{target_language}足球文化的本地梗和表达习惯
3. 保持原文的情绪强度和煽动性
4. Push Title 保持 15-30 字符
5. Push Description 保持 40-80 字符
6. AIGC Prompt 的 lyrics 字段需要适配为{target_language}的歌词意象和文化引用
7. Hashtag 需要加入{target_language}球迷社区的流行标签
8. 输出格式与英文版完全一致（结构化 JSON）

文化适配指南：
{language_specific_guidelines}
```

---

### 七、自动化调度方案

**技术选型：QoderWork Scheduled Task + lark-cli**

```
┌─────────────────────────────────────────────────────────┐
│  定时任务编排                                             │
│                                                         │
│  ① 每日 06:00 UTC (赛前预生成)                           │
│     → 扫描未来 48h 赛程                                  │
│     → 预生成内容 → 写入 Bitable                          │
│     → 飞书群通知运营"今日预生成内容已就绪"                  │
│                                                         │
│  ② 每 5 分钟 (赛中实时监控)                              │
│     → 轮询 API-Football 事件端点                         │
│     → 检测新事件 → 场景分类 → 内容生成                    │
│     → 写入 Bitable → 飞书群即时通知                       │
│     → 仅在有比赛进行时激活                                │
│                                                         │
│  ③ 赛后 1 小时 (赛后总结)                                │
│     → 生成本场比赛的"最佳 Push"回顾                       │
│     → 统计点击率（如后端回传数据）                         │
│     → 更新梗标签库（发现新梗）                            │
│                                                         │
│  ④ 每周一 09:00 UTC (周报)                               │
│     → 汇总本周 Push 表现数据                              │
│     → 生成优化建议                                       │
│     → 推送到飞书群                                       │
└─────────────────────────────────────────────────────────┘
```

---

### 八、Hashtag 策略

Hashtag 采用分层组合策略：

```
Layer 1 - 品牌层（必选）：
  #VansoWorldCup26  #MyAnthem2026  #AIMusic

Layer 2 - 赛事层（按阶段）：
  #WorldCup2026  #WC2026  #FIFAWorldCup

Layer 3 - 国家层（按对阵）：
  每个参赛国对应 2-3 个 hashtag，如：
  🇧🇷 BRA: #VaiBrasil #SeleçãoCanarinha #BrazilWorldCup
  🇫🇷 FRA: #AllezLesBleus #EquipeDeFrance #FranceWorldCup
  🇦🇷 ARG: #VamosArgentina #LaAlbiceleste #ArgentinaWorldCup

Layer 4 - 球员层（按触发球员）：
  球员姓名 + 球员梗标签，如：
  Mbappé: #Mbappe #DirectorMbappe #TurtlePower
  Kane: #HarryKane #NoTrophyKane #KaneCurse

Layer 5 - 场景层（按场景类型）：
  场景一: #FootballMeme #SavageTroll #RoastAnthem
  场景二: #FootballTribute #LastDance #GOATDebate
  场景三: #WatchParty #MatchDay #SquadAnthem
  场景四: #TikTokFootball #ViralBGM #FootballEdit
  场景五: #StadiumAnthem #HomeGround #VARRage
  场景六: #FootballLegend #MissedWorldCup #InMemoriam
```

---

### 九、Hashtag 国家映射表（部分示例）

| 国家 | 代码 | 官方 Hashtag | 球迷文化 Hashtag | 梗/昵称 Hashtag |
|------|------|-------------|-----------------|----------------|
| 巴西 | BRA | #VaiBrasil | #SeleçãoCanarinha | #SambaFootball |
| 阿根廷 | ARG | #VamosArgentina | #LaAlbiceleste | #MessisArmy |
| 法国 | FRA | #AllezLesBleus | #EquipeDeFrance | #FrenchFlair |
| 英格兰 | ENG | #ItsComingHome | #ThreeLions | #FootballComingHome |
| 德国 | GER | #DieMannschaft | #ZusammenHalt | #GermanMachine |
| 西班牙 | ESP | #VamosEspaña | #LaRoja | #TikiTaka |
| 葡萄牙 | POR | #ForçaPortugal | #SeleçãoDasQuinas | #CR7Forever |
| 墨西哥 | MEX | #NadaNosDetiene | #ElTri | #AztecaPride |
| 美国 | USA | #USMNT | #StarsAndStripes | #SoccerStates |
| 加拿大 | CAN | #CANMNT | #TrueNorth | #MapleLeafFC |

---

### 十、实施路线图

**Phase 0：基础设施搭建（赛前 4 周）**
- 注册 API-Football 账号，拉取赛程和球队数据
- 预置球员梗标签库（50+ 球星 × 梗标签）
- 创建飞书多维表格（主表+子表+视图）
- 搭建 Prompt 模板库（6 场景 × 结构化模板）

**Phase 1：MVP 验证（赛前 2 周）**
- 实现赛前预生成 Pipeline（EN + ZH 两种语言先跑通）
- 手动触发测试：用历史比赛数据模拟事件，验证生成质量
- 运营团队审核流程试跑
- 优化 Prompt 模板（根据生成质量迭代）

**Phase 2：全语言上线（赛前 1 周）**
- 补全全部 7 语言的生成能力
- 接入赛中实时监控 Pipeline
- 全量预生成小组赛阶段内容（约 48 场 × 3 场景）
- 压力测试：模拟高频事件场景

**Phase 3：赛事运行（2026-06-11 至 2026-07-19）**
- 全自动 Pipeline 运行 + 人工审核
- 每日复盘生成质量，动态调整 Prompt 模板
- 根据社媒热点临时增加梗标签
- 淘汰赛阶段加强实时性（缩短轮询间隔至 2 分钟）

---

### 十一、风险与应对

| 风险 | 影响 | 应对方案 |
|------|------|---------|
| API-Football 限流/宕机 | 赛中无法获取实时事件 | 备用数据源 (ESPN RSS) + 本地缓存 + 降级为手动触发 |
| LLM 生成质量不稳定 | 产出文案不够尖锐/跑题 | Prompt 模板精调 + Few-shot 示例 + 人工审核兜底 |
| 多语言文化踩雷 | 翻译不当引发争议 | 每种语言指定文化审核人 + 敏感词过滤列表 |
| 赛事冷门事件无预设梗 | 生成内容缺乏深度 | 球员梗标签库持续更新 + 通用模板兜底 |
| Bitable 写入延迟 | 审核人员看不到最新内容 | 飞书群即时推送兜底 + 本地缓存队列 |
| 内容同质化 | 不同比赛生成的文案雷同 | 在 Prompt 中注入对阵历史+球员故事线等差异化上下文 |

---

### 十二、预估成本

| 项目 | 预估费用/月 |
|------|-----------|
| API-Football (Pro Plan) | ~$30 |
| LLM 调用 (赛前预生成 + 赛中实时) | ~$50-150（取决于调用量和模型选择） |
| 飞书 Bitable | 企业版已含 |
| QoderWork 定时任务 | 已含 |

**总计约 $80-180/月**，对于 39 天的世界杯周期来说，总投入约 $100-250。

---

### 十三、待决策清单

1. **API-Football 账号**：需要你注册并提供 API Key，或者我来帮你注册？
2. **飞书多维表格**：在哪个飞书空间创建？是否需要特定的权限设置？
3. **AIGC Prompt JSON 字段**：上面的结构化 JSON 规范是否覆盖了 Vanso 生成引擎的所有输入字段？是否有引擎特定的字段需要补充？
4. **审核通知群**：赛中实时生成后，通知到哪个飞书群？
5. **后端对接协议**：Vanso 后端从 Bitable 拉取数据的协议是什么？是否需要我提供 API 对接文档？
6. **社媒数据**：MVP 阶段是否先不做社媒热点爬取，纯靠预设梗标签库？
7. **球员梗标签库**：你能提供已有的梗标签清单吗？还是需要我从零开始整理？
