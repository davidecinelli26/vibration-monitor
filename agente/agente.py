"""Agente che risponde alle domande sulle macchine, con un modello locale (Ollama) e il server MCP.

Avvio:  uv run python agente.py "c'è qualche macchina che si comporta in modo strano?"

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

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

MODELLO = os.getenv("MODELLO", "qwen2.5:7b")
MAX_PASSI = 8     # un modello che chiama strumenti all'infinito si ferma qui


def strumenti_per_ollama(strumenti) -> list[dict]:
    """Gli strumenti MCP nel formato che Ollama si aspetta (lo stesso di OpenAI)."""
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


async def rispondi(domanda: str) -> str:
    server = StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).with_name("server.py"))],
        env=dict(os.environ))   # senza, il client MCP passa al server solo poche variabili (niente DB_URL)
    async with stdio_client(server) as (r, w), ClientSession(r, w) as sessione:
        info = await sessione.initialize()
        strumenti = strumenti_per_ollama((await sessione.list_tools()).tools)
        messaggi = [
            {"role": "system", "content": info.instructions or ""},
            {"role": "user", "content": domanda},
        ]
        modello = ollama.AsyncClient()

        for _ in range(MAX_PASSI):
            risposta = await modello.chat(MODELLO, messaggi, tools=strumenti, options={"temperature": 0})
            messaggi.append(risposta.message)
            if not risposta.message.tool_calls:
                return risposta.message.content          # niente strumenti: è la risposta finale

            for chiamata in risposta.message.tool_calls:
                print("→", chiamata.function.name, json.dumps(chiamata.function.arguments, ensure_ascii=False))
                risultato = await sessione.call_tool(chiamata.function.name, chiamata.function.arguments)
                messaggi.append({"role": "tool", "tool_name": chiamata.function.name,
                                 "content": testo_risultato(risultato)})

        return "Mi fermo: ho usato tutti i passi a disposizione senza arrivare a una risposta."


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")   # il terminale di Windows non sa scrivere tutti i caratteri
    domanda = " ".join(sys.argv[1:]) or "C'è qualche macchina che si sta comportando in modo strano?"
    print(asyncio.run(rispondi(domanda)))
