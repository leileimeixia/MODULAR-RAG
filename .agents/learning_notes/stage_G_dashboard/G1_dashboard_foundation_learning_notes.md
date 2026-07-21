# G1_dashboard_foundation 学习笔记

## 1. 本阶段完成了什么

本阶段开始进入阶段 G，也就是可视化管理平台 Dashboard。

前面阶段已经把 RAG 的核心链路做出来了：文档可以摄取，向量和 BM25 可以入库，查询链路可以召回和重排，Trace 也能记录过程。但这些能力主要还是通过命令行和代码调用来使用。G1 的作用，就是先搭一个本地 Web 管理后台的骨架，让后续的数据浏览、文件摄取、Trace 查看、评估面板都有地方放。

这次完成的是 Dashboard 的第一块：系统总览页。它可以读取当前项目配置，展示 LLM、Embedding、Vision、Vector Store、Splitter、Retrieval、Rerank、Observability 等组件信息，也能读取本地 ChromaStore 的数据统计，比如当前 collection 里有多少条向量记录、来自多少个源文档。

在整个 RAG 项目中，它不直接参与“检索生成”本身，而是属于可观测性和管理层。可以把它理解为这个 RAG 系统的控制台首页。

## 2. 本阶段新增或修改的文件

| 文件路径 | 文件作用 |
| --- | --- |
| `src/observability/dashboard/app.py` | Streamlit Dashboard 主入口，注册六个页面并负责页面导航 |
| `src/observability/dashboard/pages/overview.py` | 系统总览页，展示组件配置卡片和数据统计指标 |
| `src/observability/dashboard/services/config_service.py` | Dashboard 配置服务，负责读取 Settings、格式化组件信息、读取 Chroma 数据统计 |
| `src/observability/dashboard/pages/data_browser.py` | 数据浏览页占位入口，后续 G3 实现 |
| `src/observability/dashboard/pages/ingestion_manager.py` | Ingestion 管理页占位入口，后续 G4 实现 |
| `src/observability/dashboard/pages/ingestion_traces.py` | Ingestion Trace 页占位入口，后续 G5 实现 |
| `src/observability/dashboard/pages/query_traces.py` | Query Trace 页占位入口，后续 G6 实现 |
| `src/observability/dashboard/pages/evaluation_panel.py` | 评估面板占位入口，后续 H4 实现 |
| `src/libs/vector_store/chroma_store.py` | 增加 `get_collection_stats()`，给 Dashboard 提供 collection 统计 |
| `scripts/start_dashboard.py` | Dashboard 启动脚本，封装 `python -m streamlit run ...` |
| `pyproject.toml` / `requirements.txt` | 增加 `streamlit>=1.36` 依赖 |
| `tests/unit/test_dashboard_app.py` | 测试 Dashboard 六个页面是否正确注册，以及占位页可渲染 |
| `tests/unit/test_dashboard_config_service.py` | 测试配置服务、敏感字段过滤、Chroma 统计读取 |
| `tests/unit/test_start_dashboard.py` | 测试启动脚本是否生成正确的 Streamlit 命令 |

## 3. 核心调用关系

```text
用户运行 scripts/start_dashboard.py
  -> 调用 python -m streamlit run src/observability/dashboard/app.py
  -> app.py 注册六个 Dashboard 页面
  -> 用户进入 System Overview 页面
  -> overview.render(st) 调用 ConfigService
  -> ConfigService 读取 config/settings.yaml
  -> ConfigService 格式化组件配置卡片
  -> ConfigService 调用 ChromaStore.get_collection_stats()
  -> overview.py 把组件信息和数据统计渲染到 Streamlit 页面
```

这里的数据流很清晰：启动脚本负责启动页面，`app.py` 负责导航，`overview.py` 负责页面展示，`ConfigService` 负责准备页面所需数据，`ChromaStore` 负责提供真实的向量库统计。

## 4. 每个核心文件的作用

### 文件：`src/observability/dashboard/app.py`

