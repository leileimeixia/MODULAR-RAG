# D7_query_cli 学习笔记

## 1. 本阶段完成了什么

本阶段完成的是 RAG 查询流程的命令行入口，也就是 `scripts/query.py`。

前面 D1 到 D6 已经完成了一整套 Core 查询能力：

```text
QueryProcessor
  -> DenseRetriever / SparseRetriever
  -> RRFusion
  -> CoreReranker
```

但这些能力还只是 Python 模块。如果想在终端里快速验证查询效果，就需要一个脚本入口。D7 的目标就是提供这个开发调试用 CLI，让用户可以直接运行：

```bash
python scripts/query.py --query "如何配置 Azure？"
```

脚本会加载配置、创建 `HybridSearch`、执行检索、可选执行 rerank，然后把结果打印到终端。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `scripts/query.py` | 在线查询命令行入口，调用 HybridSearch 和 CoreReranker |
| `tests/unit/test_query_cli.py` | 验证 CLI 参数解析、调用链、跳过 rerank、verbose trace 和错误输出 |
| `DEV_SPEC.md` | 标记 D7 完成并更新进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 D7 进度表 |

## 3. 核心调用关系

```text
用户运行 python scripts/query.py --query "问题"
  -> _parse_args()
  -> _parse_filters()
  -> load_settings()
  -> HybridSearch.search()
  -> CoreReranker.rerank()，除非传入 --no-rerank
  -> _print_results()
  -> verbose 模式下 _print_trace()
```

如果传入 `--no-rerank`：

```text
HybridSearch.search()
  -> 直接输出融合后的 retrieval results
```

如果传入 `--verbose`：

```text
创建 TraceContext
  -> 查询各阶段把 trace stage 写进去
  -> 最后打印 trace_id 和每个 stage 的 details
```

## 4. 每个核心文件的作用

### 文件：`scripts/query.py`

* 主要职责：提供终端可运行的在线查询入口。
* 关键函数：`main()`、`_parse_args()`、`_parse_filters()`、`_print_results()`、`_print_trace()`。
* 输入是什么：命令行参数，比如 `--query`、`--top-k`、`--filter`。
* 输出是什么：终端文本结果和进程退出码。
* 在项目中的作用：方便开发阶段快速验证 Retrieval 主链路是否可用。

脚本开头有一段路径处理：

```python
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
```

这是为了让用户直接运行 `python scripts/query.py` 时，也能正常 import `src` 下的项目包。这个写法和 `scripts/ingest.py` 保持一致。

### `main()`

`main()` 是整个 CLI 的入口。它做了这些事：

```python
args = _parse_args(argv)
filters = _parse_filters(args.filter)
settings = load_settings(args.settings)
trace = TraceContext() if args.verbose else None
```

然后创建查询组件：

```python
hybrid_search = HybridSearch(settings=settings)
```

并执行查询：

```python
candidates = hybrid_search.search(
    args.query,
    top_k=args.top_k,
    filters=filters,
    trace=trace,
)
```

如果用户没有传 `--no-rerank`，就继续调用：

```python
CoreReranker(settings=settings).rerank(...)
```

最后统一打印结果。

`main()` 返回 `0` 表示成功，返回 `1` 表示失败。这种写法适合命令行工具，也方便测试。

### `_parse_args()`

这个函数定义命令行参数：

```text
--query       必填，查询文本
--top-k       可选，返回数量，默认 10
--filter      可选，metadata filter，格式 key=value，可重复传
--settings    可选，settings.yaml 路径
--verbose     可选，打印 trace
--no-rerank   可选，跳过 reranker
```

例如：

```bash
python scripts/query.py --query "Azure 配置" --top-k 5 --filter collection=docs --verbose
```

### `_parse_filters()`

这个函数把命令行里的 filter 字符串转换成字典：

```text
["collection=docs", "language=en"]
```

会变成：

```python
{"collection": "docs", "language": "en"}
```

如果 filter 不是 `key=value` 格式，会抛出错误，然后 `main()` 捕获并打印：

```text
Query failed: filter must use key=value format: ...
```

### `_print_results()`

这个函数负责把 `RetrievalResult` 打印成终端可读格式：

```text
[1] chunk_id=xxx score=0.123456
source=docs/a.md
内容预览...
```

它不会打印无限长文本，而是通过 `_preview()` 把正文压缩成最多 500 个字符，方便终端阅读。

### `_print_trace()`

verbose 模式下会打印 trace：

```text
Trace:
trace_id=...
- query_processing method=...
- dense_retrieval method=...
- sparse_retrieval method=...
- rrf_fusion method=...
- rerank method=...
```

这对调试很有用。你可以看到一次查询到底走了哪些阶段，以及每个阶段记录了什么 details。

### 文件：`tests/unit/test_query_cli.py`

* 主要职责：验证命令行入口本身是否正确编排。
* 关键测试：
  * 正常情况下会调用 `HybridSearch` 和 `CoreReranker`。
  * `--no-rerank` 时不会调用 reranker。
  * `--verbose` 时会打印 trace。
  * 非法 filter 会返回退出码 1，并输出错误信息。

测试里没有真的创建 embedding、vector store 或 BM25 索引，而是通过 `hybrid_search_factory` 和 `reranker_factory` 注入 fake 对象。这种设计让 CLI 的测试稳定、快速，也不会依赖本地数据是否已经 ingest。

## 5. 新手重点理解

这一阶段最重要的是理解：CLI 不是新的业务逻辑，而是一个“入口包装”。

业务逻辑仍然在 Core 层：

```text
HybridSearch
CoreReranker
```

