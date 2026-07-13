# C15_ingest_cli 学习笔记

## 1. 本阶段完成了什么

本阶段实现了离线数据摄取脚本 `scripts/ingest.py`。它是阶段 C 的命令行入口，负责接收用户传入的文件或目录路径，然后调用 `IngestionPipeline` 执行完整摄取流程。

前一阶段 C14 已经实现了 Pipeline 主链路，但用户还不能方便地从命令行启动它。C15 做的就是补上这个入口：

```text
python scripts/ingest.py --path docs/sample.pdf --collection test --force
```

脚本支持：

- `--path`：必填，可以是单个文件，也可以是目录。
- `--collection`：可选，指定写入哪个 collection，默认是 `default`。
- `--force`：可选，即使文件未变化也强制重新摄取。
- `--settings`：可选，指定配置文件路径，默认使用项目的 `config/settings.yaml`。

如果 `--path` 是目录，脚本会递归扫描 `.pdf`、`.txt`、`.md`、`.docx` 文件，并逐个调用 pipeline。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `scripts/ingest.py` | 实现离线摄取 CLI，解析参数并调用 `IngestionPipeline` |
| `tests/e2e/test_data_ingestion.py` | 验证 CLI 参数、文件/目录路径、force、collection 和错误返回 |
| `DEV_SPEC.md` | 将 C15 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
命令行
  -> python scripts/ingest.py --path xxx --collection docs --force
  -> main(argv)
      -> _parse_args(argv)
      -> _resolve_paths(args.path)
      -> load_settings(args.settings)
      -> IngestionPipeline(settings=settings)
      -> pipeline.run(path, collection=args.collection, force=args.force)
      -> _print_summary(results)
```

如果传入的是单个文件：

```text
sample.pdf
  -> 校验扩展名是否支持
  -> [sample.pdf]
```

如果传入的是目录：

```text
docs/
  -> 递归扫描
  -> 只保留 .pdf/.txt/.md/.docx
  -> 按路径排序
  -> 逐个摄取
```

如果发生错误，比如路径不存在或文件类型不支持：

```text
异常
  -> 打印 Ingestion failed: ...
  -> 返回 exit code 1
