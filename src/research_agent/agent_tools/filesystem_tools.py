from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional

import aiofiles


# ------------------------------------------------------------
# Base directory: <cwd>/agent_files
# ------------------------------------------------------------

BASE_DIR: Path = Path.cwd() / "agent_files"
BASE_DIR.mkdir(parents=True, exist_ok=True)


def resolve_path(filename: str | Path) -> Path:
    """
    Resolve a file path within `agent_files` while preventing path traversal.
    """
    target = (BASE_DIR / filename).resolve()
    if BASE_DIR not in target.parents:
        raise ValueError("Invalid path: outside agent_files directory")
    return target


# ------------------------------------------------------------
# WRITE FILE
# ------------------------------------------------------------

async def write_file(filename: str | Path, content: str) -> Path:
    """
    Write text to a file asynchronously (overwrites if exists).
    Returns the path written.
    """
    filepath = resolve_path(filename)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(filepath, "w", encoding="utf-8") as f:
        await f.write(content)
    return filepath


# ------------------------------------------------------------
# READ FILE
# ------------------------------------------------------------

async def read_file(filename: str | Path) -> str:
    """
    Read a file asynchronously and return its content as a string.
    """
    filepath = resolve_path(filename)

    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
        return await f.read()


# ------------------------------------------------------------
# EDIT FILE (find & replace)
# ------------------------------------------------------------

async def edit_file(
    filename: str | Path,
    find_text: str,
    replace_text: str,
    count: int = -1,
) -> Path:
    """
    Edit a file asynchronously by replacing occurrences of `find_text`.
    `count = -1` replaces all. Returns the modified file path.
    """
    filepath = resolve_path(filename)

    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    content = await read_file(filepath)
    new_content = content.replace(find_text, replace_text, count)
    await write_file(filepath, new_content)

    return filepath


# ------------------------------------------------------------
# DELETE FILE
# ------------------------------------------------------------

async def delete_file(filename: str | Path) -> bool:
    """
    Delete a file asynchronously. Returns True if deleted, False if missing.
    """
    filepath = resolve_path(filename)

    if filepath.exists():
        filepath.unlink()
        return True

    return False


# ------------------------------------------------------------
# SEARCH DIRECTORY (list directories & files)
# ------------------------------------------------------------

async def search_directory(subdir: Optional[str | Path] = None) -> List[Path]:
    """
    List all files and directories inside the given subdir.
    Defaults to listing the root `agent_files` folder.
    """
    directory = resolve_path(subdir) if subdir else BASE_DIR

    if not directory.exists() or not directory.is_dir():
        raise NotADirectoryError(f"Directory not found: {directory}")

    return [p for p in directory.iterdir()]


# ------------------------------------------------------------
# SEARCH FILES (recursive glob search)
# ------------------------------------------------------------

async def search_files(pattern: str, subdir: Optional[str | Path] = None) -> List[Path]:
    """
    Search for files recursively inside agent_files using a glob pattern.
    Example: "*.txt", "**/*.md", "*_data.json"
    """
    directory = resolve_path(subdir) if subdir else BASE_DIR

    return [p for p in directory.rglob(pattern)]



# async def _example():
#     await write_file("hello.txt", "Hello world")
#     print(await read_file("hello.txt"))

#     await edit_file("hello.txt", "world", "agent")
#     print(await read_file("hello.txt"))

#     print(await search_files("*.txt"))
#     print(await search_directory())

#     await delete_file("hello.txt")


# if __name__ == "__main__":
#     asyncio.run(_example())
