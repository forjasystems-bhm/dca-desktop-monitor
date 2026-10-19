from __future__ import annotations


def _num(valor):
    return None if valor is None else float(valor)


def metricas_ativo(dados: dict, livro_brl: dict | None = None, *,
                   brl: bool = False, taxa_brl: float | None = None) -> dict:
    est = dados.get("estimado", False)
    if not brl:
        return {
            "pmc": dados.get("pmc_final", 0),
            "custo": dados.get("custo_posicao_final", 0),
            "pl_nr": dados.get("lucro_nao_realizado"),
            "pl_r": dados.get("lucro_realizado", 0),
            "pl_tot": dados.get("lucro_total"),
            "comprado": dados.get("total_comprado_usdt", 0),
            "est": est,
        }
    if livro_brl is None:
        return {"pmc": None, "custo": None, "pl_nr": None, "pl_r": None,
                "pl_tot": None, "comprado": 0, "est": est}
    aberta = dados.get("quantidade_final", 0) > 1e-9
    qtd_livro = float(livro_brl["quantidade"])
    custo = _num(livro_brl["custo_aberto"])
    if custo is not None and not aberta:
        custo = 0.0
    pmc = (None if custo is None else
           custo / qtd_livro if aberta and qtd_livro > 1e-12 else 0.0)
    v_atual = dados.get("valor_atual_posicao")
    if custo is None:
        pl_nr = None
    elif not aberta:
        pl_nr = 0.0
    elif v_atual is None or taxa_brl is None:
        pl_nr = None
    else:
        pl_nr = v_atual * taxa_brl - custo
    pl_r = _num(livro_brl["realizado_historico"])
    return {
        "pmc": pmc, "custo": custo, "pl_nr": pl_nr, "pl_r": pl_r,
        "pl_tot": None if pl_nr is None or pl_r is None else pl_nr + pl_r,
        "comprado": _num(livro_brl["compras_historicas"]) or 0,
        "est": est or livro_brl.get("estimado", False),
    }


def totais_exibicao(resumo: dict, metricas: list[dict], totais_brl: dict | None = None,
                    *, brl: bool = False) -> tuple:
    est = resumo.get("estimado", False)
    if not brl:
        return (resumo.get("investido_liquido", 0), resumo.get("nao_realizado"),
                resumo.get("realizado", 0), resumo.get("compras_historicas_usdt", 0), est)

    def soma(chave):
        if any(x[chave] is None for x in metricas):
            return None
        return sum(x[chave] for x in metricas)

    comprado = (totais_brl or {}).get("compras_historicas")
    return (soma("custo"), soma("pl_nr"), soma("pl_r"),
            None if comprado is None else float(comprado),
            est or any(x["est"] for x in metricas))
