# Misure

Numeri misurati sul Raspberry Pi 3 A+ (462 MB visibili con `gpu_mem=16`), scheda nuda fuori dal guscio. I dati grezzi
stanno in [`archivio/`](archivio/README.md).

## Memoria

| Cosa | Valore |
|---|---|
| Disponibile a riposo, dopo `irrobustisci.sh` | 331 MB |
| `bmo-core` a regime | 146 MB |
| `bmo-core`, picco in uso normale | 175-184 MB |
| `bmo-core`, picco massimo osservato | 252 MB, su un limite di 280 MiB |
| `bmo-face` a regime | 10 MB |
| `bmo-face`, picco | 28 MB |
| Memoria disponibile con BMO a riposo | 207-214 MB |
| Prova di carico di 24 h | Picco 239 MB, nessun blocco |

## Temperatura

| Condizione | Valore |
|---|---|
| In uso, senza guscio | 43-45 °C |
| Prova di carico di 24 h, senza guscio | Massimo 48,3 °C, `throttled=0x0` |
| Stress su 4 core, 50 s | 53,7 °C, `throttled=0x0` |

## Microfoni

Capture 40, boost 2, parlato a voce normale.

| Misura | Valore |
|---|---|
| Sbilanciamento fra i due MEMS | Entro 0,5 dB |
| Picco del parlato | Circa −14 dBFS |
| Voce a 1 m | −39…−43 dBFS rms |
| Voce a 3 m e oltre | −45…−48 dBFS rms |
| Rumore ambiente, stanza silenziosa | −52…−55 dBFS rms |

## Wake word

Punteggio del modello che reagisce alla parola, 5 ripetizioni per cella, stanza silenziosa.

| Parola (modello) | 1 m | 3 m | Punto più lontano |
|---|---|---|---|
| «Hey BMO» (`bmo2`) | 0,57 0,69 0,74 0,77 0,71 | 0,25 0,86 0,82 0,30 0,48 | 0,74 0,76 0,51 0,69 0,34 |
| «BMO» (`bmo1`) | 0,64 0,99 0,93 0,99 0,39 | 0,98 0,98 0,73 0,94 0,94 | 0,91 0,92 0,99 0,03 0,83 |

Con la soglia di 0,20, a 3 m e oltre «Hey BMO» è stato riconosciuto 10 volte su 10 e «BMO» 9 su 10. Il punteggio
massimo in stanza silenziosa è stato 0,0016, quindi nessun falso scatto.

## Tempi

| Passo | Valore |
|---|---|
| Sintesi vocale di una frase, sul Pi | 1,0-2,0 s |
| Scatto di una foto, sul Pi | 1,6 s |
| Dalla richiesta al primo fotogramma di un video | ~5 s |
| Dallo stacco della corrente a BMO sveglio | ~30-60 s, stima |

## Costo

Il piano gratuito di Gemini basta per l'uso domestico, ma le sue quote cambiano spesso. La voce con edge-tts, DuckDuckGo
e radio-browser sono gratuiti e senza chiave.

## Non ancora misurato

- Falsi scatti della wake word con TV, musica o conversazione.
- Pressione sonora dell'altoparlante.
- Latenza completa dalla fine della frase alla risposta.
- Temperatura e acustica a guscio chiuso: vedi il [collaudo finale](stampa-3d.md#6-collaudo-finale-a-guscio-chiuso).
- Il ciclo reale di stacco e riattacco della corrente, cronometrato.
