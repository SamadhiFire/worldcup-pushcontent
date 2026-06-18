# Vanso 2026 世界杯 Push 内容生成器

赛事驱动的实时 Push 内容自动化系统，为 AI 音乐生成 App (Vanso) 在世界杯期间提供多语言 Push 文案和 AIGC Prompt。

## 快速开始

### 1. 安装依赖

```bash
cd "C:\Users\AS\Desktop\足球信息实时播报"
pip install -r requirements.txt
# 如果需要 X Trending 数据：
playwright install chromium
```

### 2. 配置

复制 `.env.example` 为 `.env`，填入你的 API 密钥：

```bash
cp .env.example .env
# 编辑 .env 填入 API_FOOTBALL_KEY, LLM_BASE_URL, LLM_API_KEY 等
```

### 3. 使用

```bash
# 生成 Push 内容（完整流程）
python main.py generate \
  --match "FRA vs BRA" \
  --event goal \
  --player "Vinícius Júnior" \
  --minute 78 \
  --score "1-2" \
  --stage "小组赛" \
  --venue "MetLife Stadium"

# 启用 X Trending 情绪校准
python main.py generate \
  --match "ENG vs GER" \
  --event red_card \
  --player "Maguire" \
  --minute 34 \
  --x-trending

# 强制指定场景
python main.py generate \
  --match "MEX vs CAN" \
  --event var_controversy \
  --minute 89 \
  --scenario "主场狂热"

# DRY RUN（不写入 Bitable）
python main.py generate --match "ARG vs FRA" --event goal --player "Messi" --minute 90 --dry-run

# 测试模式（模拟数据）
python main.py test
```

## 事件类型

| 参数值 | 含义 | 默认场景 |
|--------|------|---------|
| `goal` | 进球 | 情怀致敬 |
| `red_card` | 红牌 | 玩梗群嘲 |
| `penalty` | 点球 | 玩梗群嘲 |
| `var_controversy` | VAR 争议 | 主场狂热 |
| `upset` | 爆冷 | 主场狂热 |
| `injury` | 伤退 | 遗憾怀念 |
| `hat_trick` | 帽子戏法 | 情怀致敬 |
| `own_goal` | 乌龙 | 玩梗群嘲 |
| `last_minute_goal` | 绝杀 | 情怀致敬 |
| `penalty_save` | 扑点 | 情怀致敬 |
| `milestone` | 里程碑 | 情怀致敬 |

## 项目结构

```
├── main.py                          # CLI 入口
├── config/settings.py               # 配置管理
├── data_sources/api_football.py     # API-Football 客户端
├── scrapers/x_trending_scraper.py   # X Trending 数据抓取
├── processors/
│   ├── scenario_classifier.py       # 事件→场景分类
│   ├── content_generator.py         # LLM 内容生成
│   └── translator.py               # 多语言文化适配
├── exporters/bitable_exporter.py    # 飞书 Bitable 写入
├── data/player_memes.json           # 球员梗标签库
└── outputs/                         # JSON 输出目录
```

## 数据源

- **API-Football** (主): 赛事结构化数据 (比分、事件、球员)
- **X Trending** (辅): 社媒情绪校准 (复用 x-trending 项目)

## 输出

- **飞书多维表格**: 自动生成记录，运营审核后可发布
- **JSON 文件**: 每次生成的完整数据存档

## 语言支持

EN / ZH / ES / MS / FIL / PT-PT / PT-BR (7 语言)