* 主要职责：作为 Dashboard 的 Streamlit 入口。
* 关键类 / 函数：
  * `DashboardPage`：描述一个页面的标题、图标和渲染函数。
  * `page_specs()`：集中注册六个页面。
  * `main()`：启动 Streamlit 页面，优先使用 `st.navigation()`，旧版本 Streamlit 则回退到侧边栏 `radio`。
  * `_import_streamlit()`：运行时导入 Streamlit，如果未安装则给出清晰错误。
* 输入是什么：Streamlit 运行环境。
* 输出是什么：一个可导航的本地 Dashboard 应用。
* 在项目中的作用：给阶段 G 的所有页面提供统一入口，后续 G2-G6 都会挂在这里。

### 文件：`src/observability/dashboard/pages/overview.py`

* 主要职责：渲染系统总览页。
* 关键函数：
  * `render(st, config_service=None)`：读取总览数据，并用 Streamlit 显示指标、组件配置和存储路径。
* 输入是什么：Streamlit 对象，以及可选的 `ConfigService`。
* 输出是什么：页面上的系统概览。
* 在项目中的作用：让用户不用看 YAML 和代码，也能知道当前 RAG 系统使用了哪些 provider、模型和存储配置。

### 文件：`src/observability/dashboard/services/config_service.py`

* 主要职责：把底层配置数据整理成 Dashboard 好展示的格式。
* 关键类 / 函数：
  * `ConfigService.load_settings()`：读取 `config/settings.yaml`。
  * `component_cards()`：把 Settings 拆成组件卡片。
  * `data_stats()`：读取 ChromaStore 统计信息。
  * `overview()`：汇总页面需要的所有数据。
  * `_safe_details()`：过滤 `api_key` 这类敏感字段，避免密钥显示到页面上。
* 输入是什么：settings 文件路径。
* 输出是什么：组件卡片列表和数据统计字典。
* 在项目中的作用：它是 Dashboard 页面和底层配置/存储之间的适配层。

### 文件：`src/libs/vector_store/chroma_store.py`

* 主要职责：本地向量存储适配器。
* 本阶段新增函数：
  * `get_collection_stats()`：返回 collection 名称、provider、持久化目录、collection 文件路径、记录数、源文档数。
* 输入是什么：当前 ChromaStore 的内存记录和配置。
* 输出是什么：Dashboard 可直接展示的统计字典。
* 在项目中的作用：让 Dashboard 能看到“知识库现在有多少数据”，而不是只看到静态配置。

### 文件：`scripts/start_dashboard.py`

* 主要职责：提供一个稳定的 Dashboard 启动命令。
* 关键函数：
  * `main(argv=None)`：组装 `python -m streamlit run src/observability/dashboard/app.py` 命令并执行。
* 输入是什么：可选的 Streamlit 命令行参数，比如端口参数。
* 输出是什么：Streamlit 进程退出码。
* 在项目中的作用：让用户不用记完整 Streamlit 路径，直接运行脚本即可启动管理后台。

## 5. 新手重点理解

这一阶段最重要的是理解“页面”和“数据服务”为什么要分开。

`overview.py` 只负责展示页面，不直接到处读取配置、不直接拼复杂数据。真正读取配置、清洗字段、统计向量库数据的工作放在 `ConfigService` 里。这样做的好处是：页面代码更像“前端”，服务代码更像“后端”。以后如果总览页要新增展示字段，只需要改服务输出和页面展示，不会把所有逻辑揉成一团。

另一个重点是 `app.py` 的页面注册。当前 Dashboard 规划有六个页面，但 G1 只实现系统总览页。其它页面先有 `render()` 占位函数，是为了让导航框架先完整跑起来。后续开发 G3、G4、G5、G6 时，只需要替换对应页面的内部实现，不需要重新改 Dashboard 主入口。

还要注意敏感信息过滤。配置里可能有 `api_key`，Dashboard 是可视化页面，不能把密钥直接展示出来。所以 `ConfigService._safe_details()` 会过滤掉 `api_key` 和以 `_key` 结尾的字段。这是管理后台开发里很容易忽略但非常重要的一点。

最后，`ChromaStore.get_collection_stats()` 让总览页不只是“配置展示页”，而是开始连接真实数据资产。它能告诉你当前 collection 里到底有没有数据、多少条 chunk、来自多少个源文件。对 RAG 系统来说，这是进入数据管理能力的第一步。


