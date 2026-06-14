# Workflow: Theme Momentum Ranking

## Obiettivo
Classifica tutti i 54 temi di AskLivermore per momentum ponderato, per identificare i settori più caldi su cui concentrare la selezione di titoli per swing trading.

## Formula di scoring
```
score = 5% * perf_1d + 50% * perf_1w + 30% * perf_1m + 15% * perf_3m
```
Il weekly domina (50%) perché è il timeframe più rilevante per lo swing trading. Il daily ha peso minimo (5%) per evitare rumore.

## Tool utilizzato
- `tools/theme_momentum_ranker.py`

## Come eseguire
```bash
python tools/theme_momentum_ranker.py
```

## Input richiesti
- Credenziali in `.env`: `ASKLIVERMORE_EMAIL`, `ASKLIVERMORE_PASSWORD`

## Output
- Stampa a terminale della classifica completa (54 temi)
- File JSON: `.tmp/theme_ranking.json`

## Struttura dati API
- Endpoint: `GET https://www.asklivermore.com/api/themes`
- Auth: Supabase (login via `/auth/v1/token?grant_type=password`)
- Supabase project: `dwihwpjhzssmssdewzof`
- Risposta: `{mainstream: [...], tomorrow: [...]}` — totale 54 temi
- Ogni tema include: `performance.1d/1w/1m/3m/6m/1y/5y`, `ratings.avg_ta/avg_fa/avg_ars`, `crowding`, `theme_type`, `stock_count`

## Campi output per tema
| Campo | Descrizione |
|-------|-------------|
| `rank` | Posizione in classifica |
| `score` | Punteggio momentum ponderato |
| `1d/1w/1m/3m` | Performance per timeframe (%) |
| `crowding` | very-uncrowded / uncrowded / moderate / crowded |
| `theme_type` | bottleneck / emerging / disruption / evolution |
| `stock_count` | Numero titoli nel tema |
| `avg_ta/avg_fa/avg_ars` | Score tecnico, fondamentale, AskLivermore |

## Note
- I dati sono aggiornati al close del giorno precedente (`as_of`)
- Temi con valori `None` in un timeframe vengono trattati come 0
- Il tema #43 (Glass Substrate Technology) ha tutti 0 — probabilmente non ancora valorizzato
- Prossimo step: selezionare i titoli nei top temi con filtri su TA score, crowding e pattern tecnici
