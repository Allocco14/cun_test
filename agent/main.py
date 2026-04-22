"""Entry point del agente de cierre de turno clínico (Google ADK)."""

import asyncio
import logging
import os
import sys

from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioServerParameters
from google.genai.types import Content, Part
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
log = logging.getLogger("agent")

console = Console()

APP_NAME = "clinical-shift-agent"
USER_ID  = "operator"

_MCP_MODULES = [
    "mcp_servers.database.server",
    "mcp_servers.filesystem.server",
    "mcp_servers.external_api.server",
    "mcp_servers.calculator.server",
]


# ---------------------------------------------------------------------------
# Agent factory
# ---------------------------------------------------------------------------

def build_agent() -> Agent:
    """Creates an ADK Agent wired to all MCP servers."""
    from agent.prompts import SYSTEM_PROMPT  # imported here so TODAY is evaluated at runtime

    py  = sys.executable
    env = dict(os.environ)

    toolsets = [
        McpToolset(
            connection_params=StdioServerParameters(
                command=py,
                args=["-m", module],
                env=env,
            )
        )
        for module in _MCP_MODULES
    ]

    log.info('{"event":"agent_built","toolsets":%d}', len(toolsets))

    return Agent(
        name="clinical_shift_agent",
        model=os.getenv("AGENT_MODEL", "gemini-2.0-flash"),
        description="Agente autónomo de cierre de turno para clínicas ambulatorias.",
        instruction=SYSTEM_PROMPT,
        tools=toolsets,
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run(prompt: str) -> str:
    """Run the agent with the given prompt and return the final response text."""
    _check_api_key()

    console.print(Panel(Text(prompt, style="bold cyan"), title="Prompt", border_style="cyan"))

    agent = build_agent()

    session_service = InMemorySessionService()
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID)

    message = Content(role="user", parts=[Part(text=prompt)])
    final_text = ""

    with console.status("[bold green]Agente ejecutando pasos del cierre de turno…[/bold green]"):
        async for event in runner.run_async(
            user_id=USER_ID,
            session_id=session.id,
            new_message=message,
        ):
            if not event.content or not event.content.parts:
                continue
            for part in event.content.parts:
                text = getattr(part, "text", None)
                if not text:
                    continue
                if event.is_final_response():
                    final_text = text
                else:
                    preview = text[:100].replace("\n", " ")
                    console.print(f"  [dim]↳ {preview}…[/dim]" if len(text) > 100 else f"  [dim]↳ {text}[/dim]")

    if final_text:
        console.print(Panel(final_text, title="[bold green]Resumen del Agente[/bold green]", border_style="green"))
    else:
        console.print("[yellow]El agente no emitió una respuesta final de texto.[/yellow]")

    return final_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_api_key() -> None:
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        console.print(
            "[bold red]ERROR:[/bold red] No se encontró GOOGLE_API_KEY ni "
            "GOOGLE_APPLICATION_CREDENTIALS en el entorno.\n"
            "Copia .env.example → .env y completa la clave."
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    if len(sys.argv) >= 2:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "Genera el cierre del turno de hoy para la clínica Centro Médico Norte"

    asyncio.run(run(prompt))


if __name__ == "__main__":
    main()