`scripts/query.py` 只负责：

```text
解析命令行参数
加载配置
调用 Core 层
打印结果
返回退出码
```

这是一种很常见的工程拆分。好处是后续 MCP tool、Dashboard、API 服务都可以复用 Core 层逻辑，而不是复制 CLI 里的逻辑。

另一个重点是 `--no-rerank`。这个参数方便调试：

```text
不用 rerank：看 fusion 后的原始检索结果
使用 rerank：看最终精排结果
```

如果你怀疑 reranker 影响了排序，就可以用这个参数对比。

`--verbose` 也很重要。它让查询变得透明，可以看到每个阶段是否执行、候选数量是多少、是否发生 fallback。对于 RAG 项目来说，这种可观察性非常关键，因为检索质量问题往往需要看中间过程才能定位。

本阶段在 RAG 流程中的位置是：

```text
终端命令
  -> scripts/query.py
  -> HybridSearch
  -> CoreReranker
  -> 终端输出结果
```

完成 D7 后，阶段 D 的 Retrieval MVP 已经闭环：从用户 query 到 Top-K 结果，已经可以通过命令行实际跑起来。


# 整体结构与流程

1. 文件定位
项目作用：该文件是 RAG（检索增强生成）系统的一个命令行交互入口（CLI），用于在线查询知识库。
所处层级：属于项目的脚本层/应用层（位于 scripts/ 目录下），直接面向终端用户或外部调用方。
核心职责：接收用户的查询指令和参数，调度核心的“混合检索”与“重排序”模块，获取最匹配的文档片段，并将结果及运行追踪信息格式化输出。
2. 函数拆解
函数名	作用目的	输入/输出	核心功能
main	主程序入口，串联整个查询生命周期。	入：命令行参数列表、可选的检索/重排工厂函数。<br>出：进程退出码（0成功，1失败）。	解析参数、加载配置、初始化组件、执行检索与重排、打印结果与追踪日志，并处理异常。
_parse_args	解析命令行参数。	入：参数列表。<br>出：argparse.Namespace 对象。	定义 --query, --top-k, --filter, --verbose 等参数规则，并提取用户输入的值。
_parse_filters	解析元数据过滤条件。	入：字符串序列（如 ["key=value"]）。<br>出：字典（如 {"key": "value"}）。	校验并拆分 key=value 格式的字符串，确保键值非空，转换为字典供检索模块使用。
_print_results	格式化打印最终检索结果。	入：RetrievalResult 对象列表。<br>出：无（直接打印到控制台）。	遍历结果，按序号打印 chunk_id、相关性分数、来源文件路径以及文本内容预览。
_preview	生成文本内容的截断预览。	入：原始文本、最大长度限制（默认500）。<br>出：处理后的字符串。	将文本中的换行/多余空格规范化为单空格；若超长则截断并追加 ...。
_print_trace	打印系统运行追踪信息。	入：TraceContext 对象。<br>出：无（直接打印到控制台）。	在 verbose 模式下，输出 trace_id 以及检索、重排等各个阶段的名称、方法和详细耗时/状态。
3. 执行流程
启动与解析：程序从 __main__ 启动，调用 main()。main() 首先调用 _parse_args() 获取用户输入的查询词、Top-K 数量、过滤条件等。
预处理与初始化：
调用 _parse_filters() 将过滤字符串转为字典。
调用 load_settings() 加载系统 YAML 配置。
根据 --verbose 参数决定是否实例化 TraceContext（用于记录链路耗时）。
实例化 HybridSearch（混合检索引擎）。
混合检索：调用 hybrid_search.search()，结合向量检索和关键词检索，召回初始的候选文档块（Candidates）。
重排序（Rerank）：如果未传入 --no-rerank，则实例化 CoreReranker，调用 reranker.rerank() 对候选块进行精细化打分，截取最终的 Top-K 结果。
结果输出：调用 _print_results() 将最终结果打印到控制台。
追踪输出：如果开启了 --verbose，调用 _print_trace() 打印底层执行链路的追踪日志。
退出：捕获可能的异常并返回相应的退出码（0 或 1）。
4. 场景示例
业务场景：运维工程师在终端查询“如何配置阿里云OSS的跨域规则”，并希望只看官方手册中的内容，同时想看看系统底层的检索耗时。

用户输入：

bash
python query.py --query "如何配置阿里云OSS的跨域规则" --top-k 3 --filter "doc_type=manual" --verbose
全流程串联：

参数解析：_parse_args 提取出 query 为“如何配置...”，top_k 为 3，filter 为 ["doc_type=manual"]，verbose 为 True。
过滤转换：_parse_filters 将 filter 转换为 {"doc_type": "manual"}。
混合检索：系统初始化 HybridSearch，在知识库中搜索。因为加了 filter，系统会排除掉非 manual 类型的文档（如博客、论坛帖子），通过 BM25 和 向量相似度 召回 10 个最相关的候选 Chunk。
重排序：系统初始化 CoreReranker（通常使用 Cross-Encoder 模型），对这 10 个 Chunk 与 Query 进行深度语义匹配打分，选出得分最高的前 3 个。
结果打印：_print_results 在控制台输出这 3 个结果的序号、分数（如 0.9523）、来源（如 source=oss_official_manual.pdf）以及前 500 个字符的配置步骤预览。
追踪打印：因为加了 --verbose，_print_trace 打印出类似 trace_id=xxx，以及 - retrieval method=hybrid details=... 和 - rerank method=cross_encoder details=... 的底层执行日志，方便工程师排查性能瓶颈。
结束：程序顺利执行完毕，返回状态码 0。