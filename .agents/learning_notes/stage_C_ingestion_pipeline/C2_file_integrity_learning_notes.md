# C2_file_integrity 学习笔记

## 1. 本阶段完成了什么

本阶段实现了“文件完整性检查”。它的核心作用是：在真正解析 PDF、切分文本、生成向量之前，先给原始文件计算一个 SHA256 指纹，并把处理结果记录到 SQLite 数据库里。

这样做可以解决一个很实际的问题：同一个文件如果已经成功摄取过，下次再次摄取时就可以直接跳过，避免重复写入向量库、BM25 索引或图片存储。

在整个 RAG 流程中，它属于 Ingestion Pipeline 的最前置环节：

```text
原始文件
  -> 计算 SHA256
  -> 查询历史记录
  -> 已成功处理则跳过
  -> 未处理或曾失败则继续后续摄取流程
```

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/libs/loader/file_integrity.py` | 实现文件 hash 计算、SQLite 处理历史记录、跳过判断和成功/失败标记 |
| `src/libs/loader/__init__.py` | 对外导出文件完整性检查相关类和函数，方便其他模块统一导入 |
| `tests/unit/test_file_integrity.py` | 为 SHA256、SQLite 建库、成功/失败状态和并发写入提供单元测试 |
| `DEV_SPEC.md` | 将 C2 标记为完成，并更新阶段 C 与总进度 |
| `.agents/skills/auto-coder/references/06-schedule.md` | 同步 auto-coder 使用的任务进度表 |

## 3. 核心调用关系

```text
后续 IngestionPipeline
  -> SQLiteIntegrityChecker.compute_sha256(file_path)
  -> SQLiteIntegrityChecker.should_skip(file_hash)
      -> 如果 True：跳过该文件
      -> 如果 False：继续 loader/split/embedding/upsert
  -> 处理成功：mark_success(file_hash, file_path, metadata)
  -> 处理失败：mark_failed(file_hash, error_msg, file_path)
```

数据流可以理解为两条线：

```text
文件内容 -> compute_sha256 -> file_hash

file_hash + file_path + status
  -> SQLite file_integrity 表
  -> should_skip 判断是否重复处理
```

## 4. 每个核心文件的作用

### 文件：`src/libs/loader/file_integrity.py`

* 主要职责：封装文件完整性检查和摄取历史记录。
* 关键函数 / 类：
  * `compute_sha256(path)`：读取文件二进制内容，计算 SHA256 字符串。
  * `FileIntegrityChecker`：抽象接口，规定完整性检查器应该具备哪些能力。
  * `SQLiteIntegrityChecker`：默认实现，用 SQLite 保存处理历史。
  * `should_skip(file_hash)`：判断某个 hash 是否已经成功处理过。
  * `mark_success(...)`：记录文件处理成功。
  * `mark_failed(...)`：记录文件处理失败。
  * `get_record(file_hash)`：读取一条处理记录，主要给管理功能和测试使用。
* 输入是什么：
  * 文件路径
  * 文件 hash
  * 文件处理状态
  * 可选 metadata
* 输出是什么：
  * SHA256 字符串
  * 是否应该跳过的布尔值
  * SQLite 中的历史记录
* 在项目中的作用：
  * 为后续 Pipeline 提供“增量摄取”的基础能力，避免重复摄取同一个文件。

### 文件：`src/libs/loader/__init__.py`

* 主要职责：把 `file_integrity.py` 中常用的类和函数暴露出来。
* 关键函数 / 类：
  * `DEFAULT_DB_PATH`
  * `FileIntegrityChecker`
  * `FileIntegrityError`
  * `SQLiteIntegrityChecker`
  * `compute_sha256`
* 输入是什么：无直接业务输入。
* 输出是什么：统一的包导出入口。
* 在项目中的作用：
  * 让其他模块可以通过 `from libs.loader import SQLiteIntegrityChecker` 这种方式导入，而不用关心具体文件位置。

### 文件：`tests/unit/test_file_integrity.py`

* 主要职责：验证 C2 的核心行为是稳定可靠的。
* 关键测试：
  * 同一个文件多次计算 hash，结果一致。
  * 缺失文件会抛出清晰异常。
  * 标记成功后，`should_skip` 返回 `True`。
  * 标记失败后，不会跳过；之后成功记录可以覆盖失败状态。
  * SQLite 数据库会自动创建，并启用 WAL。
  * 多线程写入 success 记录可以正常工作。
* 输入是什么：测试临时目录中的文件和 SQLite 数据库。
* 输出是什么：pytest 断言结果。
* 在项目中的作用：
  * 保证这个增量摄取基础模块在后续被 Pipeline 调用时行为可预期。

## 5. 新手重点理解

SHA256 可以理解为文件内容的“指纹”。只要文件内容不变，算出来的 hash 就不变；只要文件内容有变化，hash 通常就会变化。因此它非常适合用来判断“这个文件是不是同一个文件”。

这里没有只按文件名判断是否重复，是因为文件名并不可靠。同一个文件可以改名，不同文件也可以叫同一个名字。用内容 hash 会更准确。

`FileIntegrityChecker` 是抽象接口，`SQLiteIntegrityChecker` 是具体实现。这样拆分的好处是：现在项目默认用 SQLite，后续如果想换成 Redis 或 PostgreSQL，只要写一个新的 checker 实现同样的方法，Pipeline 层不需要大改。

SQLite 表里记录的 `status` 很关键。只有 `success` 才表示可以跳过；如果上一次是 `failed`，说明文件可能只处理了一半或完全没处理成功，下次应该允许重新处理。

WAL 是 SQLite 的一种日志模式。这里启用它，是为了让后续摄取流程在并发或多次写入时更稳一些。对于本地 RAG 项目来说，它既轻量，又足够支撑早期的增量摄取需求。
