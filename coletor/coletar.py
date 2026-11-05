#!/usr/bin/env python3
"""Cão de Guarda · coletor de exemplo.

Busca nos Diários Oficiais municipais (API aberta do Querido Diário) trechos que
falam de proteção animal e aplica o pré-filtro que separa o que interessa
(editais, castração, ração, repasses a ONGs) do ruído (vaquejada, pneus, etc.).

Uso:
    python3 coletar.py                  # Bahia, últimos 30 dias
    python3 coletar.py --uf SP --dias 60
    python3 coletar.py --cidade 2927408 # só Salvador (código IBGE)

Saída: achados.json (um item por trecho, com cidade, data, link do diário e motivo).
"""
import argparse
import datetime as dt
import gzip
import json
import re
import time
import urllib.parse
import urllib.request

API = "https://api.queridodiario.org.br"
UA = {"User-Agent": "cao-de-guarda/1.0 (+https://github.com/leomagalhaesti/cao-de-guarda)"}

BUSCA = '"proteção animal" | castração | "bem-estar animal" | "maus-tratos" | "cães e gatos"'

# o que faz um trecho valer a leitura
SINAIS = {
    "castração": r"castra[çc][ãa]o|esteriliza",
    "edital / credenciamento": r"edital|chamamento|credenciamento|inscri[çc][õo]es",
    "ração / insumos": r"\bra[çc][ãa]o\b",
    "repasse a ONG": r"\bOSCs?\b|organiza[çc][ãa]o da sociedade civil|termo de (fomento|colabora)",
    "fundo municipal": r"fundo municipal",
    "valor": r"R\$\s?[\d.]+,\d{2}",
}
# o que quase sempre é ruído
RUIDO = r"vaquejada|rodeio|pneu|aposentadoria|merenda|educa[çc][ãa]o|abate|frigor[íi]fico"


def get(caminho, **params):
    url = f"{API}{caminho}?{urllib.parse.urlencode(params, doseq=True)}"
    for tentativa in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return json.load(r)
        except Exception:
            if tentativa == 4:
                raise
            time.sleep(5 * 2 ** tentativa)       # a API pública oscila (503): espera cada vez mais


def cidades_da_uf(uf):
    """Códigos IBGE de todas as cidades do estado (fonte oficial do IBGE)."""
    url = f"https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        corpo = r.read()
    if corpo[:2] == b"\x1f\x8b":            # o IBGE responde em gzip mesmo sem pedir
        corpo = gzip.decompress(corpo)
    return [str(m["id"]) for m in json.loads(corpo)]


def avaliar(trecho):
    t = " ".join(trecho.split())
    if re.search(RUIDO, t, re.I):
        return None
    motivos = [nome for nome, rx in SINAIS.items() if re.search(rx, t, re.I)]
    return motivos if len(motivos) >= 2 else None


def coletar(territorios, dias, lote=15):
    """Consulta em lotes de cidades: uma busca com o estado inteiro estoura o tempo da API."""
    desde = (dt.date.today() - dt.timedelta(days=dias)).isoformat()
    achados, total = [], 0
    for i in range(0, len(territorios), lote):
        grupo, offset = territorios[i:i + lote], 0
        while True:
            try:
                r = get("/gazettes", querystring=BUSCA, territory_ids=grupo, published_since=desde,
                        excerpt_size=500, number_of_excerpts=5, size=50, offset=offset)
            except Exception as e:
                print(f"lote {i // lote + 1} pulado ({e}); rode de novo depois para completar")
                break
            diarios = r.get("gazettes", [])
            for g in diarios:
                for trecho in g.get("excerpts", []):
                    motivos = avaliar(trecho)
                    if motivos:
                        achados.append({"cidade": g["territory_name"], "uf": g["state_code"], "data": g["date"],
                                        "motivos": motivos, "trecho": " ".join(trecho.split()), "diario": g["url"]})
            offset += len(diarios)
            if not diarios or offset >= r.get("total_gazettes", 0):
                total += r.get("total_gazettes", 0)
                break
    return achados, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uf", default="BA")
    ap.add_argument("--cidade", action="append", help="código IBGE (pode repetir)")
    ap.add_argument("--dias", type=int, default=30)
    ap.add_argument("--saida", default="achados.json")
    a = ap.parse_args()
    territorios = a.cidade or cidades_da_uf(a.uf)
    achados, total = coletar(territorios, a.dias)
    json.dump(achados, open(a.saida, "w"), ensure_ascii=False, indent=1)
    print(f"{total} diários com o tema · {len(achados)} trechos passaram no filtro → {a.saida}")


if __name__ == "__main__":
    main()
