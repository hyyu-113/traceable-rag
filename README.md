# Traceable RAG · 文档检索与问答

面向中文制度、合同和产品表的文档问答项目。上传文件后，系统通过关键词与向量混合检索寻找证据，再生成带原文引用的回答，支持查看段落、页码或单元格范围并下载原文件。

适用于小规模、单工作区的文档查询与功能演示。示例资料为虚构内容；当前未提供账号权限、多个知识库隔离或高并发服务能力。

## 功能

- **文档解析**：支持带文字层的 PDF、Word（DOCX）和 Excel（XLSX），保留原始来源位置。
- **混合检索**：中文 BM25 与 Qdrant 向量检索并用，通过 RRF 融合候选，可选接入重排序服务。
- **原文引用**：回答中的引用编号由后端映射到本次检索片段；缺少引用或包含未知编号时返回无足够证据提示。
- **持久化**：原文件保存在上传目录，SQLite 保存文档与片段状态，Qdrant 保存向量及片段信息。
- **导入恢复**：按内容哈希去重；失败文档可重新上传；重启时恢复可检索片段。

## 快速运行

环境要求：Python 3.12、uv、Docker。需要分别配置兼容聊天接口的语言模型和兼容编码接口的向量模型。项目不附带密钥，不默认下载本地模型。

在项目根目录运行以下 PowerShell 命令：

```powershell
uv sync --frozen
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填写语言模型和向量模型的地址、密钥、模型名。
docker compose up -d qdrant
uv run --frozen python main.py
```

打开 [问答页面](http://127.0.0.1:8000/) 或 [接口文档](http://127.0.0.1:8000/docs)。Windows 已创建虚拟环境后也可运行 `start.cmd`。VSCode 请打开项目根目录，选择 `.venv` 解释器，使用“Traceable RAG”调试配置；服务入口为 `main.py`。

Linux/macOS 可使用 `test -f .env || cp .env.example .env` 创建配置，其余 uv 与 Docker 命令相同。默认仅监听本机地址。

### 模型配置

完整配置项及中文注释见 [.env.example](.env.example)。语言模型和向量模型可使用不同供应商。

| 配置组 | 必需内容 |
| --- | --- |
| `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` | 兼容 `/chat/completions` 协议的地址前缀、密钥和模型名称 |
| `EMBEDDING_BASE_URL` / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` | 兼容 `/embeddings` 协议的地址前缀、密钥和模型名称 |
| `QDRANT_URL` / `QDRANT_COLLECTION` | 向量数据库地址、集合名称；集合在首次写入时按向量维度创建 |
| `RERANKER_ENABLED` | 默认关闭；启用后的协议见 [接口约定](docs/api.md) |
| `DATA_DIR` / `UPLOAD_DIR` | 元数据目录与原文件目录 |

地址前缀是否带 `/v1` 以模型服务商要求为准，不要重复附加接口路径。选择 DeepSeek 作为语言模型时，向量模型仍需单独配置。

更换向量模型或地址，应使用新数据目录、上传目录和集合重新导入。相同维度不代表编码空间相同。更改切块参数也不会自动重建已完成的索引。

## 演示资料

```powershell
uv run --frozen python scripts/create_demo_data.py
```

脚本在 `data/demo/` 生成三份虚构资料：

| 文件 | 示例问题 | 核对要点 |
| --- | --- | --- |
| 员工差旅管理制度.docx | 北京普通员工住宿标准是多少？ | 每晚600元，查看对应章节和段落 |
| 软件采购合同.docx | 收到首付款后多久交付？ | 20个工作日，核对合同正文 |
| 产品价格表.xlsx | A100 的含税单价是多少？ | 1299元，核对产品价格工作表 |

建议依次展示上传、提问、展开引用和下载原文，再重复上传同一文件观察去重。以上为样例资料的预期答案，不是固定输出；真实模型效果需实际核对。

## 设计与实现

```text
上传文件 → 内容去重 → 结构解析 → 保留来源的切块 → 向量编码
         → 写入 Qdrant → SQLite 提交完成状态 → 更新 BM25

用户问题 → BM25 关键词检索 ─┐
         → 问题编码与向量检索 ─┴→ RRF 融合 → 可选重排序
                                → 选择证据 → 模型生成 → 引用编号校验
```

详细取舍见 [架构与边界](docs/architecture.md)，接口参数见 [接口约定](docs/api.md)，验证方法见 [测试与验收](docs/testing.md)。

| 目录或文件 | 内容 |
| --- | --- |
| `main.py` | 统一启动入口 |
| `traceable_rag/` | 配置、解析、索引、检索、生成与接口实现 |
| `traceable_rag/web/` | 中文交互页面，无额外前端构建步骤 |
| `tests/` | 单元、边界和离线集成测试 |
| `scripts/` | 虚构样例生成、真实服务验收和作品打包 |
| `docs/` | 对外技术说明 |
| `.vscode/` | 基于项目相对路径的调试配置 |

`data/`、`.env` 和 `.venv/` 为本地运行内容，均不属于作品源码包。

## 验证

离线测试不调用真实模型：

```powershell
uv run --frozen python -m pytest -q -p no:cacheprovider
uv run --frozen ruff check --no-cache .
```

真实服务验收会上传演示资料并调用已配置的模型，可能产生费用。应先生成样例、启动应用及 Qdrant，并保持重排序关闭：

```powershell
uv run --frozen python scripts/verify_live.py
```

报告写入 `data/live-verification.json`。离线链路通过不等于模型准确率达标；当前不声明未经问题集验证的准确率、延迟或吞吐量指标。

## 容器运行与数据维护

只启动数据库：`docker compose up -d qdrant`。

同时构建并启动应用：`docker compose --profile app up -d --build`。容器内数据库地址由 Compose 覆盖；模型服务若在宿主机上，需使用容器可访问的地址。应用的容器端口固定为8000。

`docker compose down` 保留命名卷；带 `-v` 会删除向量数据。备份与恢复需覆盖原文件、SQLite 和 Qdrant，避免只恢复其中一部分。运行中的 SQLite 可能包含 WAL 文件，应使用一致性备份方式或停写后备份。

## 适用边界

- 支持文字提取，不支持扫描件 OCR；Excel 公式保留为文本，不计算公式结果。
- 原文引用验证的是编号与片段的关联，不逐句证明回答正确；关键数字和结论应核对原文。
- 当前单进程导入与检索共享锁，大文件导入期间查询可能等待；不能直接增加工作进程扩容。
- 当前请求只包含本次问题，没有会话记忆；没有用户权限、文档版本替换或删除接口。
- 文本编码和生成会将相关内容发送至配置的模型服务。涉及真实业务资料时，应选择符合其使用要求的服务或私有端点。

## 依赖与授权

依赖版本由 `uv.lock` 锁定。PDF 解析使用 PyMuPDF，其 AGPL / 商业授权条件需结合实际用途确认，参见 [依赖与授权说明](docs/dependencies.md)。当前未选定项目级开源许可证。

## 分享源码

```powershell
uv run --frozen python scripts/package_release.py
```

脚本仅打包明确列出的源码、测试、技术文档和配置模板，生成项目父目录中的 `traceable-rag-作品源码.zip`，不包含密钥、上传资料、数据库、日志和虚拟环境。若同名文件已存在，需使用 `--output` 指定新文件名。
