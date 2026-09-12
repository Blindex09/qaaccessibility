import asyncio
import sys
import tempfile
from pathlib import Path

import droid_sdk as sdk
from droid_sdk.mcp import DroidTool, create_sdk_mcp_server

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "2026-09-04"))
from live_probe import load_keys


async def main():
    key = load_keys(Path(r"C:\Users\olive\Downloads\chaves de api.txt"))["factory"]
    server = create_sdk_mcp_server("qa", [DroidTool("qa_audit_probe", "Probe", {"type": "object", "properties": {}}, lambda args: "ok")])
    with tempfile.TemporaryDirectory() as directory:
        async with sdk.Session(cwd=directory, model="auto", api_key=key,
                               runtime=sdk.Runtime(executable=str(Path.home() / "bin/droid.exe")),
                               config=sdk.SessionConfig(mcp_servers=[server], restrict_tools=["qa___qa_audit_probe"], auto_reject_permission_requests=True)) as session:
            for tool in await session.list_tools():
                print(tool.id, tool.allowed, flush=True)


asyncio.run(main())
