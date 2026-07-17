# 私募材料智能整理工具

面向券商销售与研究人员的 Streamlit 应用。上传私募公司的 Word、PPT、Excel、PDF、TXT 或 ZIP 材料后，系统自动识别公司与策略，按客户决策视角整理材料，并固定输出一份简版 TXT 和一份详细 Word。

> 本工具不会绕过研究员审核。AI 输出仅来自上传材料，仍应逐项核对原文与数字口径。

## 主要功能

- 多文件拖拽上传，支持 `.docx`、`.pptx`、`.xlsx`、`.xlsm`、`.pdf`、`.txt`、`.zip`
- 自动保存、解析、识别公司名称和投资策略
- 十一个信息模块：公司、策略、团队、策略逻辑、收益来源、风控、业绩、产品规模、投资流程、模型框架、风险提示
- 每个模块保留整理内容、原始文件、页码或等效位置、原始文本
- 生成阶段要求每条事实同时返回来源编号和逐字原文；本地再次检查引文是否存在，以及所有数字是否由引文覆盖
- 详版提示词固定为可追溯版本，要求公司与团队、策略机制、风控、代表产品、客户决策要点和购买前核查事项形成完整、通顺的书面正文；当模型返回过于简略时，系统会按确定性规则从上传材料补齐核心章节，并将会议速记式表达书面化，数字与逐字引文保持不变
- 单独的“引用核验”页面展示进入输出、被拦截和未披露的内容，并可展开完整原文、下载核验 JSON；被拦截事实可在人工修改、重新选源并通过校验后加入指定客户章节
- “引用核验”页面允许逐项修改或删除与原文不一致的生成事实；保存时重新检查引用和数字口径，并立即重建对应 TXT、Word
- 生成设置支持同时选择多个策略；系统分别整理各策略事实后，按单选时的相同版式合并为一份 TXT 和一份 Word
- 简版 TXT 会在不增加材料外事实的前提下整理策略主语、删除机械标签和重复句，使多策略内容保持一段式但更自然连贯
- DeepSeek-V4-Flash、V4-Pro 可切换，同时保留 V3 与 R1 兼容选项，接口地址可配置
- 简版 TXT 参考上传样例，输出一段式产品介绍；详细 Word 直接以 `私募基金投顾推荐报告模板.docx` 为母版，采用 A4、宋体 10.5 磅、模板页边距和段落节奏，不限制页数
- 详细 Word 统一正文首行缩进、行距和段后间距；“材料日期：”“公司概况：”等冒号前标题自动加粗，长段落按完整句子拆分，避免缩进和换行凌乱
- 面向普通客户先解释“产品做什么、怎么获取收益、主要风险”，同时保留专业客户关注的因子、持仓、换手、行业与风格约束等参数；代表产品表格最多保留 18 项最新披露指标，并统一放在全部文字内容之后
- 客户版不展示“购买前需进一步确认”以及内部待办事项，只保留可直接用于客户沟通的产品事实
- 自动从 Word、PPT、Excel、PDF、ZIP 中提取原始图片或相关 PDF 页面截图；正文最后优先放入与关注策略、代表产品匹配的业绩原图，找不到合适原图时才按不少于 8 个日期—数值观测点重绘
- 相同材料、策略、模型、提示词和模板默认命中本地固定版本缓存；Word 包时间戳也会规范化，重复生成字节一致
- SQLite 保存识别信息；ZIP 包含路径穿越防护；单文件解析失败不阻断其他材料
- 兼容 Windows、macOS 与 Linux

## 项目目录

```text
PrivateFund_AI_Assistant/
├── app.py
├── pages/
│   ├── upload.py
│   ├── analysis.py
│   ├── generate.py
│   ├── citations.py
│   └── export.py
├── file_parser/
│   ├── word_parser.py
│   ├── ppt_parser.py
│   ├── excel_parser.py
│   ├── pdf_parser.py
│   ├── txt_parser.py
│   ├── zip_parser.py
│   ├── image_extractor.py
│   └── parser_factory.py
├── ai/
│   ├── deepseek_api.py
│   ├── citation_verifier.py
│   ├── source_detail_enricher.py
│   ├── prompt_template.py
│   ├── company_extract.py
│   ├── strategy_extract.py
│   └── module_extract.py
├── document/
│   ├── txt_generator.py
│   ├── performance_chart.py
│   └── word_generator.py
├── assets/
│   ├── 私募基金投顾推荐报告模板.docx
│   └── 详细介绍材料版式模板.docx
├── database/
│   └── database.py
├── config/
│   └── config.py
├── examples/
│   ├── 涵德投资_示例说明.txt
│   └── create_sample_files.py
├── tests/
│   └── test_core.py
├── uploads/
├── outputs/
├── requirements.txt
├── .env.example
└── README.md
```

