# test split, model_raw: 102 contracts

| field | correct | wrong | missed | false alarm | true empty | flagged | unscorable | accuracy where gold has a value |
|---|---|---|---|---|---|---|---|---|
| expiration | 36 | 7 | 16 | 11 | 26 | 0 | 6 | 61.0% (36/59) |
| renewal | 21 | 0 | 2 | 2 | 76 | 0 | 1 | 91.3% (21/23) |
| notice | 11 | 0 | 2 | 12 | 77 | 0 | 0 | 84.6% (11/13) |
| deadline | 4 | 3 | 0 | 0 | 0 | 3 | 0 | 40.0% (4/10) |
