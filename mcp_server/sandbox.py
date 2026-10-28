"""文件操作沙箱：所有路径必须落在 workspace/ 目录内，杜绝路径穿越。"""

from pathlib import Path


class SandboxError(Exception):
    """路径越界或非法时抛出。"""


WORKSPACE = (Path(__file__).resolve().parent.parent / "workspace").resolve()


def resolve_safe(path: str) -> Path:
    """把用户传入的相对/绝对路径解析为 workspace 内的绝对路径。

    任何试图用 ``..`` 或绝对路径逃出 workspace 的请求都会被拒绝。
    """
    if path is None:
        path = "."
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = WORKSPACE / candidate

    resolved = candidate.resolve()

    if resolved != WORKSPACE and WORKSPACE not in resolved.parents:
        raise SandboxError(f"路径越界，仅允许操作 workspace 目录：{path}")
    return resolved


def display_path(path: Path) -> str:
    """把绝对路径转成相对 workspace 的可读形式。"""
    try:
        rel = path.resolve().relative_to(WORKSPACE)
    except ValueError:
        return str(path)
    return rel.as_posix()
