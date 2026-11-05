"""The chat model.
MODEL_PROVIDER=azure_openai (default) -> your Azure OpenAI (Gov) deployment with tool calling.
    AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_CHAT_MODEL (deployment name), AZURE_OPENAI_APIVERSION
    AZURE_OPENAI_API_KEY set   -> API key (a LangSmith deployment secret / Key Vault; never in code)
    AZURE_OPENAI_API_KEY unset -> managed identity (preferred in Azure)
    Older names CHAT_DEPLOYMENT and AZURE_OPENAI_API_VERSION still work.
MODEL_PROVIDER=offline -> a tiny keyword router so the prototype runs with no model (demo/tests only)."""
from __future__ import annotations

import functools
import json
import os
import re
import uuid

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage


def _env(*names: str, default: str | None = None) -> str | None:
    for n in names:
        if os.getenv(n):
            return os.environ[n]
    return default


@functools.lru_cache(maxsize=1)
def get_model():
    """Built once per process (one HTTP connection pool), not once per run."""
    provider = os.getenv("MODEL_PROVIDER", "azure_openai")
    if provider == "offline":
        return OfflineRouter()
    if provider != "azure_openai":
        raise ValueError(f"MODEL_PROVIDER must be azure_openai or offline, not {provider!r}")
    import httpx
    from langchain_openai import AzureChatOpenAI

    from platform_auth import tls_context

    endpoint = _env("AZURE_OPENAI_ENDPOINT")
    deployment = _env("AZURE_OPENAI_CHAT_MODEL", "CHAT_DEPLOYMENT")
    if not endpoint or not deployment:
        raise ValueError("set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_CHAT_MODEL (or MODEL_PROVIDER=offline)")
    kwargs = dict(azure_endpoint=endpoint, azure_deployment=deployment, temperature=0,
                  api_version=_env("AZURE_OPENAI_APIVERSION", "AZURE_OPENAI_API_VERSION", default="2024-10-21"),
                  timeout=float(os.getenv("MODEL_TIMEOUT_SECONDS", "60")), max_retries=2,
                  http_client=httpx.Client(verify=tls_context()), http_async_client=httpx.AsyncClient(verify=tls_context()))
    key = _env("AZURE_OPENAI_API_KEY")
    if key:
        kwargs["api_key"] = key
    else:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider
        scope = os.getenv("AZURE_OPENAI_SCOPE", "https://cognitiveservices.azure.us/.default")  # Gov
        kwargs["azure_ad_token_provider"] = get_bearer_token_provider(DefaultAzureCredential(), scope)
    return AzureLLM(AzureChatOpenAI(**kwargs))


class AzureLLM:
    def __init__(self, llm):
        self.llm = llm

    async def ainvoke(self, messages: list[BaseMessage], tools) -> AIMessage:
        return await (self.llm.bind_tools(tools) if tools else self.llm).ainvoke(messages)


# ------------------------------------------------------------------ offline (no model)
def _text(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content if isinstance(c, dict))


def _payload(msg: ToolMessage) -> dict:
    try:
        return json.loads(_text(msg.content))
    except (json.JSONDecodeError, TypeError):
        return {"raw": _text(msg.content)}


class OfflineRouter:
    """Picks one tool by keywords, then formats the tool result. Good enough to demo the plumbing."""

    async def ainvoke(self, messages: list[BaseMessage], tools) -> AIMessage:
        names = {t.name for t in tools}
        last = messages[-1]
        if isinstance(last, ToolMessage):
            return AIMessage(content=self._summarize(last))
        q = _text(last.content).lower() if isinstance(last, HumanMessage) else ""
        call = None
        if re.search(r"\b(is there|exist|already|find (an|a) (agent|tool)|tool for|agent for|catalog)\b", q):
            call = ("search_catalog", {"query": _text(last.content)})
        elif re.search(r"holiday|day off|office closed|thanksgiving|christmas", q):
            call = ("list_holidays", {})
        elif re.search(r"invoice|payment|vendor|overdue", q):
            status = next((s for s in ("overdue", "pending approval", "paid") if s in q), None)
            call = ("query_invoices", {"status": status.capitalize()} if status else {})
        if call and call[0] in names:
            return AIMessage(content="", tool_calls=[{"name": call[0], "args": call[1], "id": f"call_{uuid.uuid4().hex[:8]}"}])
        return AIMessage(content="I can list company holidays, show the invoices you are allowed to see, "
                                 "or check whether an agent or tool already exists.")

    @staticmethod
    def _summarize(msg: ToolMessage) -> str:
        d = _payload(msg)
        if msg.name == "list_holidays":
            lines = [f"- {h['date']}: {h['name']}" for h in d.get("holidays", [])]
            return "Upcoming company holidays:\n" + "\n".join(lines)
        if msg.name == "query_invoices":
            rows = d.get("rows", [])
            if not rows:
                return f"No invoices you are permitted to see (query ran as {d.get('executed_as')})."
            lines = [f"- {r['invoice']} {r['vendor']}: ${r['amount']:,.2f}, {r['status']}" for r in rows]
            return (f"Invoices visible to {d.get('executed_as')} (row filter {', '.join(d.get('row_filter', []))}):\n"
                    + "\n".join(lines))
        if msg.name == "search_catalog":
            hits = d.get("results", [])
            if not hits:
                return "Nothing in the catalog matches that. File an intake request before building a new one."
            lines = [f"- {h['name']} ({h['kind'].replace('_', ' ')}, owner {h['team']}): {h['purpose']}" for h in hits]
            return "Already in the catalog - reuse before you build:\n" + "\n".join(lines)
        if "error" in d:
            return f"The tool returned an error: {d['error']}"
        return json.dumps(d)[:800]
