"""Agente che risponde alle domande sulle macchine, con un modello linguistico e il server MCP.

Avvio:  uv run python agente.py "c'è qualche macchina che si comporta in modo strano?"

Il modello si raggiunge con l'interfaccia di OpenAI, che parlano sia Ollama (in locale) sia molti
servizi in rete. Si sceglie con tre variabili d'ambiente:
  LLM_URL      default http://127.0.0.1:11434/v1  (Ollama)
  LLM_MODELLO  default qwen2.5:7b
  LLM_CHIAVE   la chiave del servizio; Ollama non la controlla

Il ciclo:
  1. il modello riceve la domanda e l'elenco degli strumenti del server MCP
  2. se chiede uno strumento, lo eseguiamo sul server e gli rimandiamo il risultato
  3. si ripete finché il modello risponde con del testo (o finiscono i passi a disposizione)
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import AsyncOpenAI

MAX_PASSI = 8     # un modello che chiama strumenti all'infinito si ferma qui


def strumenti_in_formato_openai(strumenti) -> list[dict]:
    return [
        {"type": "function",
         "function": {"name": t.name, "description": t.description or "", "parameters": t.input_schema}}
        for t in strumenti
    ]


def testo_risultato(risultato) -> str:
    """Il risultato di uno strumento come testo per il modello."""
    if risultato.is_error:
        return "ERRORE: " + " ".join(c.text for c in risultato.content if hasattr(c, "text"))
    return json.dumps(risultato.structured_content, ensure_ascii=False)


async def esegui(sessione: ClientSession, chiamata) -> str:
    nome = chiamata.function.name
    try:
        argomenti = json.loads(chiamata.function.arguments or "{}")
    except json.JSONDecodeError:
        return "ERRORE: argomenti non validi, devono essere un oggetto JSON"
    print("→", nome, json.dumps(argomenti, ensure_ascii=False))
    return testo_risultato(await sessione.call_tool(nome, argomenti))


async def rispondi(domanda: str) -> str:
    server = StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).with_name("server.py"))],
        env=dict(os.environ))   # senza, il client MCP passa al server solo poche variabili (niente DB_URL)
    llm = AsyncOpenAI(
        base_url=os.getenv("LLM_URL", "http://127.0.0.1:11434/v1"),
        api_key=os.getenv("LLM_CHIAVE", "ollama"),
        max_retries=6)          # i servizi gratuiti rispondono "troppe richieste": si aspetta e si riprova
    modello = os.getenv("LLM_MODELLO", "qwen2.5:7b")

    async with llm, stdio_client(server) as (r, w), ClientSession(r, w) as sessione:
        info = await sessione.initialize()
        strumenti = strumenti_in_formato_openai((await sessione.list_tools()).tools)
        messaggi = [
            {"role": "system", "content": info.instructions or ""},
            {"role": "user", "content": domanda},
        ]

        for _ in range(MAX_PASSI):
            risposta = await llm.chat.completions.create(
                model=modello, messages=messaggi, tools=strumenti, temperature=0)
            messaggio = risposta.choices[0].message
            messaggi.append(messaggio.model_dump(exclude_none=True))
            if not messaggio.tool_calls:
                return messaggio.content or ""          # niente strumenti: è la risposta finale

            for chiamata in messaggio.tool_calls:
                messaggi.append({"role": "tool", "tool_call_id": chiamata.id,
                                 "content": await esegui(sessione, chiamata)})

        return "Mi fermo: ho usato tutti i passi a disposizione senza arrivare a una risposta."


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")   # il terminale di Windows non sa scrivere tutti i caratteri
    domanda = " ".join(sys.argv[1:]) or "C'è qualche macchina che si sta comportando in modo strano?"
    print(asyncio.run(rispondi(domanda)))