# app.py
以下是对当前代码文件 app.py 的完整解析：

1. 文件定位
文件路径：src/observability/dashboard/app.py 作用与层级：该文件是整个 Modular RAG 项目可观测性仪表盘（Dashboard）的入口文件。它处于应用层的最前端，负责将底层的数据和逻辑通过 Web 界面展示给用户。 核心职责：初始化并启动基于 Streamlit 框架的 Web 仪表盘，配置全局页面属性，并负责将各个独立的功能页面（如系统概览、数据浏览、追踪日志等）组织成统一的导航菜单，供用户点击访问。

2. 函数拆解
DashboardError (自定义异常类)

作用：继承自 RuntimeError，用于在仪表盘启动失败（如缺少必要依赖）时抛出特定的业务异常，方便上层统一捕获和处理。
DashboardPage (数据类)

作用：使用 @dataclass 定义的数据结构，用于标准化描述仪表盘中的“单个页面”。
属性：包含 title（页面标题）、icon（页面图标）和 render（负责渲染该页面内容的回调函数）。
page_specs()

作用：页面注册中心。
输入/输出：无输入；返回一个 DashboardPage 对象列表。
核心功能：按导航顺序定义并返回系统的所有页面（包括系统概览、数据浏览、摄入管理、摄入追踪、查询追踪、评估面板共 6 个页面），并绑定对应的渲染函数。
main()

作用：仪表盘的主启动函数。
输入/输出：无输入；无返回值（直接启动 Streamlit 服务）。
核心功能：
导入 Streamlit 并设置网页基础配置（标题、图标、宽屏布局）。
获取所有页面配置。
兼容性路由：判断当前 Streamlit 版本是否支持新版多页面 API（st.navigation）。如果支持，则构建原生导航菜单并运行；如果不支持（旧版本），则回退到使用侧边栏单选框（radio）进行页面切换。
_import_streamlit()

作用：安全导入 Streamlit 库。
输入/输出：无输入；返回 streamlit 模块对象。
核心功能：尝试 import streamlit，如果环境中未安装该库，则捕获 ImportError 并抛出 DashboardError，提示用户安装依赖。
3. 执行流程
程序启动：当通过命令行运行该脚本时，触发 if __name__ == "__main__":，调用 main() 函数。
环境检查：main() 首先调用 _import_streamlit()。如果缺少 Streamlit 依赖，程序抛出 DashboardError 并终止；如果存在，则继续。
页面配置：调用 st.set_page_config() 设置网页的 Meta 信息（如标题为 "Modular RAG Dashboard"）。
加载页面：调用 page_specs() 获取包含 6 个功能页面的列表。
路由分发（核心分支）：
新版 Streamlit 分支：检测到 st.navigation 存在，遍历页面列表，将每个 DashboardPage 转换为 Streamlit 的 st.Page 对象，最后调用 st.navigation().run() 渲染出带有侧边栏高级导航的完整应用。
旧版 Streamlit 分支：检测到不支持新 API，则在侧边栏生成一个 radio 单选框，列出所有页面标题。等待用户选择后，通过 next() 找到对应的页面对象，并调用其 render(st) 方法渲染内容。
4. 场景示例
业务场景：你是一名 RAG 系统的运维工程师，刚刚部署了系统，现在需要查看数据摄入（Ingestion）是否正常。

全流程串联：

你在终端执行启动命令，程序进入 main()。环境检查通过，网页被配置为宽屏模式。
程序加载了 6 个页面。由于你的 Streamlit 版本较新，程序走了新版分支，在网页左侧生成了一个漂亮的导航菜单，里面列出了 "System Overview"、"Data Browser" 等选项。
你的目标是查看数据摄入情况，于是你在左侧菜单点击了 "Ingestion Traces"（摄入追踪）。
框架接收到点击事件，在 page_specs() 注册的列表中找到标题为 "Ingestion Traces" 的 DashboardPage 对象。
框架调用该对象绑定的 ingestion_traces.render(st) 函数。
网页主体区域瞬间刷新，展示了最近的数据摄入任务日志、耗时图表和成功/失败状态，帮助你快速确认数据同步是否健康。


