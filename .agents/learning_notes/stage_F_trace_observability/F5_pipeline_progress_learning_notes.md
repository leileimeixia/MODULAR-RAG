# F5_pipeline_progress 学习笔记

## 1. 本阶段完成了什么

本阶段给 `IngestionPipeline.run()` 增加了进度回调能力。

也就是说，外部调用文档摄取流程时，可以传入一个 `on_progress(stage_name, current, total)` 函数，实时知道当前处理到了哪一步、这是第几步、总共有多少步。

这个能力主要是给后面的 Dashboard 使用。比如用户在网页上上传一个 PDF 后，页面可以显示：

```text
正在校验文件：1/8
正在加载文档：2/8
正在切块：4/8
正在写入向量库：7/8
处理完成：8/8
```

在整个 RAG 项目里，F5 属于“摄取流程可视化支持”。它不改变文档如何处理，但让外部界面可以实时展示处理进度。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/ingestion/pipeline.py` | 给 `IngestionPipeline.run()` 增加 `on_progress` 参数，并在各阶段完成后触发回调 |
| `tests/unit/test_pipeline_progress.py` | 新增测试，验证完整摄取、跳过摄取和无回调场景 |
| `DEV_SPEC.md` | 更新 F5 任务状态和总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 的任务进度记录 |

## 3. 核心调用关系

```text
外部调用方
  -> IngestionPipeline.run(path, on_progress=callback)
  -> integrity 完成后 callback("integrity", 1, total)
  -> load 完成后 callback("load", 2, total)
  -> image_store 完成后 callback("image_store", 3, total)
  -> split 完成后 callback("split", 4, total)
  -> transform 完成后 callback("transform", 5, total)
  -> embed 完成后 callback("embed", 6, total)
  -> upsert 完成后 callback("upsert", 7, total)
  -> bm25_index 完成后 callback("bm25_index", 8, total)
  -> ingestion_complete 时 callback("ingestion_complete", 8, total)
```

如果文件已经处理过并被跳过：

```text
integrity
  -> ingestion_skip
```

如果 `on_progress=None`，流程不会调用任何回调，行为和以前一样。

## 4. 每个核心文件的作用

### 文件：`src/ingestion/pipeline.py`

* 主要职责：编排文档摄取流程。
* 本阶段修改点：
  * 定义 `ProgressCallback = Callable[[str, int, int], None]`。
  * `run()` 新增 `on_progress` 可选参数。
  * 新增 `_total_steps()` 计算总阶段数。
  * 新增 `_notify_progress()` 统一触发回调。
  * 在各个阶段完成后调用 `_notify_progress()`。
  * 在 `ingestion_complete`、`ingestion_skip`、`ingestion_failed` 时也通知外部。
* 输入是什么：文档路径、collection、force、trace、可选进度回调。
* 输出是什么：`IngestionResult`，并在运行过程中通过回调输出进度事件。
* 在项目中的作用：为 Dashboard 或 CLI 这类外部界面提供实时进度信息。

### 文件：`tests/unit/test_pipeline_progress.py`

* 主要职责：验证 progress callback 行为。
* 关键测试：
  * 完整摄取流程会按固定顺序报告阶段。
  * 每次回调都有 `stage_name`、`current`、`total`。
  * skip 路径会报告 `integrity` 和 `ingestion_skip`。
  * `on_progress=None` 时不会影响正常摄取。
* 在项目中的作用：保证后续 Dashboard 依赖进度回调时，事件格式是稳定的。

## 5. 新手重点理解

F5 解决的是“用户体验”问题。

如果没有进度回调，Dashboard 只能知道：

```text
开始导入
等待很久
导入完成 / 导入失败
```

用户不知道系统卡在哪里，也不知道还要等多久。有了 `on_progress` 后，界面可以实时显示当前阶段。

这个回调的签名很简单：

```python
on_progress(stage_name, current, total)
```

三个参数分别表示：

* `stage_name`：当前阶段名，比如 `"split"`、`"embed"`、`"upsert"`。
* `current`：当前完成到第几步。
* `total`：总共有多少步。

为什么进度回调放在 `IngestionPipeline.run()` 里？因为 pipeline 是整个摄取流程的总调度器，只有它最清楚现在执行到了哪一步。具体的 loader、chunker、embedding 组件只负责自己的小任务，不适合各自决定整体进度。

本阶段在 RAG 流程中的位置是“摄取流程进度通知层”。它不改变数据处理结果，但让外部系统可以实时感知摄取进度，为后续 Dashboard 的进度条打基础。