```

## 4. 每个核心文件的作用

### 文件：`scripts/ingest.py`

- 主要职责：提供离线摄取的命令行入口。
- 关键函数 / 类：
  - `main(argv, pipeline_factory)`：脚本主入口，返回进程退出码。
  - `_parse_args(argv)`：解析 `--path`、`--collection`、`--force`、`--settings`。
  - `_resolve_paths(path)`：把文件或目录解析成待摄取文件列表。
  - `_print_summary(results)`：打印每个文件的摄取状态和汇总。
  - `SUPPORTED_SUFFIXES`：定义支持的文件后缀。
- 输入是什么：
  - 命令行参数。
  - 配置文件 `settings.yaml`。
  - 文件或目录路径。
- 输出是什么：
  - 调用 `IngestionPipeline.run()` 的结果。
  - 控制台输出 `INGESTED` / `SKIPPED` 状态和 Summary。
  - 成功返回 exit code `0`，失败返回 `1`。
- 在项目中的作用：
  - 让阶段 C 的 ingestion pipeline 真正可以从命令行运行。

### 文件：`tests/e2e/test_data_ingestion.py`

- 主要职责：验证 CLI 行为，而不是测试真实模型或真实数据库。
- 关键测试：
  - 单文件路径会调用 pipeline，并正确传递 collection 和 force。
  - 目录路径会递归扫描支持的文件类型，忽略不支持的文件。
  - Pipeline 返回 skipped 时，输出中显示 `SKIPPED`。
  - 缺失路径返回 exit code `1`，并输出错误信息。
  - `_resolve_paths()` 会拒绝不支持的文件类型。
- 输入是什么：
  - pytest 临时目录。
  - 临时 settings.yaml。
  - `FakePipeline`。
- 输出是什么：
  - pytest 断言结果。
- 在项目中的作用：
  - 保证 CLI 参数和路径解析稳定，同时避免测试依赖真实 OpenAI、Chroma 或 PDF 解析。

## 5. 新手重点理解

`scripts/ingest.py` 是用户真正会运行的入口。

前面的 `IngestionPipeline` 是库代码，适合被脚本、Dashboard 或其他 Python 模块调用。普通用户更习惯通过命令行运行，所以需要 C15 这一层。

为什么 `main()` 支持传入 `pipeline_factory`？这是为了测试。真实运行时，脚本会创建真正的 `IngestionPipeline(settings=settings)`；测试时则注入 `FakePipeline`，这样不用真的调用模型或数据库，也能验证 CLI 是否把参数传对。

为什么要支持目录？真实知识库通常不是一个文件，而是一批文档。目录扫描能让用户一次性摄取多个文件：

```text
python scripts/ingest.py --path tests/fixtures/sample_documents --collection test
```

为什么只扫描指定后缀？因为当前 Loader/Pipeline 阶段只明确支持这些文档类型。遇到 `.bin`、`.tmp` 这类文件时，脚本会忽略或报错，避免把不该处理的文件送进 pipeline。

为什么要打印 Summary？命令行运行时，用户需要立刻知道处理了多少文件、跳过了多少文件。输出 `ingested/skipped/total` 可以快速判断这次摄取是否符合预期。

这一阶段的核心价值是：阶段 C 的能力终于从“代码模块可用”推进到“命令行可运行”，标志着 Ingestion Pipeline MVP 基本闭环。

# 整体架构与流程

1. 文件定位
项目作用：该文件是 RAG（检索增强生成）系统的离线数据摄入命令行工具（CLI）。它允许用户通过终端命令将本地文档批量导入到系统的知识库中。
所处层级：属于应用脚本层（位于 scripts/ 目录下）。它是用户与底层核心业务逻辑（src/ingestion 模块）之间的桥梁。
核心职责：负责解析命令行参数、校验并收集目标文件路径、加载系统配置、调度数据摄入管道（Pipeline）执行文档处理，并最终向用户反馈处理结果摘要。
2. 函数拆解
main(argv, pipeline_factory)
作用目的：程序的主入口函数，负责编排和协调整个数据摄入流程。
输入输出：
输入：argv（命令行参数列表，可选），pipeline_factory（用于创建 Pipeline 的工厂函数，可选，主要用于方便单元测试或扩展）。
输出：返回整数类型的进程退出码（0 表示成功，1 表示失败）。
核心功能：串联解析参数、解析路径、加载配置、实例化管道、执行摄入任务以及打印结果摘要。包含全局异常捕获，确保出错时能输出错误信息并返回失败状态码。
_parse_args(argv)
作用目的：解析用户输入的命令行参数。
输入输出：
输入：argv（参数列表）。
输出：argparse.Namespace 对象，包含结构化后的参数。
核心功能：定义了 CLI 支持的 4 个核心参数：
--path：必填，指定要摄入的文件或目录。
--collection：选填，指定目标知识库集合名称（默认 default）。
--force：选填，布尔值，强制重新摄入（忽略文件完整性校验）。
--settings：选填，指定配置文件 settings.yaml 的路径。
_resolve_paths(path)
作用目的：校验并收集用户指定路径下所有需要处理的合法文件。
输入输出：
输入：path（字符串或 Path 对象，用户输入的路径）。
输出：list[Path]，包含所有符合条件的文件路径列表。
核心功能：
检查路径是否存在，不存在则抛出 FileNotFoundError。
如果是单文件，校验其后缀是否在支持列表（.pdf, .txt, .md, .docx）中。
如果是目录，则递归搜索该目录下所有符合后缀要求的文件，并按字母排序返回。若目录下无支持的文件则抛出 ValueError。
_print_summary(results)
作用目的：在终端打印数据摄入的最终结果摘要。
输入输出：
输入：results（IngestionResult 对象列表，包含每个文件的处理结果）。
输出：无返回值，直接通过 print 输出到控制台。
核心功能：遍历结果列表，逐行打印每个文档的状态（INGESTED 成功摄入 / SKIPPED 被跳过）、文档 ID、分块数、记录数和图片数。最后统计并打印总体的摄入数、跳过数和总文件数。
3. 执行流程
启动入口：用户执行脚本，触发 if __name__ == "__main__":，调用 main() 函数。
解析参数：main() 调用 _parse_args()，将终端输入的字符串转化为结构化的参数对象。
收集文件：main() 调用 _resolve_paths()，根据参数中的 --path 递归查找并过滤出所有支持格式的文档路径列表。
加载配置：调用 load_settings() 读取 YAML 配置文件，获取向量数据库连接、Embedding 模型等配置信息。
初始化管道：根据配置实例化 IngestionPipeline（或使用传入的 pipeline_factory）。
执行摄入：遍历文件路径列表，逐个调用 pipeline.run()。该方法会在底层执行文档解析、文本分块、向量化并写入向量数据库，返回处理结果。
异常处理：若上述任何步骤抛出异常，捕获异常并打印错误日志，返回退出码 1 终止程序。
输出摘要：若全部执行完毕，调用 _print_summary() 打印每个文件的处理明细和总体统计信息。
正常退出：返回退出码 0，程序结束。
4. 场景示例
业务场景：公司的技术团队需要将本地 ./tech_docs 目录下的最新技术文档（包含 .md 和 .pdf）导入到 RAG 系统的 tech_kb 知识库中，以便后续进行技术问答。

全流程串联：

执行命令：工程师在终端输入：
bash
python scripts/ingest.py --path ./tech_docs --collection tech_kb
参数解析：_parse_args 捕获到路径为 ./tech_docs，集合名为 tech_kb，使用默认配置文件。
文件过滤：_resolve_paths 扫描 ./tech_docs 目录，发现了 api_guide.md、architecture.pdf 以及一张无关的 logo.png。它自动过滤掉不支持的 logo.png，返回 [api_guide.md, architecture.pdf]。
加载与初始化：系统加载 settings.yaml，初始化包含文本分割器和向量库客户端的 IngestionPipeline。
逐个处理：
先处理 api_guide.md：提取文本 -> 切分成 10 个 Chunk -> 向量化 -> 写入向量库。返回结果：成功摄入。
再处理 architecture.pdf：系统检测到该文件的 MD5 哈希值与历史记录一致（且未加 --force 参数），决定跳过处理以节省算力。返回结果：跳过。
打印结果：_print_summary 在终端输出：
text
INGESTED document=doc_api_001 chunks=10 records=10 images=0
SKIPPED document=doc_arch_002 chunks=0 records=0 images=0
Summary: ingested=1 skipped=1 total=2
流程结束：工程师确认 1 个文件更新，1 个文件无变化被跳过，程序正常退出（返回码 0）。