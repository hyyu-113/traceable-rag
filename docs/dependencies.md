# 依赖与授权说明

项目的 Python 版本、直接依赖和开发依赖定义在 `pyproject.toml`，具体版本锁定在 `uv.lock`。正常部署使用 `uv sync --frozen`，避免不同机器自动解析出不同版本。

## PDF 解析依赖

本项目使用 PyMuPDF 提取 PDF 文字、页码和坐标。PyMuPDF 官方提供 AGPL 与商业授权两种方式，具体条件以其许可证文本为准。

- [PyMuPDF 官方授权说明](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright)
- [PyMuPDF 源码和许可证](https://github.com/pymupdf/PyMuPDF)

项目公开展示、分发和闭源商业交付是不同的使用场景。准备交付时，需要按实际分发与部署方式确认依赖授权；不能仅为自己的代码添加 MIT 许可证，就认为已改变第三方依赖的授权条件。若需更换 PDF 解析库，应重新验证中文提取、阅读顺序、坐标和加密文件处理。

本说明不授予额外使用权，也不替代各依赖的许可证。仓库尚未选定项目级开源许可证，不宣称已获得第三方商业授权。

## 运行与测试

FastAPI 提供接口服务；python-docx 与 openpyxl 解析 Office 文件；jieba 与 rank-bm25 负责中文关键词检索；qdrant-client 与 httpx 分别连接数据库和模型服务。

测试中的模型响应是明确标注的协议夹具，仅用于验证请求、状态和引用关联。实际回答由配置的模型生成；模型服务的使用条件和费用由服务商规定。