## 本地运行

建议使用 Python 3.10 或更高版本。

### Windows PowerShell

```powershell
cd PrivateFund_AI_Assistant
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DEEPSEEK_API_KEY="sk-你的密钥"
streamlit run app.py
```

### macOS / Linux

```bash
cd PrivateFund_AI_Assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DEEPSEEK_API_KEY="sk-你的密钥"
streamlit run app.py
```

浏览器通常会自动打开 `http://localhost:8501`。

API Key 也可在第三页临时输入。页面输入只保存在当前 Streamlit 会话，不写入 SQLite 或源码。不要把真实密钥提交到版本库。

## 配置项

配置集中在 `config/config.py`，均可用环境变量覆盖：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_PROVIDER` | `deepseek` | 预留的模型供应商标识 |
| `DEEPSEEK_API_KEY` | 空 | DeepSeek API Key |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容接口根地址 |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | 默认模型 |
| `MAX_UPLOAD_MB` | `100` | 单文件大小限制 |
| `MAX_CONTEXT_CHARS` | `100000` | 单次请求最多提交的材料字符数 |

模型名和接口能力以实际接入的 DeepSeek 或兼容服务为准；如使用兼容代理，可在页面修改接口地址。

## 使用流程

1. 上传同一家私募的多份材料，点击“保存并自动解析”。
2. 在识别页核对公司、策略及十一类信息；展开卡片查看来源和原文。
3. 填写或读取 DeepSeek API Key，可同时选择一个或多个关注策略；多选时分别整理各策略，再合并生成一份 TXT 和一份 Word。
4. 在“引用核验”页逐条核对合并材料中的事实、逐字引文、原始位置和代表产品图的数据来源；发现有误时可直接修改或删除，保存后自动重建文件。
5. 在导出页下载合并后的 TXT 和 Word；如需重新调用模型，可返回第三步主动勾选“忽略固定缓存”。

## 示例材料

`examples/涵德投资_示例说明.txt` 可直接上传。运行以下命令还会生成 Word、PPT、Excel、PDF 和含多种文件的 ZIP 测试包：

```bash
python examples/create_sample_files.py
```

示例中的机构、策略与内容仅用于软件测试，不应作为真实研究结论。

## 测试

```bash
pytest -q
```

测试覆盖：TXT 解析、公司/策略识别、模块来源追溯、ZIP 路径安全、SQLite 入库、逐字引文和数字拦截、原材料图片提取与优先选择、TXT/DOCX 导出、客户文件无引用标记，以及 DOCX 字节稳定性。

## 已知边界

- 扫描版 PDF 没有文本层时无法直接解析，请先用 OCR 软件生成可搜索 PDF。
- DOCX 文件本身不存储稳定页码，界面使用“段落 N / 表格 N”定位；PPT 和 PDF 会保留真实页码，Excel 使用工作表和行号。
- `.doc`、`.ppt`、`.xls` 旧格式不在本版本支持范围，请先另存为新版 Office 格式。
- 很长的材料会按稳定来源顺序截断到 `MAX_CONTEXT_CHARS`；界面审核仍保留完整解析结果。
- 原材料中的栅格图片和含业绩关键词的 PDF 页面可直接进入报告；Office 原生矢量图表若不能提取为图片，则只有在底层数据能识别出至少 8 个有效观测点时才会重绘，不会从曲线外观反向猜测数据。
- 逐字引用和数字核验能拦截常见幻觉，但不能代替销售或研究人员对事实含义、统计口径和适当性的最终审核。
- 固定版本缓存在本机 `cache/research/`；材料敏感时应按机构数据管理要求控制该目录的访问和清理。

## 扩展其他模型

当前 DeepSeek 调用被封装在 `ai/deepseek_api.py`。后续可新增同样返回 `GeneratedResearch` 的 Provider 客户端，并根据 `LLM_PROVIDER` 在生成页选择客户端，无需改动文件解析和文档导出模块。
