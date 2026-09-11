# image_browser

基于 FastAPI 的本地图片浏览器与后台管理系统。支持本地模型自动打标、以图搜图（指纹 + 标签混合检索）、标签与翻译管理。

## 系统环境

支持以下操作系统：

- **Windows 10 / 11**（本项目已在 Windows 上实测；启动时自动使用 `SelectorEventLoop`，无需额外配置事件循环）
- **Linux**（Debian / Ubuntu 等）
- **macOS**

## Python 版本

- **Python 3.12 – 3.14**（`pyproject.toml` 声明 `>=3.12,<3.15`）
- 建议使用 3.12 / 3.13（实测通过）
- 包管理使用 [uv](https://docs.astral.sh/uv/)（推荐）或 pip

## 数据库

本项目**仅支持 PostgreSQL**（通过 `psycopg3` 异步驱动访问），不支持 MySQL / SQLite 等其它数据库。

- 建议版本：**PostgreSQL 14+**（pgvector / pgroonga 对较新版本支持最好）
- 所有表位于 `IMAGE_BROWSER_DB_SCHEMA` 指定的 schema（默认 `public`）

### 数据库扩展

| 扩展 | 用途 | 官方文档 |
| --- | --- | --- |
| `vector`（pgvector） | 图片指纹向量存储与 HNSW 相似度检索 | https://github.com/pgvector/pgvector |
| `pgroonga` | 标签全文搜索（`&@~` 等 Groonga 全文索引） | https://pgroonga.github.io/install/ |

#### 安装扩展

**Windows**：

- PostgreSQL 官方 EDB 安装器（https://www.enterprisedb.com/downloads/postgres-postgresql-downloads）在较新版本中可勾选安装 pgvector
- pgvector 也可从 https://github.com/pgvector/pgvector/releases 获取 Windows 安装包
- pgroonga 官方暂不提供 Windows 二进制，可在 WSL2 或 Docker 中运行 PostgreSQL 使用；如已通过其它渠道安装，跳过即可

**Debian / Ubuntu（使用 PGDG 官方仓库）**：

```bash
# 以 PostgreSQL 16 为例，版本号请替换为实际 PG 主版本
sudo apt install postgresql-16-pgvector postgresql-16-pgroonga
```

**macOS（Homebrew）**：

```bash
brew install pgvector
brew tap groonga/groonga && brew install pgroonga
```

**源码编译**：参考各扩展官方文档（pgvector / pgroonga）。

安装完成后，在 PostgreSQL 中启用扩展（`init.py` 会自动执行，也可以手动执行）：

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgroonga;
```

## 安装项目依赖

```bash
# 使用 uv（推荐）
uv sync --locked
```

> 本项目依赖 `torch` / `torchvision` / `onnxruntime-gpu` 等较重的推理依赖，首次同步耗时较长。
> 本地打标模型（pixai-tagger）会在服务启动时后台加载，首次使用需要从 Hugging Face 下载模型文件（需网络）。

## 配置

复制 `.env.example` 为 `.env` 并修改为实际环境：

```bash
cp .env.example .env
```

模板内容（所有环境变量使用 `IMAGE_BROWSER_` 前缀）：

```env
IMAGE_BROWSER_RELOAD=False

IMAGE_BROWSER_DB_HOST=localhost
IMAGE_BROWSER_DB_USER=postgres
IMAGE_BROWSER_DB_PASS=postgres
IMAGE_BROWSER_DB_BASE=postgres
IMAGE_BROWSER_DB_ECHO=True
```

> 更多配置项（搜索权重、模型名称、图片目录、数据库 schema 等）见 `image_browser/settings.py`，均可通过 `IMAGE_BROWSER_` 前缀的环境变量覆盖。

## 初始化数据库

首次部署（或数据库为全新库）时执行：

```bash
uv run python init.py
```

脚本会依次完成（**全程幂等**，可重复执行）：

1. 创建扩展 `vector` / `pgroonga`
2. 创建枚举类型 `tag_type` / `tag_sub_type`
3. 创建序列与全部数据表（`image` / `tag` / `tag_translation` / `image_tag_assoc` / `image_tag` / `series_character`）
4. 创建索引（HNSW 向量索引、pgroonga 全文索引、外键等）
5. 从 `data/tag.json`（14072 条）、`data/tag_translation.json`（28144 条）导入标签与翻译数据
6. 对齐自增序列

> 也可指定 schema 初始化：`uv run python init.py --schema custom_schema`
> 该 schema 需在 PostgreSQL 中已存在并有相应权限（或使用超级用户）。

## 启动项目

```bash
uv run -m image_browser
```

启动后：

- 管理后台首页（图片浏览）：http://127.0.0.1:8000/admin/
- 图片管理：http://127.0.0.1:8000/admin/image
- 标签管理：http://127.0.0.1:8000/admin/tag
- 标签翻译管理：http://127.0.0.1:8000/admin/translation
- Swagger 文档：http://127.0.0.1:8000/api/docs

## 主要功能

- **图片浏览与上传**：上传单文件或目录，本地模型自动打标并入库；图片按签名哈希的两位子目录存储
- **以图搜图**：上传图片，后台计算指纹并按标签匹配（混合检索，权重在服务端配置，前端不可调）
- **标签管理**：按图片聚合展示标签、新增/删除关联标签
- **标签翻译管理**：批量导入/修改标签翻译（en / zh），支持缺失翻译查询

## 项目结构

```text
image_browser/
├── image_browser/
│   ├── __main__.py      # 启动入口（Windows 自动切换 SelectorEventLoop）
│   ├── loop.py          # Windows 事件循环工厂
│   ├── settings.py      # 配置（环境变量 IMAGE_BROWSER_ 前缀）
│   ├── db/              # 数据访问（core.py 为 SQL 层，models 为数据库模型）
│   ├── web/
│   │   ├── admin/       # 管理后台页面（/admin）
│   │   └── api/         # RESTful API（/api）
│   └── static/          # 自定义样式与脚本
├── data/                # 导出的标签与翻译数据（init.py 导入）
├── images/              # 上传的图片（按两位哈希子目录存储）
├── init.py              # 一键初始化数据库
└── pyproject.toml
```
