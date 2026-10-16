"""离线检查规范文件；这不是产品运行时测试。"""
# 本脚本离线检查规范文件，不会启动或测试产品运行时。
from __future__ import annotations

# ast 用于检查 Python 语法；json 用于解析 JSON 文件。
import ast
import json
import os
# 正则、Unicode 分类及 URL 解码用于 Markdown 规则检查。
import re
import sys
import unicodedata
# dataclass 定义结果结构；Path 处理文件系统路径。
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote


# 检查结果是不可变对象，包含出错文件及原因。
@dataclass(frozen=True)
class Finding:
    path: Path
    message: str


# 仓库检查器把本地检查与 CI 检查统一到同一实现。
class RepositoryChecker:
    """Keep local and CI planning checks identical without third-party packages."""

        # 将根目录规范为绝对路径，并准备问题列表。
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.findings: list[Finding] = []

        # 扫描仓库并返回发现的问题。
    def check(self) -> tuple[Finding, ...]:
        # 清空旧结果，确保每轮检查相互独立。
        self.findings.clear()
        # 排除依赖、版本控制、运行数据及缓存目录。
        excluded = {'.git', '.venv', 'node_modules', '__pycache__', 'var', '.pytest_cache', '.mypy_cache', '.ruff_cache'}
        # 递归遍历仓库目录。
        for folder, directories, names in os.walk(self.root):
            # 原地过滤目录，并排序以保证检查顺序稳定。
            directories[:] = sorted(name for name in directories if name not in excluded)
            # 对文件名排序，让输出结果稳定。
            for name in sorted(names):
                # 组合当前目录和文件名得到文件路径。
                path = Path(folder) / name
                # 只检查 Markdown、JSON 和 Python 文件。
                if path.suffix not in {'.md', '.json', '.py'}:
                    continue
                # 读取或解析失败时记录问题，然后继续检查其他文件。
                try:
                    # 目标文件统一按 UTF-8 读取。
                    text = path.read_text(encoding='utf-8')
                    # JSON 文件只做语法解析。
                    if path.suffix == '.json':
                        json.loads(text)
                    # Python 文件只解析语法，不会执行。
                    elif path.suffix == '.py':
                        ast.parse(text, filename=str(path))
                    # Markdown 文件交由专用检查方法处理。
                    else:
                        self._check_markdown(path, text)
                # 收集常见读取、编码、解析和语法错误。
                except (OSError, UnicodeError, ValueError, SyntaxError) as error:
                    self.findings.append(Finding(path, str(error)))
        # 返回不可变的问题集合。
        return tuple(self.findings)

    # 静态工具方法不需要访问检查器实例。
    # 把 Markdown 标题转换成用于链接比对的锚点形式。
    @staticmethod
    def _slug(value: str) -> str:
        # 小写化，并用连字符替换空格。
        value = value.lower().replace(' ', '-')
        # 去掉标点和符号，保留连字符与下划线。
        return ''.join(char for char in value if char in '-_' or not unicodedata.category(char).startswith(('P', 'S')))

    # 静态工具方法：提取代码围栏之外的正文行。
    @staticmethod
    def _prose_lines(text: str) -> tuple[list[str], bool]:
        # lines 存正文；marker 记录当前是否位于代码块内。
        lines: list[str] = []
        marker = ''
        # 按行扫描文本，识别 Markdown 代码围栏。
        for line in text.splitlines():
            # 代码块可以使用至少三个反引号或波浪号。
            fence = re.match(r'^\s*(`{3,}|~{3,})', line)
            if fence:
                # 记录当前围栏标记及长度。
                current = fence.group(1)
                # 尚未进入代码块时，这一行开启代码块。
                if not marker:
                    marker = current
                # 同类且长度足够的围栏关闭代码块。
                elif current[0] == marker[0] and len(current) >= len(marker):
                    marker = ''
                # 围栏标记本身不加入正文。
                continue
            # 仅保留代码块外的行。
            if not marker:
                lines.append(line)
        # 返回正文行及代码围栏是否未闭合。
        return lines, bool(marker)

    # 从目标 Markdown 标题计算锚点，供本地链接校验使用。
    def _anchors(self, path: Path) -> set[str]:
        # 忽略代码块里的伪标题。
        lines, _ = self._prose_lines(path.read_text(encoding='utf-8'))
        # 统计重名标题，生成序号后缀。
        counts: dict[str, int] = {}
        result: set[str] = set()
        # 检查每一行是否为 Markdown 标题。
        for line in lines:
            # 支持一至六级标题。
            heading = re.match(r'^#{1,6}\s+(.+)', line)
            if heading:
                # 根据标题内容生成基础锚点。
                slug = self._slug(heading.group(1))
                # 读取该标题此前出现的次数。
                count = counts.get(slug, 0)
                # 首次出现不加序号，重复标题按顺序加后缀。
                result.add(slug if count == 0 else f'{slug}-{count}')
                counts[slug] = count + 1
        return result

    # 检查 Markdown 的代码围栏、本地链接及 Skill 元数据。
    def _check_markdown(self, path: Path, text: str) -> None:
        # 先排除代码示例，避免把示例链接当成真实链接。
        lines, unclosed = self._prose_lines(text)
        # 未闭合代码围栏说明文档格式有问题。
        if unclosed:
            self.findings.append(Finding(path, 'Unclosed code fence'))
        # 查找正文中的 Markdown 链接目标。
        for href in re.findall(r'\]\((<[^>]+>|[^)]+)\)', '\n'.join(lines)):
            # 去掉尖括号链接写法外层的括号。
            href = href.strip('<>')
            # 跳过 https:、mailto: 等外部 URI 链接。
            if re.match(r'^[A-Za-z][A-Za-z0-9+.-]*:', href):
                continue
            # 解码 URL，并拆出相对文件路径和章节锚点。
            relative, _, fragment = unquote(href).partition('#')
            # 相对当前文档解析；只有锚点时目标就是当前文件。
            target = (path.parent / relative).resolve() if relative else path
            # 先确认本地目标存在。
            if not target.exists():
                self.findings.append(Finding(path, f'Missing local link: {href}'))
            # 对 Markdown 文件的章节链接继续验证锚点。
            elif fragment and target.is_file() and target.suffix == '.md' and fragment not in self._anchors(target):
                self.findings.append(Finding(path, f'Missing section: {href}'))
        # SKILL.md 还需包含符合约定的 frontmatter。
        if path.name == 'SKILL.md':
            # frontmatter 必须位于文件开头并由 --- 包围。
            frontmatter = re.match(r'\A---\n(.*?)\n---\n', text, re.DOTALL)
            # 缺少 frontmatter 时无法检查其中字段。
            if not frontmatter:
                self.findings.append(Finding(path, 'Missing Skill frontmatter'))
                return
            # 提取 Skill 名称，格式限小写字母、数字和连字符。
            name = re.search(r'^name:\s*([a-z0-9-]+)\s*$', frontmatter.group(1), re.MULTILINE)
            # description 必须存在且非空。
            description = re.search(r'^description:\s*(\S[^\n]*)$', frontmatter.group(1), re.MULTILINE)
            # Skill 名称须与父目录名一致，并且要有描述。
            if not name or name.group(1) != path.parent.name or not description:
                self.findings.append(Finding(path, 'Skill name/description missing or folder name mismatch'))


# 命令行入口：运行检查并返回进程退出状态。
def main() -> int:
    # 脚本位于 tools/ 下，因此其父目录就是仓库根目录。
    root = Path(__file__).resolve().parents[1]
    # 实例化检查器并执行检查。
    findings = RepositoryChecker(root).check()
    # 按仓库相对路径逐条打印问题。
    for finding in findings:
        print(f'{finding.path.relative_to(root)}: {finding.message}')
    # 有任何发现都返回失败状态，供 CI 识别。
    if findings:
        return 1
    # 通过信息明确检查范围不包含运行时、模型及玩家行为。
    print('Repository structure checks passed. Runtime, model and player behavior were not tested.')
    return 0


# 只有直接运行此文件时才启动命令行检查。
if __name__ == '__main__':
    # 将检查返回值传给操作系统作为退出码。
    sys.exit(main())
