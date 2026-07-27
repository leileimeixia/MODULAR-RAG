# H5_recall_regression 学习笔记

## 1. 本阶段完成了什么

本阶段实现了 Recall 回归测试，也就是 `tests/e2e/test_recall.py`。

前面 H1 到 H4 已经完成了评估器、组合评估器、评估运行器和 Dashboard 评估面板。H5 的重点是把这些能力用于“防止检索质量退步”。它通过固定一份 golden test set，运行 `EvalRunner + CustomEvaluator`，然后检查 `hit_rate` 和 `mrr` 是否达到阈值。

通俗理解，这个测试像一条质量红线：以后无论你改切块、embedding、向量库、稀疏检索、融合逻辑还是 rerank，只要导致标准问题检索不到应该命中的 chunk，这个回归测试就会失败。

这一阶段在 RAG 流程中的位置是“评估体系的回归守门”。它不是新功能页面，也不是新检索算法，而是用测试把已有检索质量固定住。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `tests/e2e/test_recall.py` | 新增 recall 回归测试，基于 golden set 固定 hit_rate/mrr 阈值 |
| `tests/fixtures/golden_test_set.json` | 扩充 golden test set，增加第二条标准测试用例 |
| `DEV_SPEC.md` | 更新 H5 任务进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步自动开发进度表 |

## 3. 核心调用关系

```text
pytest tests/e2e/test_recall.py
  -> EvalRunner(settings, hybrid_search, evaluator)
  -> load_golden_test_set(tests/fixtures/golden_test_set.json)
  -> GoldenHybridSearch.search(query, top_k)
  -> 返回 RetrievalResult 列表
  -> CustomEvaluator.evaluate(retrieved_ids, expected_chunk_ids)
  -> EvalRunner 聚合 metrics
  -> 断言 hit_rate/mrr 达到阈值
```

核心数据流是：

```text
golden_test_set.json
  -> query + expected_chunk_ids
  -> GoldenHybridSearch 返回 retrieved_ids
  -> CustomEvaluator 计算 hit_rate / mrr / precision
  -> EvalReport.metrics
  -> 阈值断言
```

## 4. 每个核心文件的作用

### 文件：`tests/e2e/test_recall.py`

* 主要职责：作为 recall 质量回归测试。
* 关键常量：
  * `GOLDEN_TEST_SET`：指向 `tests/fixtures/golden_test_set.json`。
  * `MIN_HIT_RATE = 1.0`：要求所有标准问题至少命中一个期望 chunk。
  * `MIN_MRR = 0.75`：要求命中位置不能太靠后。
* 关键类：
  * `GoldenHybridSearch`：一个确定性的 fake 检索器，根据 query 返回固定结果。
  * `FakeSettings`：提供 EvalRunner 所需的 retrieval 配置。
* 关键测试：
  * `test_golden_set_recall_thresholds_hold()`：运行 EvalRunner，并断言 recall 指标达到阈值。
* 输入是什么：golden test set。
* 输出是什么：pytest 通过或失败。
* 在项目中的作用：防止后续检索相关改动破坏标准问题的召回质量。

### 文件：`tests/fixtures/golden_test_set.json`

* 主要职责：保存标准测试问题和期望命中的 chunk。
* 当前包含两条 case：
  * Azure OpenAI 配置问题，期望命中 `chunk_azure_openai_001`。
  * Ingestion 进度查看问题，期望命中 `chunk_dashboard_ingestion_001`。
* 在项目中的作用：作为评估和回归测试的固定题库。

### 文件：`src/observability/evaluation/eval_runner.py`

* H5 没有修改它，但 H5 依赖它。
* 它负责读取 golden set、运行检索、调用 evaluator、汇总指标。
* 在 H5 中，它把测试集、fake 检索器和 `CustomEvaluator` 串起来。

## 5. 新手重点理解

Recall 回归测试的核心不是追求“复杂”，而是追求“稳定”。

为什么 H5 使用 `GoldenHybridSearch` 这种 fake 检索器？因为这个阶段的目标是验证评估闭环和阈值逻辑，而不是依赖真实向量库、embedding 模型或外部服务。真实检索系统可能受数据环境影响，但回归测试应该尽量可重复、可控。

为什么要检查 `hit_rate`？因为 RAG 的第一步是找资料。如果标准问题连期望文档都找不到，后面生成再强也很难回答准确。

为什么还要检查 `mrr`？因为命中了还不够，命中结果最好靠前。MRR 会关注第一个命中结果的排名。比如正确 chunk 在第 1 名和第 10 名，`hit_rate` 可能都算命中，但 MRR 会明显不同。

为什么把阈值写死在测试里？因为这就是“质量红线”。以后改代码，如果指标低于阈值，就说明召回质量可能退步，需要开发者停下来检查。

这一阶段相当于给评估体系加了一个自动守门员：每次跑测试，它都会检查标准问题还能不能稳定召回正确内容。
